# B4H portal: workflow and API flow

Django admin portal that reads everything live from the MegCube B4H box. Arrows show who calls whom; each table lists parameters in and data out.

## 1. Staff user (browser)

Logs in at `/admin/` (Django session cookie + CSRF). Every route below is staff-only and checked against a per-page `view_*` permission.

↓ **HTTP GET / POST** to the portal ↓

## 2a. Portal pages (Django admin changelists)

GET with query-string filters. Time fields are `YYYY-MM-DDTHH:MM:SS` (default last 24 h, logs 7 days). Returns rendered HTML.

| Page URL | Params (in) | Box call | Data out |
| --- | --- | --- | --- |
| `/admin/boxapp/recognitionrecord/` | start, end, minor=`face_comparison_successful`\|`stranger`, size 10/20/30, page, hide_deleted | alarm_history (+ person/query if hide_deleted) | Rows: person, score, time, images |
| `/admin/boxapp/capturerecord/` | start, end, target_type=all\|face\|body, size, page | alarm_history (+ structure type) | Rows: device name, attributes, images |
| `/admin/boxapp/person/` | q (name or id) | person/query | person_id + name list |
| `/admin/boxapp/device/` | none | device_config | device_id + name |
| `/admin/boxapp/liveview/` | cols 1-4 | device_config | Grid of `<img src=live/ID/stream/>` |
| `/admin/boxapp/logview/` | start, end, size, page | device_maintenance/log | Log rows + total |
| `/admin/boxapp/algorithmpackage/` | none | alg_warehouse/packet_list | Package name, version, status |

↓ thumbnails in those pages load through the image proxy ↓

## 2b. Portal helper routes (non-admin views)

| Route | In | Out | Notes |
| --- | --- | --- | --- |
| GET `/admin/box-image/` | uri (no `://` or `..`) | image bytes, cached 1 day | Django adds the box cookie; tries `/web/<uri>` then `get_image`; 404/503 on failure |
| GET `/admin/live/<id>/stream/` | device_id | MJPEG `multipart/x-mixed-replace` | Needs `view_liveview`; works in a plain img tag |
| GET `/admin/live/<id>/snapshot/` | device_id | one JPEG | 504 if camera silent (8 s) |
| GET `/admin/box-log/download/` | none | file attachment (zip/json/txt) | Needs `view_logview` |
| GET `/admin/movement-alarm/` | none | HTML: rules, last 100 events, devices |  |
| POST `/admin/movement-alarm/create/` | JSON: name, device_id, zone_points \[\[x,y\]×3+\], sensitivity 0.015, trigger_frames 3, cooldown_seconds 30, alarm_duration_seconds 10; header X-CSRFToken | `{ok, id}` or 400 `{error}` | Saves rule, starts worker |
| POST `.../<rule_id>/toggle/` and `/delete/` | rule_id | redirect | Start/stop worker |
| POST `.../event/<id>/ack/` | event_id | redirect | Sets acknowledged |

↓ services.py builds the request, `box.call()` sends it ↓

## 3. B4HClient (one shared connection, thread lock)

1. GET `/auth/login/challenge?username=` returns session_id, salt, challenge
2. POST `/auth/login` with `{session_id, username, password = sha256(pwd+salt+challenge)}`
3. Every call sends `Cookie: sessionID=...`

1. Reply envelope: `{code, message, data}`; code 0 returns data
2. Code 512 (session dropped, \~30 s idle): login again and retry once
3. One request at a time (box rejects parallel queries); other codes raise B4HError, shown as a page error

↓ HTTPS JSON (`B4H_BASE_URL`, TLS verify off) ↓

## 4. B4H box WebAPI

Max 30 records per request. Timestamps: alarms in ms, logs in seconds, both as strings.

| Method + path | Request body / params | Response data |
| --- | --- | --- |
| POST `/device_access/device_config` | {offset:0, size:100} | list of {device_id, device_name, rtsp_param.url} |
| POST `/face_manager/person/query` | {offset, size≤30, get_feature:false} | {person_list\[{person_id, person_info.name}\], total_count} |
| POST `/device_alarm/alarm_history` | {offset, size, query_condition:{start_time, end_time, alarm_type:\[{major_type:"face_basic_business", minor_type:\[...\]}\]}}. Captures add {major_type:"structure", minor_type:\[face, pedestrian, vehicle, non_motor, plate\]} | {list or alarm_list, total_count}: additional, global_info.time_ms, faces/pedestrians, full_images, recognition_info |
| GET `/web/<uri>` or `/device_storage/get_image?image_uri=` | image uri from a record | raw JPEG (content-type often unlabeled) |
| POST `/device_maintenance/log` | {offset, size, query_condition:{start_time, end_time}} (configurable via B4H_LOG_BODY) | {logs_data\[\], total_count} |
| GET `/device_maintenance/logFile` | none | full log file |
| POST `/intelli_manager/alg_warehouse/packet_list` | {offset:0, size:100} | {list\[\]} algorithm packages |

device_config also supplies each camera's RTSP URL (cached 5 min, server-side only, never sent to the browser) ↓

## 5a. Live video pipeline

1. Camera/NVR RTSP over TCP (`/channels/201`, or 202 sub-stream if LIVE_SUBSTREAM=1)
2. One OpenCV thread per camera: decode, downscale to 960 px, JPEG quality 70
3. Latest frame shared by all viewers; thread stops after 10 s with no viewer
4. stream/ yields `--frame` parts; snapshot/ returns one frame

## 5b. Movement alarm pipeline

1. One worker thread per enabled rule, same RTSP URL
2. MOG2 background subtraction, masked to the zone polygon
3. score = moving pixels / zone pixels; moving if score ≥ sensitivity
4. After trigger_frames in a row and outside cooldown, save a MovementAlarmEvent (SQLite); user acknowledges it from the page
