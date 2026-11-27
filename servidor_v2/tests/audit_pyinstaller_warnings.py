#!/usr/bin/env python3
"""Summarize only module identifiers and import contexts from PyInstaller.

No raw report lines, absolute paths, credentials, model contents or private
source are emitted. Analysis warnings are evidence, not proof of runtime
failure; the frozen EXE and OPUS acceptance gates remain mandatory.
"""
import argparse
import collections
import re
from pathlib import Path

ENTRY = re.compile(
    r"^(missing|excluded|invalid) module named "
    r"['\"]?([A-Za-z_][A-Za-z0-9_.]{0,159})['\"]?\s+- imported by (.*)$"
)
IMPORTER = re.compile(
    r"(?:^|,\s*)([A-Za-z_][A-Za-z0-9_.]{0,159})\s+\(([a-z ,\-]+)\)"
)
CONTEXTS = {"top-level", "conditional", "delayed", "optional"}

def summarize(report):
    counts = collections.Counter()
    rows = []
    unparsed = 0
    for line in report.splitlines():
        match = ENTRY.fullmatch(line)
        if match is None:
            if "module named " in line:
                unparsed += 1
            continue
        kind, module, tail = match.groups()
        contexts = set()
        importers = []
        for importer, raw in IMPORTER.findall(tail):
            tags = {tag.strip() for tag in raw.split(",")} & CONTEXTS
            contexts.update(tags)
            if tags:
                importers.append(importer + "(" + ",".join(sorted(tags)) + ")")
        counts[kind] += 1
        # Preserve attribution to the importing module, not a filesystem path.
        rows.append((kind, module, ",".join(sorted(contexts)) or "unclassified",
                     ";".join(importers) or "unclassified"))
    return counts, sorted(rows), unparsed

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    if (not args.report.is_file() or args.report.is_symlink()
            or args.report.stat().st_size > 4 * 1024 * 1024):
        raise SystemExit("IA_PYINSTALLER_WARNING_REPORT_UNAVAILABLE")
    report = args.report.read_text(encoding="utf-8", errors="replace")
    counts, rows, unparsed = summarize(report)
    print("IA_PYINSTALLER_WARNING_SUMMARY "
          + " ".join(f"{k}={counts[k]}" for k in ("missing", "excluded", "invalid"))
          + f" unparsed={unparsed}")
    for kind, module, context, importers in rows:
        print(f"IA_PYINSTALLER_IMPORT {kind} {module} {context} importers={importers}")
    print("IA_PYINSTALLER_REPORT_REVIEW_REQUIRED runtime_acceptance_remains_mandatory")

if __name__ == "__main__":
    main()
