from datetime import timedelta

from django import forms
from django.utils import timezone

from . import services

_DT_FORMAT = "%Y-%m-%dT%H:%M:%S"
_DT_INPUTS = ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
PAGE_SIZES = [(10, "10"), (20, "20"), (30, "30")]  # the box refuses more than 30 per request


def _dt_field(label: str) -> forms.DateTimeField:
    return forms.DateTimeField(
        label=label,
        input_formats=_DT_INPUTS,
        widget=forms.DateTimeInput(format=_DT_FORMAT, attrs={"type": "datetime-local", "step": "1"}),
    )


class _RangeForm(forms.Form):
    start = _dt_field("From")
    end = _dt_field("To")
    size = forms.TypedChoiceField(label="Per page", choices=PAGE_SIZES, coerce=int, initial=10)

    @staticmethod
    def default_range(days: int = 1) -> dict:
        now = timezone.localtime()
        return {
            "start": (now - timedelta(days=days)).strftime(_DT_FORMAT),
            "end": now.strftime(_DT_FORMAT),
            "size": "10",
        }

    def clean(self):
        cd = super().clean()
        if cd.get("start") and cd.get("end") and cd["start"] > cd["end"]:
            raise forms.ValidationError("'From' must be before 'To'.")
        return cd


class RecognitionFilterForm(_RangeForm):
    minor = forms.ChoiceField(label="Type", choices=services.RECOGNITION_MINORS)
    hide_deleted = forms.BooleanField(label="Hide people deleted from the library", required=False)

    @classmethod
    def defaults(cls) -> dict:
        return {**cls.default_range(), "minor": services.MATCHED, "hide_deleted": "on"}


class CaptureFilterForm(_RangeForm):
    target_type = forms.ChoiceField(label="Target type", choices=services.CAPTURE_TARGETS)

    @classmethod
    def defaults(cls) -> dict:
        return {**cls.default_range(), "target_type": "all"}


class LogFilterForm(_RangeForm):
    @classmethod
    def defaults(cls) -> dict:
        return cls.default_range(days=7)  # logs are sparse, so look back further than for alarms
