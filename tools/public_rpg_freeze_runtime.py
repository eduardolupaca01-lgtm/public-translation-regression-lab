"""Bundled Windows C-extension DLL locations for the public RPG test EXE.

PyInstaller's onefile launcher extracts native packages to sys._MEIPASS.
On Python 3.8+ Windows, extension DLL dependencies require DLL search dirs
explicitly registered with os.add_dll_directory (PATH alone is insufficient).
No DLL is downloaded, loaded from the network, or shipped from private code.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys


if os.name == "nt" and getattr(sys, "frozen", False):
    root = Path(getattr(sys, "_MEIPASS", "")).resolve()
    candidates = [
        root,
        root / "sentencepiece",
        root / "sentencepiece.libs",
        root / "ctranslate2",
        root / "ctranslate2.libs",
        root / "torch" / "lib",
        root / "numpy.libs",
    ]
    candidates.extend(root.glob("*.libs"))
    candidates.extend(root.glob("*libs"))
    discovered = []
    handles = []
    for path in candidates:
        if not path.is_dir() or path in discovered:
            continue
        discovered.append(path)
        try:
            handles.append(os.add_dll_directory(str(path)))
        except OSError:
            pass
    # Keep handles alive for the whole process; GC would remove the directories.
    sys._tenshixgame_dll_handles = handles
    sys._tenshixgame_dll_dirs = [str(path) for path in discovered]
