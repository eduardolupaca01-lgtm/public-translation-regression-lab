#!/usr/bin/env python3
"""Validate that the canonical 17-family Go UI and evidence ledger cannot drift.

An engine's historic source tests must NEVER silently turn into a "ready for
installation" GUI button. This source-free check runs on Windows and Linux.
"""
from __future__ import annotations
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
CATALOG=ROOT/"internal"/"engine"/"catalog.go"
LEDGER=ROOT/"docs"/"TX776_MATRIZ_MOTORES_17_CONTRATO.json"

def main()->None:
    raw=CATALOG.read_text(encoding="utf-8")
    ledger=json.loads(LEDGER.read_text(encoding="utf-8"))
    catalog=re.findall(r'\{ID:"([^"]+)"',raw)
    records=ledger["families"]
    recorded=[f["id"] for f in records]
    if len(catalog)!=17 or len(records)!=17 or len(set(catalog))!=17:
        raise AssertionError("TX776_CATALOG_OR_LEDGER_MUST_HAVE_17_UNIQUE_FAMILIES")
    if catalog!=recorded:
        raise AssertionError("TX776_GO_GUI_AND_LEDGER_FAMILY_ORDER_DRIFT")
    if ledger.get("catalog_family_count")!=17:
        raise AssertionError("TX776_FAMILY_COUNT_CONTRACT_DRIFT")
    if any(f["unified_detector_installer_enabled"] for f in records):
        raise AssertionError("TX776_UNVERIFIED_AUTOINSTALL_FAMILY_ENABLED")
    if any(f["physical_game_certified"] for f in records):
        raise AssertionError("TX776_SYNTHETIC_QA_MISLABELED_AS_REAL_GAME")
    pilot=ledger["pilot"]
    if pilot["family"]!="rpg-maker" or set(pilot["verified_subengines"])!={"mv","mz"}:
        raise AssertionError("TX776_PILOT_SUBENGINE_MUST_STAY_MV_MZ")
    if pilot["real_game_visual_certified"] or pilot["copy_to_clean_windows_offline_certified"]:
        raise AssertionError("TX776_SYNTHETIC_RUN_FALSIFIED_REAL_GAME_TEST")
    if ledger["installed_in_unified_R1"] or ledger["physically_certified_game_families"]!=0:
        raise AssertionError("TX776_PUBLIC_READONLY_DETECTOR_MUST_NOT_CLAIM_INSTALLER")
    if [x["id"] for x in records if x["evidence_status"]=="original-v95-mv-mz"]!=["rpg-maker"]:
        raise AssertionError("TX776_V95_MV_MZ_WRONGLY_IMPORTED_INTO_ANOTHER_ENGINE")
    for r in records:
        if r["evidence_status"] not in {"original-v95-mv-mz","research-only","read-only"}:
            raise AssertionError("TX776_UNKNOWN_EVIDENCE_CATEGORY")
        if not r["notes"].strip():
            raise AssertionError("TX776_EMPTY_EVIDENCE_LIMIT")
    print("TX776_17_FAMILY_READONLY_INSTALLATION_CONTRACT_PASS")

if __name__=="__main__":
    main()
