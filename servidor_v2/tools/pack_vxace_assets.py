#!/usr/bin/env python3
"""Add the verified VX Ace helper/runtime to the existing Servidor SFX package.

This post-pack step preserves the already-built bootstrap and every existing
package entry. It does not build a second installer or a second AI worker.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

HELPER_NAME = "vxace-helper.exe"
PLUGIN_NAME = "vxace/TenshixgameVXACELive.rb"
PLUGIN_MARKER = b"# TENSHIXGAME_VXACE_RGSS3_OWNER_V1"
PLUGIN_BUILD = b"VXACE-RGSS3-20261126-A"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pe_amd64(path: Path) -> None:
    with path.open("rb") as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise ValueError("VXACE_HELPER_NOT_PE")
        pe_offset = int.from_bytes(dos[0x3C:0x40], "little")
        if pe_offset < 64 or pe_offset > 1024 * 1024:
            raise ValueError("VXACE_HELPER_PE_OFFSET_INVALID")
        stream.seek(pe_offset)
        header = stream.read(26)
    if len(header) < 26 or header[:4] != b"PE\0\0":
        raise ValueError("VXACE_HELPER_PE_SIGNATURE_INVALID")
    machine = int.from_bytes(header[4:6], "little")
    optional_magic = int.from_bytes(header[24:26], "little")
    if machine != 0x8664 or optional_magic != 0x20B:
        raise ValueError("VXACE_HELPER_MUST_BE_WINDOWS_X64")


def find_manifest(archive: zipfile.ZipFile) -> str:
    candidates = [
        name for name in archive.namelist()
        if Path(name.replace("\\", "/")).name.lower() in {
            "manifest.json", "package-manifest.json", "servidor-manifest.json"
        }
    ]
    if len(candidates) != 1:
        raise ValueError("SERVIDOR_PACKAGE_MANIFEST_NOT_UNIQUE")
    return candidates[0]


def sfx_prefix_length(path: Path) -> int:
    with path.open("rb") as stream:
        end_record = zipfile._EndRecData(stream)
    if end_record is None or len(end_record) < 10:
        raise ValueError("SERVIDOR_SFX_ZIP_FOOTER_INVALID")
    prefix = end_record[-1]
    if not isinstance(prefix, int) or prefix < 0 or prefix >= path.stat().st_size:
        raise ValueError("SERVIDOR_SFX_PREFIX_INVALID")
    return prefix


def read_manifest(archive: zipfile.ZipFile) -> tuple[str, dict]:
    name = find_manifest(archive)
    try:
        manifest = json.loads(archive.read(name).decode("utf-8"))
    except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("SERVIDOR_PACKAGE_MANIFEST_INVALID") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise ValueError("SERVIDOR_PACKAGE_MANIFEST_SCHEMA_INVALID")
    return name, manifest


def verify_assets(exe: Path) -> dict:
    with zipfile.ZipFile(exe, "r") as archive:
        manifest_name, manifest = read_manifest(archive)
        names = set(archive.namelist())
        if HELPER_NAME not in names or PLUGIN_NAME not in names:
            raise ValueError("SERVIDOR_VXACE_ASSETS_MISSING")
        helper_sha = hashlib.sha256(archive.read(HELPER_NAME)).hexdigest()
        plugin_bytes = archive.read(PLUGIN_NAME)
        plugin_sha = hashlib.sha256(plugin_bytes).hexdigest()
        if manifest["files"].get(HELPER_NAME) != helper_sha:
            raise ValueError("SERVIDOR_VXACE_HELPER_MANIFEST_MISMATCH")
        if manifest["files"].get(PLUGIN_NAME) != plugin_sha:
            raise ValueError("SERVIDOR_VXACE_PLUGIN_MANIFEST_MISMATCH")
        if PLUGIN_MARKER not in plugin_bytes or PLUGIN_BUILD not in plugin_bytes:
            raise ValueError("SERVIDOR_VXACE_PLUGIN_BUILD_INVALID")
        return {
            "manifest": manifest_name,
            "helper_sha256": helper_sha,
            "plugin_sha256": plugin_sha,
            "entry_count": len(names),
        }


def append_assets(exe: Path, helper: Path, plugin: Path) -> dict:
    exe = exe.resolve(strict=True)
    helper = helper.resolve(strict=True)
    plugin = plugin.resolve(strict=True)
    if not exe.is_file() or exe.is_symlink():
        raise ValueError("SERVIDOR_EXE_INVALID")
    if not helper.is_file() or helper.is_symlink():
        raise ValueError("VXACE_HELPER_INVALID")
    if not plugin.is_file() or plugin.is_symlink():
        raise ValueError("VXACE_PLUGIN_INVALID")
    verify_pe_amd64(helper)
    plugin_bytes = plugin.read_bytes()
    if len(plugin_bytes) == 0 or len(plugin_bytes) > 1024 * 1024:
        raise ValueError("VXACE_PLUGIN_SIZE_INVALID")
    if PLUGIN_MARKER not in plugin_bytes or PLUGIN_BUILD not in plugin_bytes:
        raise ValueError("VXACE_PLUGIN_BUILD_INVALID")

    prefix_len = sfx_prefix_length(exe)
    with exe.open("rb") as stream:
        prefix = stream.read(prefix_len)
    helper_bytes = helper.read_bytes()
    helper_sha = hashlib.sha256(helper_bytes).hexdigest()
    plugin_sha = hashlib.sha256(plugin_bytes).hexdigest()

    with zipfile.ZipFile(exe, "r") as source:
        manifest_name, manifest = read_manifest(source)
        existing = set(source.namelist())
        for required in (HELPER_NAME, PLUGIN_NAME):
            if required in existing:
                # Replacing a prior owned build is allowed only if its manifest
                # hash still matches the actual bytes; unknown payloads are held.
                old_sha = manifest["files"].get(required)
                actual_sha = hashlib.sha256(source.read(required)).hexdigest()
                if not old_sha or old_sha != actual_sha:
                    raise ValueError("SERVIDOR_VXACE_EXISTING_ASSET_NOT_OWNED")
        manifest["files"][HELPER_NAME] = helper_sha
        manifest["files"][PLUGIN_NAME] = plugin_sha
        entries = []
        for info in source.infolist():
            if info.filename in (HELPER_NAME, PLUGIN_NAME, manifest_name):
                continue
            entries.append((info, source.read(info.filename)))

    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    exe_dir = exe.parent
    fd, temp_name = tempfile.mkstemp(prefix=".servidor-vxace-", suffix=".exe", dir=exe_dir)
    os.close(fd)
    temp_exe = Path(temp_name)
    temp_zip = temp_exe.with_suffix(".zip")
    try:
        with zipfile.ZipFile(temp_zip, "w", allowZip64=True) as output:
            for info, data in entries:
                output.writestr(info, data)
            output.writestr(manifest_name, manifest_bytes, compress_type=zipfile.ZIP_DEFLATED)
            output.writestr(HELPER_NAME, helper_bytes, compress_type=zipfile.ZIP_DEFLATED)
            output.writestr(PLUGIN_NAME, plugin_bytes, compress_type=zipfile.ZIP_DEFLATED)
        with temp_exe.open("wb") as output, temp_zip.open("rb") as package:
            output.write(prefix)
            for chunk in iter(lambda: package.read(1024 * 1024), b""):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        verify_assets(temp_exe)
        os.replace(temp_exe, exe)
        return verify_assets(exe)
    finally:
        for path in (temp_exe, temp_zip):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--helper", type=Path)
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        if args.verify:
            result = verify_assets(args.exe)
        else:
            if args.helper is None or args.plugin is None:
                raise ValueError("VXACE_HELPER_AND_PLUGIN_REQUIRED")
            result = append_assets(args.exe, args.helper, args.plugin)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(str(exc), file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
