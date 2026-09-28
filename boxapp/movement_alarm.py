"""
Portal-side restricted movement detector.

This module uses the existing RTSP URL provider and OpenCV. It intentionally
does NOT invent a B4H movement/intrusion API.

Detection method:
    RTSP -> OpenCV background subtraction -> restricted polygon -> alarm event

This detects visual movement inside the configured polygon. It does not
identify whether the moving object is a person, vehicle, etc. If the B4H box
later exposes a real object/region/line-crossing API, this service can be
replaced by an API-backed detector without changing the admin UI.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta

import cv2
import numpy as np
from django.utils import timezone
from .models import MovementAlarmEvent, MovementAlarmRule
from .services import camera_rtsp_url

log = logging.getLogger("b4h.movement")

DEFAULT_WIDTH = 960
MIN_CONTOUR_AREA = 500
PROCESS_INTERVAL = 0.12


class PolygonZone:
    def __init__(self, points):
        self.points = np.array(points, dtype=np.int32).reshape((-1, 1, 2))

    def mask(self, shape):
        mask = np.zeros(shape[:2], dtype=np.uint8)
        if len(self.points) >= 3:
            cv2.fillPoly(mask, [self.points], 255)
        return mask


class MovementRuleWorker:
    def __init__(self, rule_id: int):
        self.rule_id = rule_id
        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name=f"movement-rule-{rule_id}",
            daemon=True,
        )
        self.last_alarm_at = 0.0

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=3)

    def _run(self):
        cap = None
        subtractor = cv2.createBackgroundSubtractorMOG2(
            history=300,
            varThreshold=32,
            detectShadows=True,
        )
        consecutive = 0

        try:
            while not self.stop_event.is_set():
                rule = MovementAlarmRule.objects.filter(
                    pk=self.rule_id,
                    enabled=True,
                ).first()

                if not rule:
                    return

                url = camera_rtsp_url(rule.device_id)
                if not url:
                    log.warning(
                        "No RTSP URL available for movement rule %s",
                        rule.pk,
                    )
                    time.sleep(5)
                    continue

                if cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
                    if not cap.isOpened():
                        log.warning(
                            "Cannot open camera %s for movement rule %s",
                            rule.device_id,
                            rule.pk,
                        )
                        time.sleep(5)
                        continue

                ok, frame = cap.read()
                if not ok:
                    cap.release()
                    cap = None
                    time.sleep(1)
                    continue

                h, w = frame.shape[:2]
                if w > DEFAULT_WIDTH:
                    frame = cv2.resize(
                        frame,
                        (
                            DEFAULT_WIDTH,
                            int(h * DEFAULT_WIDTH / w),
                        ),
                    )

                if len(rule.zone_points) < 3:
                    consecutive = 0
                    time.sleep(1)
                    continue

                zone = PolygonZone(rule.zone_points)
                mask = zone.mask(frame.shape)

                fg = subtractor.apply(frame)
                _, fg = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
                fg = cv2.morphologyEx(
                    fg,
                    cv2.MORPH_OPEN,
                    np.ones((3, 3), np.uint8),
                )
                fg = cv2.bitwise_and(fg, mask)

                moving_pixels = int(cv2.countNonZero(fg))
                zone_pixels = max(int(cv2.countNonZero(mask)), 1)
                score = moving_pixels / zone_pixels

                moving = score >= float(rule.sensitivity)

                if moving:
                    consecutive += 1
                else:
                    consecutive = 0

                if consecutive >= max(1, rule.trigger_frames):
                    now = time.time()
                    if now - self.last_alarm_at >= rule.cooldown_seconds:
                        MovementAlarmEvent.objects.create(
                            rule=rule,
                            device_id=rule.device_id,
                            detection_score=score,
                            duration_seconds=rule.alarm_duration_seconds,
                        )
                        self.last_alarm_at = now
                        log.warning(
                            "Restricted movement detected: rule=%s camera=%s score=%.4f",
                            rule.pk,
                            rule.device_id,
                            score,
                        )
                    consecutive = 0

                time.sleep(PROCESS_INTERVAL)

        except Exception:
            log.exception("Movement worker %s stopped unexpectedly", self.rule_id)
        finally:
            if cap is not None:
                cap.release()


class MovementAlarmManager:
    """
    One worker per enabled rule in this Django process.

    The project is designed for one server process, so this in-process
    registry follows the existing deployment constraint.
    """

    _lock = threading.Lock()
    _workers: dict[int, MovementRuleWorker] = {}

    @classmethod
    def start_rule(cls, rule_id: int):
        with cls._lock:
            worker = cls._workers.get(rule_id)
            if worker and worker.thread.is_alive():
                return

            worker = MovementRuleWorker(rule_id)
            cls._workers[rule_id] = worker
            worker.start()

    @classmethod
    def stop_rule(cls, rule_id: int):
        with cls._lock:
            worker = cls._workers.pop(rule_id, None)

        if worker:
            worker.stop()

    @classmethod
    def sync(cls):
        enabled = set(
            MovementAlarmRule.objects.filter(enabled=True)
            .values_list("id", flat=True)
        )

        for rule_id in enabled:
            cls.start_rule(rule_id)

        for rule_id in list(cls._workers):
            if rule_id not in enabled:
                cls.stop_rule(rule_id)

    @classmethod
    def stop_all(cls):
        for rule_id in list(cls._workers):
            cls.stop_rule(rule_id)
