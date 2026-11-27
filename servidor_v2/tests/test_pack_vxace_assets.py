import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.pack_vxace_assets import (
    HELPER_NAME,
    PLUGIN_NAME,
    append_assets,
    verify_assets,
)


def fake_pe_amd64() -> bytes:
    data = bytearray(256)
    data[:2] = b"MZ"
    data[0x3C:0x40] = (64).to_bytes(4, "little")
    data[64:68] = b"PE\0\0"
    data[68:70] = (0x8664).to_bytes(2, "little")
    data[64 + 24:64 + 26] = (0x20B).to_bytes(2, "little")
    return bytes(data)


class PackVXAssetsTests(unittest.TestCase):
    def test_adds_owned_helper_and_plugin_without_losing_bootstrap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exe = root / "Servidor.exe"
            helper = root / "vxace-helper.exe"
            plugin = root / "TenshixgameVXACELive.rb"
            helper.write_bytes(fake_pe_amd64())
            plugin.write_text(
                "# TENSHIXGAME_VXACE_RGSS3_OWNER_V1\n"
                "PLUGIN_BUILD = 'VXACE-RGSS3-20261126-A'\n",
                encoding="utf-8",
            )
            package = root / "package.zip"
            manifest = {"schema": "servidor-v2-package-v1", "files": {"IATraductora.exe": "a" * 64}}
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("manifest.json", json.dumps(manifest))
                archive.writestr("IATraductora.exe", b"worker")
                archive.writestr("models/opus_ja_es/model.bin", b"model")
            exe.write_bytes(b"MZ-BOOTSTRAP-PREFIX" + package.read_bytes())
            result = append_assets(exe, helper, plugin)
            self.assertEqual(result["helper_sha256"], hashlib.sha256(helper.read_bytes()).hexdigest())
            self.assertEqual(result["plugin_sha256"], hashlib.sha256(plugin.read_bytes()).hexdigest())
            self.assertTrue(exe.read_bytes().startswith(b"MZ-BOOTSTRAP-PREFIX"))
            self.assertEqual(verify_assets(exe)["entry_count"], 5)
            with zipfile.ZipFile(exe) as archive:
                self.assertEqual(archive.read(HELPER_NAME), helper.read_bytes())
                self.assertEqual(archive.read(PLUGIN_NAME), plugin.read_bytes())
                self.assertEqual(archive.read("IATraductora.exe"), b"worker")

    def test_rejects_wrong_helper_architecture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            exe = root / "Servidor.exe"
            helper = root / "helper.exe"
            plugin = root / "plugin.rb"
            helper.write_bytes(b"MZ" + b"\0" * 200)
            plugin.write_text(
                "# TENSHIXGAME_VXACE_RGSS3_OWNER_V1\n"
                "PLUGIN_BUILD = 'VXACE-RGSS3-20261126-A'\n",
                encoding="utf-8",
            )
            with zipfile.ZipFile(exe, "w") as archive:
                archive.writestr("manifest.json", json.dumps({"files": {}}))
            with self.assertRaises(ValueError):
                append_assets(exe, helper, plugin)


if __name__ == "__main__":
    unittest.main()
