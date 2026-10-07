<<<<<<< Updated upstream
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


# B4H Portal

A Django admin portal for the MegCube B4H box. It reads recognition, capture, people, device, log and algorithm data live from the box, shows live camera video, and runs a portal-side movement alarm on RTSP streams.

The local database (SQLite) holds only Django users and sessions, plus movement alarm rules and events. All camera data is read from the box on demand.

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Create a `.env` file in the project root:

| Variable | Default | Purpose |
|---|---|---|
| `B4H_BASE_URL` | `https://192.168.90.200` | Box address |
| `B4H_USER` / `B4H_PASS` | `admin` / empty | Box login |
| `DJANGO_SECRET_KEY` | dev key | Change in production |
| `DJANGO_DEBUG` | `1` | Set `0` in production |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated |
| `TIME_ZONE` | `Asia/Dhaka` | Display time zone |
| `RECOG_MAJOR` | `face_basic_business` | Alarm major type |
| `LIVE_SUBSTREAM` | `0` | `1` = use RTSP sub stream (`/channels/NN02`) |
| `B4H_LOG_BODY` | built in | JSON body for the box log query |
| `B4H_LOG_PATH` / `B4H_LOG_FILE_PATH` | `/device_maintenance/log` / `/device_maintenance/logFile` | Log endpoints |
| `B4H_ALG_PATH` / `B4H_ALG_BODY` | `/intelli_manager/alg_warehouse/packet_list` / `{"offset":0,"size":100}` | Algorithm list |

No box available? Run the fake box: `python mock_box.py`, then start the server with `B4H_BASE_URL=http://127.0.0.1:9001`.

Production (Windows, single process with threads): `waitress-serve --threads=4 config.wsgi:application`. Run one process only, because camera streams and alarm workers live in process memory.

## Project layout

| File | Role |
|---|---|
| `config/urls.py` | Routes (all wrapped in `admin.site.admin_view`, staff only) |
| `boxapp/b4h.py` | Box client: login, session retry, locking |
| `boxapp/box.py` | One shared client per process |
| `boxapp/services.py` | Builds box requests, pagination, filtering |
| `boxapp/mapping.py` | Turns raw box records into table rows |
| `boxapp/admin.py`, `forms.py`, `templates/` | Admin pages and filter forms |
| `boxapp/views.py` | Image proxy, live video, log download, movement alarm routes |
| `boxapp/streams.py` | RTSP to MJPEG (OpenCV, one thread per camera) |
| `boxapp/movement_alarm.py` | Motion detection workers |
| `boxapp/models.py` | Page permission models and alarm rule/event tables |
| `mock_box.py` | Fake box for offline development |

## Workflow

### 1. Startup
1. Django loads `config/settings.py` and `.env`.
2. `boxapp/box.py` creates one shared `B4HClient` (one login lock, one call lock).

### 2. Staff login
1. `/` redirects to `/admin/`.
2. The user logs in with a Django staff account (session cookie and CSRF).
3. The sidebar shows only pages the account has `view_*` permission for: Recognition, Captures, People, Devices, Live view, Logs, Algorithms.

### 3. Box authentication (automatic on the first box call)
1. `GET /auth/login/challenge?username=...` returns `session_id`, `salt`, `challenge`.
2. Password hash = `sha256(password + salt + challenge)`.
3. `POST /auth/login` with `{session_id, username, password: hash}`.
4. Every later request sends `Cookie: sessionID=...`.
5. Code 512 (idle session dropped after about 30 s): log in again and retry once.
6. Requests go one at a time, because the box rejects parallel queries.

> Five wrong passwords in a row lock the box account. Check `B4H_PASS` first if login fails.

### 4. Data pages (Recognition, Captures, People, Devices, Logs, Algorithms)
1. The user sets filters and submits (GET, filters in the URL).
2. The form is validated and `services.py` builds the box request: times in milliseconds (seconds for logs), `offset = (page - 1) * size`, size at most 30.
3. `box.call()` returns `data`, or raises `B4HError`, which the page shows as a message.
4. Recognition with "hide deleted" on: fetch the face library, pull up to 5000 matched alarms, drop people no longer in the library, then paginate locally.
5. `mapping.py` converts raw records to rows.
6. Thumbnails load through `/admin/box-image/?uri=...` so the browser never needs the box cookie.

### 5. Live view
1. The page lists cameras from `device_config` and renders one `<img src="/admin/live/<id>/stream/">` per camera.
2. The RTSP URL (which contains the camera password) is looked up server-side and never sent to the browser. It is cached for 5 minutes.
3. A background thread reads RTSP over TCP with OpenCV, downscales to 960 px, encodes JPEG quality 70.
4. All viewers of a camera share that thread. The browser receives MJPEG.
5. The thread stops 10 seconds after the last viewer leaves.

