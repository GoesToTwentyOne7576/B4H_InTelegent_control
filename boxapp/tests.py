import threading

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

import mock_box
from boxapp.box import box

# 2026-09-27..2026-09-28 around the mock's timestamps (the mock ignores the range; this just has to parse)
RANGE = "start=2026-09-01T00:00:00&end=2026-10-30T00:00:00"
BOB_PHOTO = "faceX"


class BoxPagesTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.srv = mock_box.serve(0)  # port 0 = any free port
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        box.__init__(f"http://127.0.0.1:{cls.port}", "admin", "pw")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        super().tearDownClass()

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("root", "r@example.com", "pw12345!")
        self.client.force_login(self.admin)

    def get(self, name, qs=""):
        return self.client.get(f"/admin/boxapp/{name}/?{qs}")

    def test_sidebar_lists_pages(self):
        html = self.client.get("/admin/").content.decode()
        for label in ("Recognition", "Captures", "People", "Devices", "Logs", "Algorithms"):
            self.assertIn(label, html)

    def test_recognition_hides_deleted_people_and_paginates(self):
        r = self.get("recognitionrecord", RANGE + "&minor=face_comparison_successful&hide_deleted=on&size=10")
        html = r.content.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn("Alice", html)
        self.assertIn("Carol", html)
        self.assertNotIn("<strong>Bob</strong>", html)
        self.assertIn("<strong>30</strong> records", html)  # 45 records, 15 of them Bob's -> 30 left
        self.assertIn("Page 1 of 3", html)
        self.assertIn("/admin/box-image/?uri=", html)
        html2 = self.get("recognitionrecord", RANGE + "&minor=face_comparison_successful&hide_deleted=on&size=10&page=3").content.decode()
        self.assertIn("Page 3 of 3", html2)

    def test_recognition_show_deleted(self):
        html = self.get("recognitionrecord", RANGE + "&minor=face_comparison_successful&size=30").content.decode()  # checkbox unchecked
        self.assertIn("<strong>Bob</strong>", html)
        self.assertIn("<strong>45</strong> records", html)

    def test_recognition_strangers(self):
        html = self.get("recognitionrecord", RANGE + "&minor=stranger&size=10").content.decode()
        self.assertIn("<strong>5</strong> records", html)

    def test_recognition_default_filter_renders_form(self):
        r = self.get("recognitionrecord")
        self.assertEqual(r.status_code, 200)
        self.assertIn('type="datetime-local"', r.content.decode())

    def test_bad_range_shows_form_error(self):
        html = self.get("recognitionrecord", "start=2026-10-30T00:00:00&end=2026-09-01T00:00:00&size=10&minor=stranger").content.decode()
        self.assertIn("must be before", html)

    def test_captures(self):
        html = self.get("capturerecord", RANGE + "&target_type=all&size=30").content.decode()
        self.assertIn("<strong>20</strong> records", html)
        self.assertIn("Front Door", html)
        self.assertIn("Wear glasses: ", html)
        self.assertNotIn("link_info", html)
        face = self.get("capturerecord", RANGE + "&target_type=face&size=10").content.decode()
        self.assertIn("<strong>12</strong> records", face)
        body = self.get("capturerecord", RANGE + "&target_type=body&size=10").content.decode()
        self.assertIn("<strong>8</strong> records", body)

    def test_people_and_devices(self):
        p = self.get("person").content.decode()
        self.assertIn("Alice", p)
        self.assertNotIn("Bob", p)
        d = self.get("device").content.decode()
        self.assertIn("Lobby", d)
        self.assertNotIn("secret", d)  # RTSP passwords never leave the box client

    def test_logs(self):
        html = self.get("logview", RANGE + "&size=10").content.decode()
        self.assertIn("<strong>23</strong> records", html)
        self.assertIn("Page 1 of 3", html)
        self.assertIn("Person added", html)
        self.assertIn("Person deleted", html)  # the box logs a deletion as "modify_personnel_data"
        self.assertIn("Failed login attempts", html)
        self.assertIn("box-badge security", html)
        html3 = self.get("logview", RANGE + "&size=10&page=3").content.decode()
        self.assertIn("Page 3 of 3", html3)
        self.assertIn("Download full log", html)

    def test_logs_default_filter_renders_form(self):
        r = self.get("logview")
        self.assertEqual(r.status_code, 200)
        self.assertIn("<strong>", r.content.decode())  # default range is applied, so records are listed

    def test_log_download_and_permission(self):
        r = self.client.get("/admin/box-log/download/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment; filename=\"b4h-log-", r["Content-Disposition"])
        self.assertEqual(r.content, b"mock box log file")
        User = get_user_model()
        staff = User.objects.create_user("guard", password="pw12345!", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/admin/box-log/download/").status_code, 403)
        self.assertEqual(self.get("logview").status_code, 403)
        from django.contrib.auth.models import Permission
        staff.user_permissions.add(Permission.objects.get(codename="view_logview"))
        self.client.force_login(User.objects.get(pk=staff.pk))
        self.assertEqual(self.get("logview").status_code, 200)
        self.assertEqual(self.client.get("/admin/box-log/download/").status_code, 200)

    def test_algorithms(self):
        html = self.get("algorithmpackage").content.decode()
        self.assertIn("<strong>2</strong> algorithm packages", html)
        self.assertIn("Face-human &amp; Recognition", html)
        self.assertIn("200 MB", html)
        self.assertIn("increase population statistics", html)

    def test_image_proxy(self):
        r = self.client.get("/admin/box-image/?uri=./record_CHN0/face1.jpg")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/jpeg")  # box says octet-stream, we guess from the name
        self.assertEqual(self.client.get("/admin/box-image/?uri=http://evil/x").status_code, 400)
        self.assertEqual(self.client.get("/admin/box-image/?uri=../../etc/passwd").status_code, 400)
        self.assertEqual(self.client.get("/admin/box-image/?uri=./nope/x.jpg").status_code, 404)

    def test_permissions(self):
        self.client.logout()
        self.assertEqual(self.get("recognitionrecord").status_code, 302)  # -> admin login
        User = get_user_model()
        staff = User.objects.create_user("guard", password="pw12345!", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.get("recognitionrecord").status_code, 403)
        from django.contrib.auth.models import Permission
        staff.user_permissions.add(Permission.objects.get(codename="view_recognitionrecord"))
        staff = User.objects.get(pk=staff.pk)
        self.client.force_login(staff)
        self.assertEqual(self.get("recognitionrecord", RANGE + "&minor=stranger&size=10").status_code, 200)
        self.assertEqual(self.get("capturerecord").status_code, 403)

    @override_settings()
    def test_box_offline_shows_friendly_error(self):
        good = box._http.base_url
        import httpx
        box._http.base_url = httpx.URL("http://127.0.0.1:1")
        box.session_id = None
        try:
            r = self.get("recognitionrecord", RANGE + "&minor=stranger&size=10")
            self.assertEqual(r.status_code, 200)
            self.assertIn("unreachable", r.content.decode())
        finally:
            box._http.base_url = good
