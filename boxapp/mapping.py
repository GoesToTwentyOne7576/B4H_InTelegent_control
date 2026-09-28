"""
Turns the box's raw alarm records into simple rows for the tables.
Ported from the Next.js app (client/src/lib/recognition.ts and captures.ts): the box's
field names vary, so values are looked up by several possible keys.
"""
import json
import math
from collections import deque
from datetime import datetime
from typing import Any
from urllib.parse import quote

from django.urls import reverse
from django.utils import timezone

MISSING = "—"


# ---------- small helpers for unknown JSON ----------

def _empty(v: Any) -> bool:
    return v is None or v == "" or (isinstance(v, list) and not v)


def find(obj: Any, keys: list[str]) -> Any:
    """First non-empty value found under any of `keys`, searching nested objects/arrays breadth-first."""
    queue = deque([obj])
    while queue:
        cur = queue.popleft()
        if isinstance(cur, list):
            queue.extend(cur)
        elif isinstance(cur, dict):
            for k in keys:
                v = cur.get(k)
                if not _empty(v):
                    return v
            queue.extend(v for v in cur.values() if isinstance(v, (dict, list)))
    return None


def find_all(obj: Any, keys: list[str]) -> list[Any]:
    """Every value found under any of `keys` (e.g. all group names)."""
    out: list[Any] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            for k, v in node.items():
                if k in keys and v is not None and v != "":
                    out.extend(v if isinstance(v, list) else [v])
                elif isinstance(v, (dict, list)):
                    walk(v)

    walk(obj)
    return out


def find_list(resp: Any) -> list[Any]:
    """The array of records inside a box response."""
    if isinstance(resp, list):
        return resp
    v = find(resp, ["alarm_list", "person_list", "list", "records", "items", "data"])
    return v if isinstance(v, list) else []


def collect_images(obj: Any) -> list[tuple[str, str]]:
    """All image URIs in a record, in order, with any type label next to them."""
    out: list[tuple[str, str]] = []

    def first_present(o: dict, keys: list[str]) -> Any:
        for k in keys:
            if o.get(k) is not None:
                return o[k]
        return None

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            uri = first_present(node, ["image_uri", "uri", "url", "image_url"])
            if uri is None and str(node.get("image_data_format")) == "2":
                uri = node.get("image_data")
            if isinstance(uri, str) and uri:
                label = first_present(node, ["image_type", "type", "pic_type"])
                out.append((uri, str(label if label is not None else "").lower()))
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)

    walk(obj)
    return out


def image_path(v: Any) -> str | None:
    """Image path inside an `image_data` object: {image_data_format: 2, value: "./record_CHN0/...jpg"}."""
    if isinstance(v, dict) and isinstance(v.get("value"), str) and v["value"]:
        return v["value"]
    return None


def image_url(uri: str | None) -> str | None:
    if not uri:
        return None
    if uri.startswith(("http", "data:")):
        return uri
    return f"{reverse('box_image')}?uri={quote(uri, safe='')}"


def score(v: Any) -> str:
    if v is None:
        return MISSING
    try:
        n = float(v)
    except (TypeError, ValueError):
        return MISSING
    if math.isnan(n):
        return MISSING
    return f"{(n * 100 if 0 < n <= 1 else n):.1f}"  # 0.79 -> 79.0


def format_time(v: Any) -> str:
    try:
        ms = float(v)
    except (TypeError, ValueError):
        return MISSING
    if not ms:
        return MISSING
    if ms < 1e12:
        ms *= 1000  # seconds -> ms
    dt = datetime.fromtimestamp(ms / 1000, tz=timezone.get_current_timezone())
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def humanize_key(key: str) -> str:
    """"wear_glasses" -> "Wear glasses". Values stay raw codes: we don't have the box's enum legend."""
    s = key.replace("_", " ")
    return s[:1].upper() + s[1:]


# ---------- recognition ----------

def to_recognition_row(rec: dict, index: int) -> dict:
    # Box layout: faces[0].image_data = face crop, faces[0].recognition_info[0].image_data = library photo,
    # full_images[0].image_data = panorama.
    faces = rec.get("faces") or []
    face0 = faces[0] if faces else None
    infos = (face0 or {}).get("recognition_info") or []
    match0 = infos[0] if infos else None
    fulls = rec.get("full_images") or []
    full0 = fulls[0] if fulls else None

    known_face = image_path((face0 or {}).get("image_data"))
    known_base = image_path((match0 or {}).get("image_data"))
    known_pano = image_path((full0 or {}).get("image_data"))

    images = collect_images(rec)

    def by_type(words: list[str]) -> str | None:
        for uri, typ in images:
            if any(w in typ for w in words):
                return uri
        return None

    face = known_face or by_type(["face", "crop", "snap", "target"])
    panorama = known_pano or by_type(["panor", "background", "scene", "full", "bg"])
    base = known_base or by_type(["base", "library", "register", "person", "db"])
    rest = [u for u, _ in images if u not in (face, panorama, base)]

    groups = [str(g) for g in find_all(rec, ["group_name", "group_names"])]
    time_value = find(rec, ["time_ms", "capture_time", "alarm_time", "timestamp", "time"])

    person_id = find(match0, ["person_id"]) if match0 else None
    if person_id is None:
        person_id = find(rec, ["person_id"])

    def pop_rest() -> str | None:
        return rest.pop(0) if rest else None

    # unlabelled images: assume order face, panorama, base
    face_img = image_url(face or pop_rest())
    pano_img = image_url(panorama or pop_rest())
    base_img = image_url(base or pop_rest())

    return {
        "id": str(find(rec, ["data_uuid", "alarm_id", "record_id", "uuid", "id"]) or f"{index}-{time_value}"),
        "time": format_time(time_value),
        "device_id": str(find(rec, ["device_id", "channel_id"]) or ""),
        "device": str(find(rec, ["device_name", "channel_name", "camera_name", "source_name"]) or MISSING),
        "living": score(find(rec, ["liveness_score", "living_score", "liveness", "live_score", "living_fraction"])),
        "person_id": str(person_id if person_id is not None else ""),
        "name": str(find(rec, ["person_name", "name"]) or MISSING),
        "groups": ", ".join(dict.fromkeys(groups)) if groups else MISSING,
        "similarity": score(find(rec, ["face_score", "similarity", "score", "compare_score", "match_score"])),
        "face_img": face_img,
        "panorama_img": pano_img,
        "base_img": base_img,
        "raw_json": json.dumps(rec, indent=2, ensure_ascii=False, default=str),
    }


