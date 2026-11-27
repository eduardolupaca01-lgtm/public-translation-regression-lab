"""Validate the RGSS3 assets before they enter the normal Servidor package.

No second SFX or alternate footer: pack.py owns the one package format.
"""
from pathlib import Path

HELPER_NAME = "vxace-helper.exe"
PLUGIN_NAME = "vxace/IATraductoraVXACE.rb"
PLUGIN_MARKER = b"# IA_TRADUCTORA_VXACE_RGSS3_OWNER_V1"
PLUGIN_BUILD = b"VXACE-RGSS3-20261126-D"


def validated_assets(helper: Path, plugin: Path) -> dict[str, Path]:
    for file, limit in ((helper, 128 * 1024 * 1024), (plugin, 1024 * 1024)):
        if file.is_symlink() or not file.is_file() or not 0 < file.stat().st_size <= limit:
            raise ValueError("IA_VXACE_ASSET_INVALIDO")
    with helper.open("rb") as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise ValueError("IA_VXACE_HELPER_NOT_PE")
        offset = int.from_bytes(dos[60:64], "little")
        if not 64 <= offset <= 1024 * 1024:
            raise ValueError("IA_VXACE_HELPER_PE_OFFSET")
        stream.seek(offset)
        header = stream.read(26)
    if (len(header) != 26 or header[:4] != b"PE\0\0" or
            int.from_bytes(header[4:6], "little") != 0x8664 or
            int.from_bytes(header[24:26], "little") != 0x20B):
        raise ValueError("IA_VXACE_HELPER_MUST_BE_WINDOWS_X64")
    raw = plugin.read_bytes()
    raw.decode("utf-8", errors="strict")
    if PLUGIN_MARKER not in raw or PLUGIN_BUILD not in raw:
        raise ValueError("IA_VXACE_PLUGIN_BUILD_INVALIDO")
    return {HELPER_NAME: helper, PLUGIN_NAME: plugin}
