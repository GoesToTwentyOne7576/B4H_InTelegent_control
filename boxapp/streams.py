"""
Live video: one background thread per camera reads the RTSP stream with OpenCV and keeps the
latest frame as a JPEG. Any number of browser viewers share that one connection.
"""
import atexit
import logging
import os
import threading
import time

# Must be set before cv2 is imported: RTSP over TCP is far more reliable than UDP.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
import cv2  # noqa: E402

log = logging.getLogger("b4h.live")

IDLE_STOP = 10        # seconds with no viewer before the RTSP connection is closed
MAX_WIDTH = 960       # frames wider than this are downscaled
JPEG_QUALITY = 70


class CameraStream:
    def __init__(self, url: str):
        self.url = url
        self._cond = threading.Condition()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._jpeg: bytes | None = None
        self._seq = 0
        self._last_access = 0.0
        self._stop = False

    def _ensure_running(self) -> None:
        with self._lock:
            if not (self._thread and self._thread.is_alive()):
                self._thread = threading.Thread(target=self._run, daemon=True)
                self._thread.start()

    def _run(self) -> None:
        cap = None
        try:
            while not self._stop and time.time() - self._last_access < IDLE_STOP:
                if cap is None:
                    cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
                    if not cap.isOpened():
                        cap.release()
                        cap = None
                        log.warning("Cannot open camera stream")
                        time.sleep(3)
                        continue
                ok, frame = cap.read()
                if not ok:
                    cap.release()
                    cap = None
                    time.sleep(1)
                    continue
                h, w = frame.shape[:2]
                if w > MAX_WIDTH:
                    frame = cv2.resize(frame, (MAX_WIDTH, int(h * MAX_WIDTH / w)))
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                if ok:
                    with self._cond:
                        self._jpeg = buf.tobytes()
                        self._seq += 1
                        self._cond.notify_all()
        finally:
            if cap is not None:
                cap.release()

    def stop(self) -> None:
        self._stop = True
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=3)

    def frames(self):
        """Yield JPEG bytes as new frames arrive. Ends if the camera stays silent for ~15 s."""
        self._last_access = time.time()
        self._ensure_running()
        seen, silent = 0, 0
        while True:
            with self._cond:
                got = self._cond.wait_for(lambda: self._seq != seen, timeout=5)
                jpeg, seen = self._jpeg, self._seq
            self._last_access = time.time()
            if not got:
                silent += 1
                if silent >= 3:
                    return
                continue
            silent = 0
            yield jpeg

    def snapshot(self, timeout: float = 8) -> bytes | None:
        self._last_access = time.time()
        self._ensure_running()
        with self._cond:
            self._cond.wait_for(lambda: self._jpeg is not None, timeout=timeout)
            return self._jpeg


_streams: dict[int, CameraStream] = {}
_registry_lock = threading.Lock()


def get_stream(device_id: int, url: str) -> CameraStream:
    with _registry_lock:
        s = _streams.get(device_id)
        if s is None or s.url != url:
            s = _streams[device_id] = CameraStream(url)
        return s


@atexit.register
def _stop_all() -> None:
    """Close camera connections cleanly when the server exits."""
    for s in list(_streams.values()):
        s._stop = True
    for s in list(_streams.values()):
        s.stop()
