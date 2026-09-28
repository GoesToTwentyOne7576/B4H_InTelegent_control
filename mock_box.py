"""
A tiny fake B4H box for offline development and tests.

    python mock_box.py            # listens on http://127.0.0.1:9001
    B4H_BASE_URL=http://127.0.0.1:9001 python manage.py runserver

Library has Alice + Carol. Bob appears in the recognition history but was "deleted" from the library.
"""
import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)
BASE_MS = 1_790_000_000_000
LIBRARY = [("p1", "Alice"), ("p3", "Carol")]
HISTORY_PEOPLE = [("p1", "Alice"), ("p2", "Bob"), ("p3", "Carol")]
DEVICES = [
    {"device_id": 1, "device_name": "Front Door", "proto": "rtsp",
     "rtsp_param": {"user": "u", "password": "secret", "url": "rtsp://u:secret@127.0.0.1:554/ISAPI/Streaming/channels/201"}},
    {"device_id": 2, "device_name": "Lobby", "proto": "rtsp"},  # no rtsp_param
]


def _img(name):
    return {"image_data_format": 2, "value": f"./record_CHN0/{name}.jpg"}


def matched(i):
    pid, name = HISTORY_PEOPLE[i % 3]
    return {
        "additional": {"alarm_id": 1000 + i, "device_id": 1 + i % 2, "alarm_minor": "face_comparison_successful"},
        "global_info": {"time_ms": str(BASE_MS + i * 60_000)},
        "faces": [{"image_data": _img(f"face{i}"),
                   "recognition_info": [{"person_id": pid, "person_name": name, "face_score": 0.80 + (i % 10) / 100,
                                         "group_name": "Staff", "image_data": _img(f"base{pid}")}]}],
        "full_images": [{"image_data": _img(f"pano{i}")}],
    }


def stranger(i):
    return {
        "additional": {"alarm_id": 2000 + i, "device_id": 1, "alarm_minor": "stranger"},
        "global_info": {"time_ms": str(BASE_MS + i * 60_000)},
        "faces": [{"image_data": _img(f"sface{i}")}],
        "full_images": [{"image_data": _img(f"spano{i}")}],
    }


def capture(i, minor):
    key = "faces" if minor == "face_capture" else "pedestrians"
    return {
        "additional": {"alarm_id": 3000 + i, "device_id": 1 + i % 2, "alarm_minor": minor},
        "global_info": {"time_ms": str(BASE_MS + i * 30_000)},
        key: [{"track_id": f"trk{i}", "image_data": _img(f"cap{i}"), "gender": 1 + i % 2, "wear_glasses": i % 2,
               "link_info": {"x": 1}}],
        "full_images": [{"image_data": _img(f"cpano{i}")}] if i % 3 else [{"image_data": {"value": ""}}],
    }


DATASETS = {
    "face_comparison_successful": [matched(i) for i in range(45)],
    "stranger": [stranger(i) for i in range(5)],
    "face_capture": [capture(i, "face_capture") for i in range(12)],
    "body_capture": [capture(100 + i, "body_capture") for i in range(8)],
}


def _log(i):
    """23 log entries, newest first (log_sequence 36 down to 14); every 5th is a brute-force login."""
    security = i % 5 == 4
    delete = i % 3 == 1
    return {
        "log_content": "violent_login" if security else "modify_personnel_data" if delete else "build_personnel_data",
        "log_datetime": BASE_MS // 1000 + 600_000 - i * 300,
        "log_detail_content": "192.168.90.241" if security else "Delete person" if delete else "Person name:Tanzia",
        "log_ip": "192.168.90.122",
        "log_sequence": 36 - i,
        "major_type": "operation",
        "minor_type": "security_manager" if security else "data_operation",
        "user_name": "192.168.90.122",
    }


LOGS = [_log(i) for i in range(23)]
ALGORITHMS = [
    {"alg_name": "mc40_face_pkg_V1", "alg_version": "V1.2.1", "alg_warehouse_serial": "Face-human & Recognition",
     "alg_warehouse_type": "face", "alg_description": "face detect", "chip_type": "MC_40", "manufacturer": "ks",
     "file_id": 1, "size": 209715200, "status": "install", "using": True,
     "operation_info": {"result": "success", "stage": 4}, "version_update_description": "increase population statistics"},
    {"alg_name": "mc40_tywb_pkg_V1", "alg_version": "V1.0.0", "alg_warehouse_serial": "General False Alarm Package",
     "alg_warehouse_type": "tywb_alarm", "alg_description": "extract any feature", "chip_type": "MC_40",
     "manufacturer": "ks", "file_id": 35, "size": 209715200, "status": "install", "using": False,
     "operation_info": {"result": "success", "stage": 4}, "version_update_description": ""},
]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/auth/login/challenge":
            return self._json({"code": 0, "data": {"session_id": "sess1", "salt": "s", "challenge": "c"}})
        if u.path.startswith("/web/record_CHN0/"):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")  # like the real box
            self.send_header("Content-Length", str(len(PNG)))
            self.end_headers()
            return self.wfile.write(PNG)
        if u.path == "/device_maintenance/logFile":
            body = b"mock box log file"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(n) or b"{}")
        if u.path == "/auth/login":
            return self._json({"code": 0, "data": {"session_id": "sess1"}})
        if u.path == "/device_access/device_config":
            return self._json({"code": 0, "data": DEVICES})
        if u.path == "/face_manager/person/query":
            off, size = req.get("offset", 0), req.get("size", 30)
            people = [{"person_id": p, "person_info": {"name": nm}} for p, nm in LIBRARY]
            return self._json({"code": 0, "data": {"total_count": len(people), "person_list": people[off:off + size]}})
        if u.path == "/device_alarm/alarm_history":
            q = req["query_condition"]["alarm_type"][0]["minor_type"]
            records = [r for m in q for r in DATASETS.get(m, [])]
            off, size = req.get("offset", 0), req.get("size", 10)
            if size > 30:
                return self._json({"code": 1073741825, "message": "general"})
            page = records[off:off + size]
            return self._json({"code": 0, "data": {"total_count": len(records), "return_count": len(page), "list": page}})
        if u.path == "/intelli_manager/alg_warehouse/packet_list":
            return self._json({"code": 0, "data": {"list": ALGORITHMS, "total_num": len(ALGORITHMS)}})
        if u.path == "/device_maintenance/log":
            cond = req.get("query_condition") or {}
            if not (isinstance(req.get("offset"), int) and isinstance(req.get("size"), int)
                    and isinstance(cond.get("start_time"), str) and isinstance(cond.get("end_time"), str)):
                return self._json({"code": 1073741826, "message": "invalid_param"})  # strict, like the real box
            off, size = req["offset"], req["size"]
            if size > 30:
                return self._json({"code": 1073741825, "message": "general"})
            page = LOGS[off:off + size]
            return self._json({"code": 0, "data": {"current_count": len(page), "logs_data": page, "total_count": len(LOGS)}})
        self._json({"code": 404, "message": "unknown"})


def serve(port=9001):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Mock B4H box on http://127.0.0.1:{port}")
    return srv


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 9001).serve_forever()
