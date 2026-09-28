"""
Non-admin-page views. Every route is wrapped in admin.site.admin_view() in config/urls.py (staff login only).
"""
import mimetypes
from datetime import datetime

import httpx
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseBadRequest, StreamingHttpResponse

from . import services
from .b4h import B4HError
from .box import box
from .streams import get_stream


# ---------------------------------------------------------------- image proxy
# The browser can't send the box's session cookie, so Django fetches the image for it.

def box_image(request):
    uri = request.GET.get("uri", "")
    if not uri or "://" in uri or ".." in uri:
        return HttpResponseBadRequest("Bad image uri")
    for path, params in (("/web/" + uri.lstrip("./"), None), ("/device_storage/get_image", {"image_uri": uri})):
        try:
            content, ctype = box.get_bytes(path, params)
        except httpx.HTTPStatusError:
            continue
        except httpx.TransportError:
            return HttpResponse("B4H box unreachable", status=503)
        if ctype == "application/octet-stream":  # the box doesn't label its JPEGs
            ctype = mimetypes.guess_type(uri)[0] or ctype
        resp = HttpResponse(content, content_type=ctype)
        resp["Cache-Control"] = "private, max-age=86400"
        return resp
    raise Http404("Image not found on the box")


# ---------------------------------------------------------------- live video


def _camera(request, device_id: int):
    if not request.user.has_perm("boxapp.view_liveview"):
        raise PermissionDenied
    try:
        url = services.camera_rtsp_url(device_id)
    except (B4HError, httpx.HTTPError) as e:
        raise Http404(f"B4H box not reachable: {e}")
    if not url:
        raise Http404("The box has no RTSP URL for this camera")
    return get_stream(device_id, url)


def live_stream(request, device_id: int):
    """MJPEG stream: works in a plain <img> tag, no JavaScript."""
    stream = _camera(request, device_id)

    def gen():
        for jpeg in stream.frames():
            yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpeg) + jpeg + b"\r\n"

    resp = StreamingHttpResponse(gen(), content_type="multipart/x-mixed-replace; boundary=frame")
    resp["Cache-Control"] = "no-store"
    return resp


def live_snapshot(request, device_id: int):
    jpeg = _camera(request, device_id).snapshot()
    if not jpeg:
        return HttpResponse("Camera not responding", status=504)
    return HttpResponse(jpeg, content_type="image/jpeg")


# ---------------------------------------------------------------- box log file


def log_file_download(request):
    if not request.user.has_perm("boxapp.view_logview"):
        raise PermissionDenied
    try:
        content, ctype = services.log_file()
    except httpx.HTTPStatusError as e:
        return HttpResponse(f"Box answered HTTP {e.response.status_code} for the log file", status=502)
    except (B4HError, httpx.TransportError) as e:
        return HttpResponse(f"B4H box unreachable: {e}", status=503)
    ext = "zip" if "zip" in ctype else "json" if "json" in ctype else "txt"
    resp = HttpResponse(content, content_type=ctype)
    resp["Content-Disposition"] = f'attachment; filename="b4h-log-{datetime.now():%Y%m%d-%H%M%S}.{ext}"'
    return resp














#-------------------------------------------------


from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import MovementAlarmEvent,MovementAlarmRule
from .movement_alarm import MovementAlarmManager
from .services import devices


@staff_member_required
def movement_alarm_page(request):
    if not request.user.has_perm("boxapp.view_movementalarmrule"):
        return JsonResponse({"detail": "Forbidden"}, status=403)

    rules = list(MovementAlarmRule.objects.all())
    events = MovementAlarmEvent.objects.select_related("rule")[:100]

    return render(
        request,
        "admin/boxapp/movement_alarm.html",
        {
            "rules": rules,
            "events": events,
            "devices": devices(),
        },
    )


@staff_member_required
@require_http_methods(["POST"])
def movement_alarm_create(request):
    if not request.user.has_perm("boxapp.add_movementalarmrule"):
        return JsonResponse({"detail": "Forbidden"}, status=403)

    import json

    try:
        payload = json.loads(request.body or "{}")
        name = str(payload["name"]).strip()
        device_id = int(payload["device_id"])
        points = payload["zone_points"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid request"}, status=400)

    if not name or not isinstance(points, list) or len(points) < 3:
        return JsonResponse(
            {"error": "Name and at least 3 zone points are required"},
            status=400,
        )

    rule = MovementAlarmRule.objects.create(
        name=name,
        device_id=device_id,
        zone_points=points,
        sensitivity=float(payload.get("sensitivity", 0.015)),
        trigger_frames=int(payload.get("trigger_frames", 3)),
        cooldown_seconds=int(payload.get("cooldown_seconds", 30)),
        alarm_duration_seconds=int(payload.get("alarm_duration_seconds", 10)),
    )

    MovementAlarmManager.start_rule(rule.id)
    return JsonResponse({"ok": True, "id": rule.id})


@staff_member_required
@require_http_methods(["POST"])
def movement_alarm_toggle(request, rule_id):
    rule = get_object_or_404(MovementAlarmRule, pk=rule_id)

    if not request.user.has_perm("boxapp.change_movementalarmrule"):
        return JsonResponse({"detail": "Forbidden"}, status=403)

    rule.enabled = not rule.enabled
    rule.save(update_fields=["enabled", "updated_at"])

    if rule.enabled:
        MovementAlarmManager.start_rule(rule.id)
    else:
        MovementAlarmManager.stop_rule(rule.id)

    messages.success(
        request,
        f"{rule.name}: {'enabled' if rule.enabled else 'disabled'}",
    )
    return redirect("movement_alarm")


@staff_member_required
@require_http_methods(["POST"])
def movement_alarm_delete(request, rule_id):
    rule = get_object_or_404(MovementAlarmRule, pk=rule_id)

    if not request.user.has_perm("boxapp.delete_movementalarmrule"):
        return JsonResponse({"detail": "Forbidden"}, status=403)

    MovementAlarmManager.stop_rule(rule.id)
    rule.delete()
    messages.success(request, "Movement alarm rule deleted.")
    return redirect("movement_alarm")


@staff_member_required
@require_http_methods(["POST"])
def movement_alarm_ack(request, event_id):
    event = get_object_or_404(MovementAlarmEvent, pk=event_id)

    if not request.user.has_perm("boxapp.change_movementalarmevent"):
        return JsonResponse({"detail": "Forbidden"}, status=403)

    event.acknowledged = True
    event.save(update_fields=["acknowledged"])
    return redirect("movement_alarm")
