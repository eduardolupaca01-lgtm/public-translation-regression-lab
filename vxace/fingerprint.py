"""Read-only VX Ace / RGSS3 game fingerprinting.

This module never launches Game.exe and never writes to the game directory.
It identifies the runtime from mutually consistent PE, Game.ini and data/archive
evidence. Archive contents are deliberately left to the next parsing layer.
"""
from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


_MAX_GAME_INI_BYTES = 1024 * 1024
_MAX_PE_HEADER_OFFSET = 16 * 1024 * 1024
_RGSS3_LIBRARY = "rgss301.dll"
_SCRIPT_FILENAME = "scripts.rvdata2"
_SYSTEM_FILENAME = "system.rvdata2"


class FingerprintError(ValueError):
    """A stable, machine-readable reason why a folder is not safe to identify."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class GameFingerprint:
    engine: str
    layout: str
    root: Path
    game_exe: Path
    game_ini: Path
    script_entry: str
    script_source: str
    archive: Path | None
    evidence: tuple[str, ...]


def _find_child(parent: Path, wanted_name: str) -> Path | None:
    if not parent.is_dir():
        return None
    matches = [entry for entry in parent.iterdir() if entry.name.casefold() == wanted_name.casefold()]
    if len(matches) > 1:
        raise FingerprintError("VXACE_CASE_COLLISION")
    if not matches:
        return None
    candidate = matches[0]
    if candidate.is_symlink():
        raise FingerprintError("VXACE_SYMLINK_NOT_ALLOWED")
    return candidate


def _require_regular_file(path: Path | None, code: str) -> Path:
    if path is None or path.is_symlink() or not path.is_file():
        raise FingerprintError(code)
    return path


def _is_pe_executable(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            header = stream.read(64)
            if len(header) < 64 or header[:2] != b"MZ":
                return False
            pe_offset = int.from_bytes(header[0x3C:0x40], "little")
            if pe_offset < 64 or pe_offset > _MAX_PE_HEADER_OFFSET:
                return False
            stream.seek(pe_offset)
            return stream.read(4) == b"PE\x00\x00"
    except OSError:
        return False


def _decode_ini(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp932", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise FingerprintError("VXACE_GAME_INI_ENCODING_INVALID")


def _read_game_ini(path: Path) -> configparser.ConfigParser:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise FingerprintError("VXACE_GAME_INI_UNREADABLE") from exc
    if len(data) > _MAX_GAME_INI_BYTES:
        raise FingerprintError("VXACE_GAME_INI_TOO_LARGE")

    parser = configparser.ConfigParser(
        interpolation=None,
        strict=True,
        delimiters=("=",),
        comment_prefixes=(";", "#"),
    )
    parser.optionxform = str.casefold
    try:
        parser.read_string(_decode_ini(data))
    except (configparser.Error, FingerprintError) as exc:
        if isinstance(exc, FingerprintError):
            raise
        raise FingerprintError("VXACE_GAME_INI_INVALID") from exc
    return parser


def _game_section(parser: configparser.ConfigParser) -> str:
    for section in parser.sections():
        if section.casefold() == "game":
            return section
    raise FingerprintError("VXACE_GAME_SECTION_MISSING")


def _safe_script_entry(value: str) -> tuple[str, ...]:
    normalized = value.strip().replace("\\", "/")
    if not normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise FingerprintError("VXACE_SCRIPT_ENTRY_UNSAFE")
    parts = tuple(normalized.split("/"))
    if any(part in ("", ".", "..") for part in parts):
        raise FingerprintError("VXACE_SCRIPT_ENTRY_UNSAFE")
    if parts[-1].casefold() != _SCRIPT_FILENAME:
        raise FingerprintError("VXACE_SCRIPT_ENTRY_UNEXPECTED")
    return parts


def _resolve_game_file(root: Path, parts: Iterable[str]) -> Path | None:
    current = root
    materialized = tuple(parts)
    for index, part in enumerate(materialized):
        child = _find_child(current, part)
        if child is None:
            return None
        if index < len(materialized) - 1:
            if not child.is_dir():
                return None
        elif not child.is_file():
            return None
        current = child
    if current.is_symlink():
        raise FingerprintError("VXACE_SYMLINK_NOT_ALLOWED")
    return current


def fingerprint_vxace(game_root: str | Path) -> GameFingerprint:
    """Identify a VX Ace folder without executing or modifying any game file.

    Packed games use Game.rgss3a as the authoritative script source when it is
    present. A loose Data/Scripts.rvdata2 beside that archive is not treated as
    authoritative because VX Ace loads scripts from the archive in that layout.
    """
    supplied_root = Path(game_root)
    if supplied_root.is_symlink():
        raise FingerprintError("VXACE_ROOT_SYMLINK_NOT_ALLOWED")
    if not supplied_root.exists() or not supplied_root.is_dir():
        raise FingerprintError("VXACE_GAME_ROOT_NOT_FOUND")
    root = supplied_root.resolve(strict=True)

    game_exe = _require_regular_file(_find_child(root, "Game.exe"), "VXACE_GAME_EXE_MISSING")
    if not _is_pe_executable(game_exe):
        raise FingerprintError("VXACE_GAME_EXE_NOT_PE")

    game_ini = _require_regular_file(_find_child(root, "Game.ini"), "VXACE_GAME_INI_MISSING")
    parser = _read_game_ini(game_ini)
    section = _game_section(parser)

    library = parser.get(section, "library", fallback="").strip().replace("\\", "/").split("/")[-1]
    if library.casefold() != _RGSS3_LIBRARY:
        raise FingerprintError("VXACE_RGSS3_LIBRARY_MISMATCH")

    raw_script_entry = parser.get(section, "scripts", fallback="")
    script_parts = _safe_script_entry(raw_script_entry)

    rgss3_archive = _find_child(root, "Game.rgss3a")
    other_archives = [
        name for name in ("Game.rgssad", "Game.rgss2a")
        if _find_child(root, name) is not None
    ]
    if other_archives:
        raise FingerprintError("VXACE_MULTIPLE_OR_OTHER_RGSS_ARCHIVE")
    if rgss3_archive is not None:
        rgss3_archive = _require_regular_file(rgss3_archive, "VXACE_RGSS3_ARCHIVE_INVALID")
        if rgss3_archive.stat().st_size == 0:
            raise FingerprintError("VXACE_RGSS3_ARCHIVE_EMPTY")
        return GameFingerprint(
            engine="RPG Maker VX Ace / RGSS3",
            layout="packed",
            root=root,
            game_exe=game_exe,
            game_ini=game_ini,
            script_entry="/".join(script_parts),
            script_source="Game.rgss3a",
            archive=rgss3_archive,
            evidence=("PE executable", "Game.ini Library=RGSS301.dll", "Game.rgss3a present"),
        )

    script_file = _resolve_game_file(root, script_parts)
    system_file = _resolve_game_file(root, ("Data", _SYSTEM_FILENAME))
    _require_regular_file(script_file, "VXACE_LOOSE_SCRIPTS_MISSING")
    _require_regular_file(system_file, "VXACE_LOOSE_SYSTEM_MISSING")

    return GameFingerprint(
        engine="RPG Maker VX Ace / RGSS3",
        layout="loose",
        root=root,
        game_exe=game_exe,
        game_ini=game_ini,
        script_entry="/".join(script_parts),
        script_source="loose",
        archive=None,
        evidence=("PE executable", "Game.ini Library=RGSS301.dll", "Data/Scripts.rvdata2", "Data/System.rvdata2"),
    )
