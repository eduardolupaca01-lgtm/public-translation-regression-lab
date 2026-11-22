"""Execute original Eduardo TX765 Windows build, preserving its exact private gates.

The private source is checked out only in the ephemeral Windows runner at a
pinned SHA. No game files, model weights, original code, or build logs are
published to the public repository. The two source-writing and public-release
steps are never run. The verified EXE is encrypted before artifact upload.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

SOURCE_REPO = "eduardolupaca01-lgtm/tenshixgame-rpg-tx723-build"
SOURCE_SHA = "b69efbe13c02bc341f1443e46e5eee8d1b805f07"
SOURCE_BRANCH = "fix/tx771-portable-game-local-worker-and-render-20261122"
SOURCE_WORKFLOW = ".github/workflows/tx758-clean-current-baseline.yml"

BUILD_STEPS = (
    "TX718 original cache speed, native labels, names, Japanese punctuation and strict regressions",
    "TX757 independently prove the durable-cache template survives restart before neural rebuild",
    "TX765 protect synchronous custom RPG Bitmap from Spanish-over-Japanese and recover real bridge folder",
    "TX712 beta confirm V95 SQLite durable cache and native no-double-scan on MV/MZ",
    "Check new GUI and one-executable integrity tests only",
    "Verify TX203 archived source, bounded continuation and safe original onefile contracts",
    "TX723 verify revised source snapshot is strictly pinned before real V95 rebuild",
    "Build NEW native TENSHIXGAME RPG interface (not old MV RenPy GUI)",
    "Build ONE native RPG x64 EXE streaming bootstrap",
    "Download and SHA256-pin original V95 from EDUARDO private release (not Panda or Actions artifacts)",
    "Install exact original V95 build dependencies in disposable private Windows CI",
    "Rebuild exact TX203 V95 worker ONLY with source-pinned scanner continuation",
    "Repackage only verified V95 worker, preserving all 21 model and supervisor files",
    "Test rebuilt original V95 Japanese-to-Spanish locally through authenticated HTTP",
    "TX723 cryptographic V95 worker pin against exact native RPG JS",
    "TX763 apply current durable-cache patch AFTER strict source attestation, then archive exact delivery",
    "TX720 REBUILD final actual GUI and prove Go-embedded installed JS SHA equals the actual model EXE",
    "Assemble ONE real TENSHIXGAME RPG EXE (no user-visible scripts or folders)",
    "Verify the exact original 22-file neural engine and UI bytes INSIDE the single EXE",
    "ACTUALLY start onefile on disposable Windows installation (no games)",
    "TX712 verify original offline V95 neural SQLite updates hydrate production renderer without a duplicate model request",
    "TX711 verify original V95 infers Japanese to Spanish in idle map and paints native sentence on first render",
    "Prove exact original V95 cold-starts locally from Node WITHOUT Terminal or Internet",
    "Record immutable SHA256 receipt for the owner-visible ONE EXE",
    "End-to-end real V95 model engine plus original MV plugin install and exact rollback",
    "TX720 verify exact runtime SHA before PRIVATE DRAFT GitHub release",
)
EXCLUDED = (
    "TX763 archive this exact current delivery for the NEXT private update",
    "Upload verified EXE to PRIVATE DRAFT GitHub release (not Actions artifact storage)",
)


def check_original_workflow(document):
    job = (document.get("jobs") or {}).get("build-verify-private-windows")
    if not isinstance(job, dict) or not isinstance(job.get("steps"), list):
        raise RuntimeError("ORIGINAL_EDUARDO_WORKFLOW_MISSING")
    all_steps = job["steps"]
    setup = [s.get("uses") for s in all_steps if "uses" in s]
    if setup != [
        "actions/checkout@v4", "actions/setup-go@v5",
        "actions/setup-python@v5", "actions/setup-node@v4",
    ]:
        raise RuntimeError("ORIGINAL_EDUARDO_TOOLCHAIN_CHANGED")
    steps = [s for s in all_steps if "run" in s]
    if [s.get("name") for s in steps] != list(BUILD_STEPS + EXCLUDED):
        raise RuntimeError("ORIGINAL_EDUARDO_GATES_CHANGED_REVIEW_REQUIRED")
    if any(s.get("shell") != "pwsh" or not isinstance(s["run"], str) for s in steps):
        raise RuntimeError("ORIGINAL_EDUARDO_SHELL_CHANGED")
    return steps[:-2]


def render(value, runner_temp, token):
    value = value.replace("$" + "{{ runner.temp }}", runner_temp)
    value = value.replace("$" + "{{ github.token }}", token)
    if "$" + "{{" in value:
        raise RuntimeError("UNEXPECTED_ORIGINAL_WORKFLOW_EXPRESSION")
    return value


def self_test():
    template = [
        {"uses": "actions/checkout@v4"},
        {"uses": "actions/setup-go@v5"},
        {"uses": "actions/setup-python@v5"},
        {"uses": "actions/setup-node@v4"},
    ] + [{"name": n, "shell": "pwsh", "run": "echo OK"}
         for n in BUILD_STEPS + EXCLUDED]
    sample = {"jobs": {"build-verify-private-windows": {"steps": template}}}
    assert len(check_original_workflow(sample)) == 26
    template[-1]["name"] = "unauthorized release"
    try:
        check_original_workflow(sample)
    except RuntimeError:
        pass
    else:
        raise AssertionError("PUBLIC_RELEASE_STEP_NOT_BLOCKED")
    assert render("$" + "{{ runner.temp }}", "C:/build", "test") == "C:/build"
    try:
        render("$" + "{{ secrets.unexpected }}", "C:/build", "test")
    except RuntimeError:
        pass
    else:
        raise AssertionError("UNAPPROVED_SECRET_EXPRESSION")
    print("EDUARDO_ORIGINAL_WINDOWS_BRIDGE_PREFLIGHT_PASS")


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while chunk := fp.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def execute(source_root, receipt_path):
    import yaml

    token = os.environ.get("EDUARDO_RPG_SOURCE_TOKEN", "")
    runner_temp = os.environ.get("RUNNER_TEMP", "")
    if len(token) < 20 or os.environ.get("EDUARDO_RPG_ARCHIVE_PASSWORD", "") == "":
        print("EDUARDO_ORIGINAL_BUILD_HOLD:PRIVATE_CREDENTIAL_OR_ENCRYPTION_PASSWORD_MISSING")
        return 2
    if os.name != "nt" or not runner_temp:
        raise RuntimeError("ORIGINAL_BUILD_REQUIRES_WINDOWS_RUNNER")
    root = source_root.resolve()
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                  text=True).strip()
    if sha != SOURCE_SHA:
        raise RuntimeError("EDUARDO_ORIGINAL_SOURCE_COMMIT_MISMATCH")
    # Require the real existing app's TX765 runtime and bridge repairs.
    # The original 26 Windows quality gates remain separately mandatory.
    template = root / "reference/tx331-clean-product-host/rpg_live_plugin/versions/tx757-patched-template.js"
    native_go = root / "reference/tx331-clean-product-host/cmd/tenshixgame-ui/main_windows.go"
    for label, file, signatures in (
        ("TX765_JS", template, ("tx765FirstNativePaint", "separateName", "nameVisible", "localNameBox", "_tx765FirstPaintSource", "dynamicSpeaker", "mirrorSqliteTranslation", "sqliteVerifiedKeys", "native_lookup_untranslated", "whitespaceAliasKey", "foregroundRetriedAt", "native_adapter_installed", "tx771PortableRuntime", "tx771BridgeFailed", "_tx771ConvertedBeforeDraw", "bridge_descriptor_located",
                                "TenshigameTraduccion", "prefetch_read_summary")),
        ("TX765_WINDOWS", native_go, ("TenshigameTranduccion", "TenshigameTraduccion")),
        ("TX768_JS_TEST", root / "tests/js/test_tx765_no_overdraw_sync_custom_start.js",
         ("TX768 PASS", "pendingSpeaker", "inlineSpeaker")),
        ("TX769_SQLITE_PERSISTENCE_TEST", root / "tests/js/test_tx769_sqlite_durable_restart.js",
         ("TX769 SQLITE DURABLE RESTORE PASS", "awaitSavedSqliteMirror", "serveHistoricalSqlite=false")),
        ("TX770_FOREGROUND_RECOVERY_TEST", root / "tests/js/test_tx770_foreground_cache_before_cooldown.js",
         ("TX770 FOREGROUND CACHE BEFORE COOLDOWN PASS", "A failed background retry", "No second urgent retry")),
        ("TX770_WHITESPACE_RESTART_TEST", root / "tests/js/test_tx770_sqlite_whitespace_recovery.js",
         ("TX770 SQLITE WHITESPACE RESTORE PASS", "paddedFile", "paddedRestartWindow")),
        ("TX770_OWNER_PREDECESSOR_GO", root / "reference/tx331-clean-product-host/rpg_live.go",
         ("rpgLegacyTX769OwnerInstalledSHA", "rpgOwnedPluginHash")),
        ("TX770_OWNER_PREDECESSOR_TEST", root / "reference/tx331-clean-product-host/rpg_tx770_owner_tx769_upgrade_test.go",
         ("TestTX770RecognizesOwnersExactTX769InstalledScriptForUpgrade",
          "TX770 must not relax owner source guard")),
        ("TX771_PORTABLE_PLUGIN_TEST", root / "tests/js/test_tx771_game_local_v95_portability.js",
         ("TX771 PORTABLE GAME LOCAL V95 PASS", "TEMP", "TMPDIR")),
        ("TX771_CUSTOM_NATIVE_RENDER_TEST", root / "tests/js/test_tx771_custom_message_converter_first_paint.js",
         ("TX771 CUSTOM NATIVE CONVERTER FIRST PAINT PASS", "no second paint layer")),
        ("TX771_GAME_LOCAL_WORKER", root / "reference/tx541-rpg-onefile/tx771_portable_windows.go",
         ("tx771PreparePortableOnefile", "tx771ChooseGameEXE", "TX771_PORTABLE_PUBLISH_FAILED")),
        ("TX771_GAME_LOCAL_JOURNAL", root / "reference/tx331-clean-product-host/rpg_tx771_adopt_legacy.go",
         ("rpgTX771AdoptVerifiedPreviousInstall", "TX771_PREVIOUS_JS_UNKNOWN_OR_MODIFIED")),
        ("TX771_MIGRATION_TEST", root / "reference/tx331-clean-product-host/rpg_tx771_legacy_official_adoption_test.go",
         ("TestTX771RecoverPreviousKnownPluginNoGlobalJournal",
          "TestTX771RefuseAlteredPriorInstalledPlugin")),
    ):
        if not file.is_file() or not all(p in file.read_text(encoding="utf-8") for p in signatures):
            raise RuntimeError(label + "_ORIGINAL_SOURCE_REPAIR_MISSING")
    private_workflow = (root / SOURCE_WORKFLOW).read_bytes()
    steps = check_original_workflow(yaml.safe_load(private_workflow.decode("utf-8")))
    result = {
        "schema": "eduardo-original-rpg-exe-windows-build-v1",
        "status": "HOLD",
        "original_private_repository": SOURCE_REPO,
        "source_commit": sha,
        "tx765_private_repair_source_verified": True,
        "source_workflow_sha256": hashlib.sha256(private_workflow).hexdigest(),
        "real_original_steps": 26,
        "steps_passed": 0,
        "source_repository_written": False,
        "original_source_or_model_files_published": False,
        "public_release_authorized": False,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(runner_temp)
    try:
        for number, step in enumerate(steps, 1):
            print(f"EDUARDO_ORIGINAL_GATE_{number:02d}_START:{step['name']}", flush=True)
            env = dict(os.environ)
            env["GITHUB_REPOSITORY"] = SOURCE_REPO
            env["GITHUB_REF_NAME"] = SOURCE_BRANCH
            env["GITHUB_SHA"] = SOURCE_SHA
            for key, value in (step.get("env") or {}).items():
                env[key] = render(str(value), runner_temp, token)
            env["GH_TOKEN"] = token
            script = temp / f"eduardo-original-gate-{number:02d}.ps1"
            private_log = temp / f"eduardo-original-gate-{number:02d}.log"
            script.write_text(
                "$ErrorActionPreference = 'Stop'\n"
                + render(step["run"], runner_temp, token)
                + "\nif ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }\n",
                encoding="utf-8-sig",
            )
            try:
                with private_log.open("wb") as log:
                    process = subprocess.run(
                        ["pwsh", "-NoProfile", "-NonInteractive",
                         "-ExecutionPolicy", "Bypass", "-File", str(script)],
                        cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                        timeout=55 * 60, check=False,
                    )
            finally:
                script.unlink(missing_ok=True)
            if process.returncode:
                # Only diagnostic *codes*, never private scripts/logs, games,
                # model output, paths, bearer credentials or stack traces.
                import re
                safe_codes = sorted(set(re.findall(
                    r"\bTX[0-9]{3}_[A-Z][A-Z0-9_]{4,90}\b",
                    private_log.read_text(encoding="utf-8", errors="replace")[-25000:],
                )))
                result["safe_gate_error_codes"] = safe_codes[:12]
                print("EDUARDO_ORIGINAL_SAFE_FAILURE_CODES:" +
                      json.dumps(safe_codes[:12]), flush=True)
                raise RuntimeError(f"ORIGINAL_GATE_{number:02d}_FAILED")
            result["steps_passed"] = number
            receipt_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(f"EDUARDO_ORIGINAL_GATE_{number:02d}_PASS", flush=True)
        exe = temp / "Tenshixgame-RPG.exe"
        if not exe.is_file() or exe.stat().st_size < 600_000_000:
            raise RuntimeError("ORIGINAL_WINDOWS_V95_EXE_MISSING_OR_SMALL")
        result.update({
            "status": "ORIGINAL_EXE_BUILT_AND_REAL_NEURAL_TESTS_PASS",
            "exe_size_bytes": exe.stat().st_size,
            "exe_sha256": file_hash(exe),
            "exe_name": exe.name,
            "original_neural_model_tested": True,
            "public_release_authorized": False,
            "encrypted_artifact_required": True,
        })
        print("EDUARDO_ORIGINAL_EXE_BUILT_REAL_MODEL_VERIFIED", flush=True)
        return 0
    except Exception as exc:
        result["status"] = "HOLD"
        result["blocker"] = str(exc)
        print("EDUARDO_ORIGINAL_EXE_HOLD:" + str(exc), flush=True)
        return 1
    finally:
        receipt_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--source-root", type=Path)
    p.add_argument("--receipt", type=Path)
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.source_root or not args.receipt:
        p.error("--source-root and --receipt required")
    return execute(args.source_root, args.receipt)


if __name__ == "__main__":
    raise SystemExit(main())
