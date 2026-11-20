"""Fail public CI if disallowed binary/model/secret files enter this repository."""
from __future__ import annotations
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_SUFFIXES = {".zip", ".exe", ".dll", ".onnx", ".bin", ".pt", ".pth",
                    ".safetensors", ".sqlite", ".sqlite3", ".db", ".pem", ".key",
                    ".pkl", ".argostranslate", ".argosmodel", ".gguf", ".ckpt",
                    ".spm", ".model", ".tflite", ".npz", ".gz", ".7z"}
BLOCKED_NAMES = {".env", "id_rsa", "id_ed25519",
                 "embedded_worker.py", "v95_safety.py"}
BLOCKED_DIRECTORIES = {"private", "models", "model_weights", "original_game", "game",
                       "saves", "assets", "runtime-src", "quarantine"}
SECRET_PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"ghp_[A-Za-z0-9]{32,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{60,}"),
]

def inspect_tree() -> list[str]:
    errors = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(ROOT)
        if (path.suffix.lower() in BLOCKED_SUFFIXES or path.name in BLOCKED_NAMES
                or any(part.lower() in BLOCKED_DIRECTORIES for part in rel.parts)):
            errors.append("blocked public file: " + str(rel))
            continue
        if path.stat().st_size > 1048576:
            errors.append("oversized file: " + str(rel))
            continue
        content = path.read_bytes()
        if any(pattern.search(content) for pattern in SECRET_PATTERNS):
            errors.append("credential-looking text: " + str(rel))
    return errors

if __name__ == "__main__":
    problems = inspect_tree()
    for issue in problems:
        print(issue)
    if problems:
        raise SystemExit("PUBLICATION_GUARD_FAILED")
    print("PUBLICATION_GUARD_OK")
