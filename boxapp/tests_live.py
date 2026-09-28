import os
import tempfile
import threading
import unittest

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

import mock_box
from boxapp import services
from boxapp.box import box

try:
    import cv2
    import numpy as np
except ImportError:  # opencv not installed -> live tests are skipped
    cv2 = None


class SubstreamTest(TestCase):
    def test_to_substream(self):
        self.assertEqual(services.to_substream("rtsp://u:p@10.0.0.5:554/ISAPI/Streaming/channels/201"),
                         "rtsp://u:p@10.0.0.5:554/ISAPI/Streaming/channels/202")
        self.assertEqual(services.to_substream("rtsp://h/x/Channels/101"), "rtsp://h/x/Channels/102")
        self.assertEqual(services.to_substream("rtsp://h/other/path"), "rtsp://h/other/path")


@unittest.skipIf(cv2 is None, "opencv-python-headless not installed")
class LiveTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.video = os.path.join(cls.tmp.name, "cam.mp4")
        vw = cv2.VideoWriter(cls.video, cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 360))
        for i in range(60):
            f = np.zeros((360, 640, 3), np.uint8)
            cv2.rectangle(f, (10 + i * 8, 100), (110 + i * 8, 200), (0, 255, 0), -1)
            vw.write(f)
        vw.release()
        mock_box.DEVICES[0]["rtsp_param"]["url"] = cls.video   # a file stands in for the camera
        cls.srv = mock_box.serve(0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        box.__init__(f"http://127.0.0.1:{cls.srv.server_address[1]}", "a", "b")

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.tmp.cleanup()
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        self.client.force_login(get_user_model().objects.create_superuser("r", "r@x.com", "pw12345!"))

    def test_page_lists_cameras_and_leaks_nothing(self):
        html = self.client.get("/admin/boxapp/liveview/").content.decode()
        self.assertIn("/admin/live/1/stream/", html)           # box gave device 1 an RTSP URL -> <img>
        self.assertIn("has no RTSP URL", html)                 # device 2 has none
        self.assertNotIn("secret", html)                       # camera password never reaches the browser
        self.assertNotIn("rtsp://", html)

    def test_snapshot_and_stream(self):
        r = self.client.get("/admin/live/1/snapshot/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.content.startswith(b"\xff\xd8"))     # JPEG magic bytes
        s = self.client.get("/admin/live/1/stream/")
        self.assertIn("multipart/x-mixed-replace", s["Content-Type"])
        chunk = next(iter(s.streaming_content))
        self.assertTrue(chunk.startswith(b"--frame"))
        s.close()

    def test_unknown_camera_and_permissions(self):
        self.assertEqual(self.client.get("/admin/live/2/stream/").status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get("/admin/live/1/stream/").status_code, 302)
        staff = get_user_model().objects.create_user("g", password="pw12345!", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/admin/live/1/stream/").status_code, 403)