# ---------- capture ----------

_DETAIL_NOISE = {"image_data", "link_info", "alarm_linkage", "track_id", "track_id_times"}


def normalize_capture(alarm: dict) -> dict:
    """Flatten one box alarm record (face_capture or body_capture) into one row."""
    additional = alarm.get("additional") or {}
    global_info = alarm.get("global_info") or {}
    minor = additional.get("alarm_minor")  # "face_capture" | "body_capture"

    if minor == "face_capture":
        target_type, targets = "face", alarm.get("faces") or [{}]
    else:
        target_type, targets = "body", alarm.get("pedestrians") or [{}]
    target = targets[0] if targets else {}

    target_image = ((target.get("image_data") or {}).get("value") or "") or None
    full_images = alarm.get("full_images") or [{}]
    panoramic = ((full_images[0].get("image_data") or {}).get("value") or "") or None

    return {
        "alarm_id": additional.get("alarm_id"),
        "track_id": target.get("track_id"),
        "target_type": target_type,
        "device_id": additional.get("device_id"),
        "capture_time_ms": global_info.get("time_ms"),
        "target_image": target_image,
        "panoramic_image": panoramic,
        "attributes": {k: v for k, v in target.items() if k not in _DETAIL_NOISE},
    }


def to_capture_row(raw: dict, device_names: dict[str, str]) -> dict:
    dev_id = str(raw.get("device_id"))
    attrs = raw.get("attributes") or {}
    return {
        "id": str(raw.get("alarm_id")),
        "track_id": raw.get("track_id") or MISSING,
        "target_type": raw.get("target_type"),
        "device": device_names.get(dev_id, f"Device {dev_id}"),
        "time": format_time(raw.get("capture_time_ms")),
        "target_img": image_url(raw.get("target_image")),
        "panoramic_img": image_url(raw.get("panoramic_image")),
        "attributes": [(humanize_key(k), v) for k, v in attrs.items()],
    }


# ---------- logs ----------

_LOG_LABELS = {
    "build_personnel_data": "Person added",
    "modify_personnel_data": "Person modified",
    "violent_login": "Failed login attempts (brute force)",
}
_LOG_CATEGORIES = {
    "data_operation": "Data operation",
    "security_manager": "Security",
}


def to_log_row(rec: dict) -> dict:
    content = rec.get("log_content") or ""
    minor = rec.get("minor_type") or ""
    detail = rec.get("log_detail_content") or ""
    event = _LOG_LABELS.get(content, humanize_key(content) if content else MISSING)
    if content == "modify_personnel_data" and detail == "Delete person":
        event = "Person deleted"  # the box logs a deletion as a "modify"
    return {
        "seq": rec.get("log_sequence"),
        "time": format_time(rec.get("log_datetime")),
        "category": _LOG_CATEGORIES.get(minor, humanize_key(minor) if minor else MISSING),
        "event": event,
        "detail": detail or MISSING,
        "ip": rec.get("log_ip") or MISSING,
        "user": rec.get("user_name") or MISSING,
        "is_security": minor == "security_manager",
    }


# ---------- algorithm packages ----------

def format_size(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return MISSING
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if n == int(n) else f"{n:.1f} {unit}"
        n /= 1024


def to_algorithm_row(rec: dict) -> dict:
    op = rec.get("operation_info") or {}
    return {
        "id": rec.get("file_id"),
        "name": rec.get("alg_warehouse_serial") or rec.get("alg_name") or MISSING,
        "package": rec.get("alg_name") or MISSING,
        "version": rec.get("alg_version") or MISSING,
        "type": rec.get("alg_warehouse_type") or MISSING,
        "chip": rec.get("chip_type") or MISSING,
        "manufacturer": rec.get("manufacturer") or MISSING,
        "description": rec.get("alg_description") or MISSING,
        "update_note": rec.get("version_update_description") or MISSING,
        "size": format_size(rec.get("size")),
        "status": humanize_key(rec["status"]) if rec.get("status") else MISSING,
        "result": humanize_key(op["result"]) if op.get("result") else MISSING,
        "in_use": bool(rec.get("using")),
    }
