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