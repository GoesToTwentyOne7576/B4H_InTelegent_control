"""
"Virtual" models: no database tables (managed = False). They exist only so each page shows up in
the admin sidebar and gets a "view" permission you can hand out per user or group.
"""
from django.db import models


class _BoxPage(models.Model):
    class Meta:
        abstract = True
        managed = False
        default_permissions = ("view",)


class RecognitionRecord(_BoxPage):
    class Meta(_BoxPage.Meta):
        verbose_name = "recognition record"
        verbose_name_plural = "Recognition"


class CaptureRecord(_BoxPage):
    class Meta(_BoxPage.Meta):
        verbose_name = "capture record"
        verbose_name_plural = "Captures"


class Person(_BoxPage):
    class Meta(_BoxPage.Meta):
        verbose_name = "person"
        verbose_name_plural = "People"


class Device(_BoxPage):
    class Meta(_BoxPage.Meta):
        verbose_name = "device"
        verbose_name_plural = "Devices"


class LiveView(_BoxPage):
    class Meta(_BoxPage.Meta):
        verbose_name = "live view"
        verbose_name_plural = "Live view"


class LogView(_BoxPage):
    class Meta(_BoxPage.Meta):
        verbose_name = "log"
        verbose_name_plural = "Logs"

class AlgorithmPackage(_BoxPage):
    class Meta(_BoxPage.Meta):
        verbose_name = "algorithm package"
        verbose_name_plural = "Algorithms"
        permissions = [("upload_algorithmpackage", "Can upload algorithm package")]















class MovementAlarmRule(models.Model):
    """
    Persistent configuration for the portal-side movement alarm.

    This is intentionally a real Django model because rules must survive
    server restarts. Camera credentials and RTSP URLs are never stored here.
    """

    name = models.CharField(max_length=120)
    device_id = models.IntegerField()
    zone_points = models.JSONField(default=list)
    enabled = models.BooleanField(default=True)

    # Motion sensitivity: minimum changed-pixel ratio in the zone.
    sensitivity = models.FloatField(default=0.015)

    # Require N consecutive detections before raising an alarm.
    trigger_frames = models.PositiveIntegerField(default=3)

    # Do not raise another alarm until this many seconds have elapsed.
    cooldown_seconds = models.PositiveIntegerField(default=30)

    # Alarm is considered active for display purposes for this duration.
    alarm_duration_seconds = models.PositiveIntegerField(default=10)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (camera {self.device_id})"


# class MovementAlarmEvent(models.Model):
#     rule = models.ForeignKey(
#         MovementAlarmRule,
#         on_delete=models.CASCADE,
#         related_name="events",
#     )
#     device_id = models.IntegerField()
#     detected_at = models.DateTimeField(auto_now_add=True)
#     duration_seconds = models.PositiveIntegerField(default=0)
#     detection_score = models.FloatField(default=0)
#     acknowledged = models.BooleanField(default=False)

#     class Meta:
#         ordering = ["-detected_at"]

#     def __str__(self):
#         return f"{self.rule.name} @ {self.detected_at:%Y-%m-%d %H:%M:%S}"

class MovementAlarmEvent(models.Model):
    rule = models.ForeignKey(
        MovementAlarmRule,
        on_delete=models.CASCADE,
        related_name="events",
    )

    device_id = models.IntegerField(
        null=False,
        blank=False,
    )

    detected_at = models.DateTimeField(auto_now_add=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    detection_score = models.FloatField(default=0)
    acknowledged = models.BooleanField(default=False)

    class Meta:
        ordering = ["-detected_at"]

    def __str__(self):
        return f"{self.rule.name} @ {self.detected_at:%Y-%m-%d %H:%M:%S}"


