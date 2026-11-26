import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

WORKER = Path(__file__).resolve().parents[1] / "worker" / "IATraductora.py"
import importlib.util
SPEC = importlib.util.spec_from_file_location("ia_rgss3_http_worker", WORKER)
IA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IA)


class FakeNeural:
    def translate(self, lang, text):
        return "Buenos días." if lang == "ja" else "Good morning."


class RGSS3HttpIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "Game.exe").write_bytes(b"MZ-fixture")
        (self.root / "Game.ini").write_text(
            "[Game]\nLibrary=RGSS301.dll\n", encoding="utf-8"
        )
        (self.root / "Game.rgss3a").write_bytes(
            b"RGSSAD\x00\x03" + b"synthetic-archive"
        )
        self.engine = self.root / "IA Traductora" / ".local" / "Rpg" / "engine"
        self.engine.mkdir(parents=True)
        self.service = IA.Service(self.root, self.engine, neural=FakeNeural())
        self.addCleanup(self.service.close)
        self.server = IA.ThreadingHTTPServer(
            ("127.0.0.1", 0), IA.make_handler(self.service)
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.thread.join, 2)

    def request(self, path, body=None, token=None):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        headers = {
            "X-IA-Token": self.service.token if token is None else token,
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = Request(
            "http://127.0.0.1:%d%s" % (self.server.server_port, path),
            data=data,
            headers=headers,
            method="POST" if data is not None else "GET",
        )
        with urlopen(req, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_rgss3_worker_accepts_authenticated_v95_batch(self):
        status, payload = self.request(
            "/translate_batch",
            {
                "source": "ja",
                "target": "es",
                "texts": ["おはようございます。", "おはようございます。"],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            [item["translated"] for item in payload["results"]],
            ["Buenos días.", "Buenos días."],
        )
        self.assertEqual(self.service.translations, 1)

    def test_rgss3_worker_status_and_authentication(self):
        status, payload = self.request("/status")
        self.assertEqual(status, 200)
        self.assertTrue(payload["active"])
        self.assertTrue(payload["batch"])
        with self.assertRaises(HTTPError) as error:
            self.request("/status", token="0" * 64)
        self.assertEqual(error.exception.code, 403)

    def test_rgss3_worker_rejects_oversized_batch(self):
        with self.assertRaises(HTTPError) as error:
            self.request(
                "/translate_batch",
                {"source": "ja", "target": "es", "texts": ["こんにちは"] * 7},
            )
        self.assertEqual(error.exception.code, 400)

    def test_rgss3_worker_rejects_unknown_source_language(self):
        with self.assertRaises(HTTPError) as error:
            self.request(
                "/translate_batch",
                {"source": "fr", "target": "es", "texts": ["Bonjour"]},
            )
        self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
