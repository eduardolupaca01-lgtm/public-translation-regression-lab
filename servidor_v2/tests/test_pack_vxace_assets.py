import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zipfile

# The repository also has a top-level tools package. Import the actual
# Servidor packer by its directory, not through the ambiguous namespace.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pack import build, MAGIC, SCHEMA, MODELS, SUFFIX
from pack_vxace_assets import HELPER_NAME, PLUGIN_NAME, PLUGIN_MARKER, PLUGIN_BUILD


def pe_amd64():
    data = bytearray(256)
    data[:2] = b"MZ"
    data[60:64] = (64).to_bytes(4, "little")
    data[64:68] = b"PE\0\0"
    data[68:70] = (0x8664).to_bytes(2, "little")
    data[88:90] = (0x20b).to_bytes(2, "little")
    return bytes(data)


class PackVXAssetsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.root = root
        self.bootstrap = root / "bootstrap.exe"
        self.bootstrap.write_bytes(b"MZ synthetic bootstrap")
        self.worker = root / "worker.exe"
        self.worker.write_bytes(b"synthetic worker; not executable")
        self.js = root / "plugin.js"
        self.js.write_text("synthetic", encoding="utf-8")
        self.helper = root / "vxace-helper.exe"
        self.helper.write_bytes(pe_amd64())
        self.ruby = root / "runtime.rb"
        self.ruby.write_bytes(PLUGIN_MARKER + b"\n# " + PLUGIN_BUILD + b"\n")
        self.models = root / "models"
        for model in MODELS:
            directory = self.models / model
            directory.mkdir(parents=True)
            for name in (*SUFFIX, "OPUS_LICENSE.txt"):
                (directory / name).write_bytes((model + name).encode())
        self.out = root / "Servidor.exe"

    def pack(self, **kwargs):
        build(self.bootstrap, self.worker, self.js, self.models, self.out, **kwargs)

    def read_package(self):
        raw = self.out.read_bytes()
        self.assertEqual(raw[-16:], MAGIC)
        size = struct.unpack("<Q", raw[-56:-48])[0]
        package = raw[-56-size:-56]
        self.assertEqual(hashlib.sha256(package).digest(), raw[-48:-16])
        self.assertEqual(raw[:-56-size], self.bootstrap.read_bytes())
        with zipfile.ZipFile(io.BytesIO(package)) as z:
            manifest = json.loads(z.read("manifest.json"))
            self.assertEqual(manifest["schema"], SCHEMA)
            self.assertEqual(set(z.namelist()), set(manifest["files"]) | {"manifest.json"})
            for name, digest in manifest["files"].items():
                self.assertEqual(hashlib.sha256(z.read(name)).hexdigest(), digest)
            return {name: z.read(name) for name in manifest["files"]}

    def test_package_keeps_all_r30_entries_and_adds_both_assets(self):
        self.pack(vxace_helper=self.helper, vxace_plugin=self.ruby)
        files = self.read_package()
        self.assertEqual(files[HELPER_NAME], self.helper.read_bytes())
        self.assertEqual(files[PLUGIN_NAME], self.ruby.read_bytes())
        self.assertEqual(files["IATraductora.exe"], self.worker.read_bytes())
        self.assertEqual(files["IATraductora.js"], self.js.read_bytes())
        self.assertEqual(len(files), 2 + len(MODELS) * (len(SUFFIX) + 1) + 2)

    def test_legacy_mv_mz_package_is_unchanged(self):
        self.pack()
        files = self.read_package()
        self.assertNotIn(HELPER_NAME, files)
        self.assertNotIn(PLUGIN_NAME, files)

    def test_half_package_and_wrong_architecture_are_rejected_before_writing(self):
        with self.assertRaises(ValueError):
            self.pack(vxace_helper=self.helper)
        self.assertFalse(self.out.exists())
        self.helper.write_bytes(b"MZ" + b"\0" * 200)
        with self.assertRaises(ValueError):
            self.pack(vxace_helper=self.helper, vxace_plugin=self.ruby)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
