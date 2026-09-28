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
