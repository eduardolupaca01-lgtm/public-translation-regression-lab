import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

WORKER = Path(__file__).resolve().parents[1] / "worker" / "IATraductora.py"
SPEC = importlib.util.spec_from_file_location("ia_rgss3_worker", WORKER)
IA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IA)


class RGSS3WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "Game.exe").write_bytes(b"MZ-fixture")
        (self.root / "Game.ini").write_text("[Game]\nLibrary=RGSS301.dll\n", encoding="utf-8")
        (self.root / "Game.rgss3a").write_bytes(b"RGSSAD\x00\x03" + b"archive-fixture")

    def test_detects_packed_vxace_without_running_game(self):
        game, content = IA.verified_rgss3_runtime(self.root)
        self.assertEqual(game, self.root.resolve())
        self.assertEqual(content, self.root.resolve())

    def test_worker_uses_rgss3_sidecar_and_existing_v95_service(self):
        engine = self.root / "IA Traductora" / ".local" / "Rpg" / "engine"
        engine.mkdir(parents=True)
        service = IA.Service(self.root, engine, neural=object())
        self.addCleanup(service.close)
        self.assertTrue(service.rgss3)
        self.assertFalse(service.halva)
        self.assertEqual(service.content, self.root.resolve())
        bridge = IA.publish(service, 43127)
        self.assertEqual(bridge, self.root / "IA Traductora" / ".local" / "Rpg" / "bridge.json")
        payload = json.loads(bridge.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], IA.SCHEMA)
        self.assertEqual(payload["port"], 43127)
        self.assertEqual(payload["token"], service.token)
        self.assertFalse((self.root / "data" / "IATraductora" / "bridge.json").exists())

    def test_rejects_wrong_archive_signature(self):
        (self.root / "Game.rgss3a").write_bytes(b"NOTRGSS3" + b"x")
        with self.assertRaisesRegex(ValueError, "IA_RGSS3_ARCHIVE_NO_VALIDO"):
            IA.verified_rgss3_runtime(self.root)

    def test_rejects_ambiguous_packed_and_loose_data(self):
        data = self.root / "Data"
        data.mkdir()
        (data / "System.rvdata2").write_bytes(b"system")
        (data / "Scripts.rvdata2").write_bytes(b"scripts")
        with self.assertRaisesRegex(ValueError, "IA_RGSS3_LAYOUT_AMBIGUO"):
            IA.verified_rgss3_runtime(self.root)

    def test_accepts_only_complete_loose_vxace_data(self):
        (self.root / "Game.rgss3a").unlink()
        data = self.root / "Data"
        data.mkdir()
        (data / "System.rvdata2").write_bytes(b"system")
        (data / "Scripts.rvdata2").write_bytes(b"scripts")
        game, content = IA.verified_rgss3_runtime(self.root)
        self.assertEqual(game, self.root.resolve())
        self.assertEqual(content, self.root.resolve())

    def test_rejects_loose_layout_missing_scripts(self):
        (self.root / "Game.rgss3a").unlink()
        data = self.root / "Data"
        data.mkdir()
        (data / "System.rvdata2").write_bytes(b"system")
        with self.assertRaisesRegex(ValueError, "IA_RGSS3_DATA_INCOMPLETA"):
            IA.verified_rgss3_runtime(self.root)

    def test_startup_errors_are_safely_classified(self):
        self.assertEqual(
            IA.safe_startup_code(ValueError("IA_RGSS3_ARCHIVE_NO_VALIDO")),
            "IA_RGSS3_ARCHIVE_NO_VALIDO",
        )


if __name__ == "__main__":
    unittest.main()