### 6. Movement alarm
1. Open `/admin/movement-alarm/`, pick a camera, enter 3 or more zone points and the thresholds.
2. The page POSTs JSON to `/admin/movement-alarm/create/`. The rule is saved and a worker thread starts.
3. The worker runs MOG2 background subtraction on the RTSP stream, masked to the polygon.
4. `score = moving pixels / zone pixels`. If `score >= sensitivity` for `trigger_frames` frames in a row and the cooldown has passed, a `MovementAlarmEvent` is saved.
5. Events are listed on the page and acknowledged there. Toggle and delete start or stop the worker.

### 7. Errors
- Box unreachable: page shows "B4H box unreachable", check `B4H_BASE_URL`.
- Box error: page shows endpoint, message and code.
- Camera silent: snapshot returns 504, stream ends after about 15 s.

## Portal routes

All routes require staff login.

| Route | Method | Params | Returns |
|---|---|---|---|
| `/admin/boxapp/recognitionrecord/` | GET | `start`, `end`, `minor` (`face_comparison_successful` or `stranger`), `size` (10/20/30), `page`, `hide_deleted` | HTML table |
| `/admin/boxapp/capturerecord/` | GET | `start`, `end`, `target_type` (`all`/`face`/`body`), `size`, `page` | HTML table |
| `/admin/boxapp/person/` | GET | `q` (name or id) | HTML list |
| `/admin/boxapp/device/` | GET | none | HTML list |
| `/admin/boxapp/liveview/` | GET | `cols` (1 to 4) | HTML camera grid |
| `/admin/boxapp/logview/` | GET | `start`, `end`, `size`, `page` | HTML table |
| `/admin/boxapp/algorithmpackage/` | GET | none | HTML table |
| `/admin/box-image/` | GET | `uri` | Image bytes (cached 1 day) |
| `/admin/live/<id>/stream/` | GET | `device_id` | MJPEG (`multipart/x-mixed-replace`) |
| `/admin/live/<id>/snapshot/` | GET | `device_id` | One JPEG, 504 if no frame |
| `/admin/box-log/download/` | GET | none | Log file attachment |
| `/admin/movement-alarm/` | GET | none | HTML: rules, last 100 events |
| `/admin/movement-alarm/create/` | POST | JSON below, header `X-CSRFToken` | `{ok, id}` or 400 `{error}` |
| `/admin/movement-alarm/<rule_id>/toggle/` | POST | none | Redirect |
| `/admin/movement-alarm/<rule_id>/delete/` | POST | none | Redirect |
| `/admin/movement-alarm/event/<id>/ack/` | POST | none | Redirect |

Date and time filters use `YYYY-MM-DDTHH:MM:SS`. Defaults are the last 24 hours (logs: 7 days).

Create rule body:

```json
{
  "name": "Back door",
  "device_id": 1,
  "zone_points": [[100, 100], [500, 100], [500, 400], [100, 400]],
  "sensitivity": 0.015,
  "trigger_frames": 3,
  "cooldown_seconds": 30,
  "alarm_duration_seconds": 10
}
```

`zone_points` are pixel coordinates on the frame as scaled to 960 px wide.

## B4H box API used

Every JSON reply has the form `{"code": 0, "message": "...", "data": ...}`. Code 0 means success.

| Method and path | Request | Response data |
|---|---|---|
| `GET /auth/login/challenge` | `?username=` | `session_id`, `salt`, `challenge` |
| `POST /auth/login` | `{session_id, username, password}` | `session_id` |
| `POST /device_access/device_config` | `{offset: 0, size: 100}` | List of `{device_id, device_name, rtsp_param.url}` |
| `POST /face_manager/person/query` | `{offset, size <= 30, get_feature: false}` | `{person_list[{person_id, person_info.name}], total_count}` |
| `POST /device_alarm/alarm_history` | `{offset, size, query_condition: {start_time, end_time, alarm_type: [...]}}` | `{list, total_count}` |
| `GET /web/<uri>` or `/device_storage/get_image?image_uri=` | image uri | JPEG bytes |
| `POST /device_maintenance/log` | `{offset, size, query_condition: {start_time, end_time}}` | `{logs_data, total_count}` |
| `GET /device_maintenance/logFile` | none | Log file |
| `POST /intelli_manager/alg_warehouse/packet_list` | `{offset: 0, size: 100}` | `{list}` |

Notes on `alarm_history`:
- `start_time` and `end_time` are epoch milliseconds as strings.
- Recognition uses `{major_type: "face_basic_business", minor_type: ["face_comparison_successful"]}` or `["stranger"]`. Other minor types can crash the box web server, so only use ones listed by `GET /device_alarm/alarm_cap`.
- Captures use `face_capture` and/or `body_capture`, plus a second entry `{major_type: "structure", minor_type: ["face", "pedestrian", "vehicle", "non_motor", "plate"]}`. Without it the box returns code 1073741831 (`not_support`).
- Log times are in seconds.

## Known limits

- Run a single server process. Streams and alarm workers are in-memory.
- Alarm workers are started when a rule is created or toggled. `MovementAlarmManager.sync()` exists but is not called at startup, so enabled rules do not resume after a restart until toggled.
- Movement detection sees motion only. It does not identify people or vehicles.
- The box connection uses `verify=False` (self-signed certificate). Use it only on a trusted network.

=======
##Test
>>>>>>> Stashed changes
