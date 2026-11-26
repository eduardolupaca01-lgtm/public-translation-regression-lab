from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from vxace.fingerprint import FingerprintError, fingerprint_vxace


def write_pe(path: Path) -> None:
    data = bytearray(128)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = (64).to_bytes(4, "little")
    data[64:68] = b"PE\x00\x00"
    path.write_bytes(data)


def make_game(
    root: Path,
    *,
    library: str = "RGSS301.dll",
    scripts: str = r"Data\Scripts.rvdata2",
    packed: bool = False,
    loose: bool = True,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    write_pe(root / "Game.exe")
    (root / "Game.ini").write_text(
        "[Game]\n"
        f"Library={library}\n"
        f"Scripts={scripts}\n"
        "Title=VX Ace fixture\n",
        encoding="utf-8",
    )
    if packed:
        (root / "Game.rgss3a").write_bytes(b"SYNTHETIC_RGSS3A_FIXTURE")
    if loose:
        data_dir = root / "Data"
        data_dir.mkdir(exist_ok=True)
        (data_dir / "Scripts.rvdata2").write_bytes(b"SYNTHETIC_MARSHAL_SCRIPTS")
        (data_dir / "System.rvdata2").write_bytes(b"SYNTHETIC_MARSHAL_SYSTEM")
    return root


class VXAceFingerprintTests(unittest.TestCase):
    def test_detects_loose_vxace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "VX Ace")
            result = fingerprint_vxace(game)
            self.assertEqual(result.engine, "RPG Maker VX Ace / RGSS3")
            self.assertEqual(result.layout, "loose")
            self.assertEqual(result.script_source, "loose")
            self.assertIsNone(result.archive)

    def test_detects_archive_only_vxace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "Packed", packed=True, loose=False)
            result = fingerprint_vxace(game)
            self.assertEqual(result.layout, "packed")
            self.assertEqual(result.script_source, "Game.rgss3a")
            self.assertEqual(result.archive, game / "Game.rgss3a")

    def test_archive_is_authoritative_when_loose_scripts_are_also_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "Mixed", packed=True, loose=True)
            result = fingerprint_vxace(game)
            self.assertEqual(result.script_source, "Game.rgss3a")
            self.assertEqual(result.layout, "packed")

    def test_detects_japanese_and_spaced_game_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "Prueba 日本語 con espacios")
            result = fingerprint_vxace(game)
            self.assertEqual(result.root, game.resolve())

    def test_rejects_other_rgss_library(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "VX", library="RGSS202.dll")
            with self.assertRaises(FingerprintError) as caught:
                fingerprint_vxace(game)
            self.assertEqual(caught.exception.code, "VXACE_RGSS3_LIBRARY_MISMATCH")

    def test_rejects_non_pe_game_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "Bad PE")
            (game / "Game.exe").write_bytes(b"not a Windows executable")
            with self.assertRaises(FingerprintError) as caught:
                fingerprint_vxace(game)
            self.assertEqual(caught.exception.code, "VXACE_GAME_EXE_NOT_PE")

    def test_rejects_unsafe_scripts_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "Unsafe", scripts=r"..\outside\Scripts.rvdata2")
            with self.assertRaises(FingerprintError) as caught:
                fingerprint_vxace(game)
            self.assertEqual(caught.exception.code, "VXACE_SCRIPT_ENTRY_UNSAFE")

    def test_rejects_missing_loose_system_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "Missing System")
            (game / "Data" / "System.rvdata2").unlink()
            with self.assertRaises(FingerprintError) as caught:
                fingerprint_vxace(game)
            self.assertEqual(caught.exception.code, "VXACE_LOOSE_SYSTEM_MISSING")

    def test_rejects_empty_rgss3a(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "Empty archive", packed=True, loose=False)
            (game / "Game.rgss3a").write_bytes(b"")
            with self.assertRaises(FingerprintError) as caught:
                fingerprint_vxace(game)
            self.assertEqual(caught.exception.code, "VXACE_RGSS3_ARCHIVE_EMPTY")

    def test_rejects_rgss2_archive_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "Wrong archive")
            (game / "Game.rgss2a").write_bytes(b"SYNTHETIC_RGSS2A")
            with self.assertRaises(FingerprintError) as caught:
                fingerprint_vxace(game)
            self.assertEqual(caught.exception.code, "VXACE_MULTIPLE_OR_OTHER_RGSS_ARCHIVE")

    def test_detection_does_not_modify_game_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            game = make_game(Path(temp) / "Read only", packed=True, loose=True)
            before = {
                str(path.relative_to(game)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in game.rglob("*")
                if path.is_file()
            }
            fingerprint_vxace(game)
            after = {
                str(path.relative_to(game)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in game.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
