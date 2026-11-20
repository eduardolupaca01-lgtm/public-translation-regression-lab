"""Cross-process durability and single-flight acceptance (public fake model).

All Japanese text is synthetic. No neural weights, private data, binaries or
network access. The deliberately slow fake producer makes duplicate inference
visible; its output must never be mistaken for real translation quality.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import TranslationRejected

DEFAULT_CASES = 36
DEFAULT_WORKERS = 8


def sample(index: int) -> tuple[str, str]:
    number = index + 1
    code = r"\V[12]" if index % 3 == 0 else ""
    original = code + f"学校に{number}人がいます。"
    translated = code + f"Hay {number} personas en la escuela."
    if index % 5 == 0:
        original += "\r\n明日は休みです。"
        translated += "\r\nMañana es día libre."
    return original, translated


def audit_database(workspace: Path) -> Path:
    return workspace / "translation-attempts.sqlite3"


def setup_audit(workspace: Path) -> None:
    with sqlite3.connect(audit_database(workspace), timeout=30) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS attempts("
            " source_id TEXT NOT NULL, worker_id TEXT NOT NULL)"
        )


def record_attempt(connection: sqlite3.Connection, source_id: str, worker_id: str) -> None:
    with connection:
        connection.execute(
            "INSERT INTO attempts(source_id,worker_id) VALUES(?,?)",
            (source_id, worker_id),
        )


def worker(workspace: Path, worker_id: int, cases: int) -> int:
    deadline = time.monotonic() + 25
    while not (workspace / "start.flag").exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("CACHE_STRESS_START_BARRIER_TIMEOUT")
        time.sleep(0.02)
    audit = sqlite3.connect(audit_database(workspace), timeout=30)
    try:
        with DurableTranslationCache(workspace / "cache") as cache:
            for index in range(cases):
                source, expected = sample(index)

                def fake_model(_text: str) -> str:
                    record_attempt(audit, str(index), str(worker_id))
                    time.sleep(0.04)
                    return expected

                result = cache.translate_or_get("ja", "es", source, fake_model)
                if result != expected:
                    raise AssertionError("CACHE_STRESS_INCORRECT_RESULT:" + str(index))
    finally:
        audit.close()
    print("STRESS_WORKER_OK " + str(worker_id), flush=True)
    return 0


def verify_fresh_process(workspace: Path, cases: int, final: bool) -> int:
    with DurableTranslationCache(workspace / "cache") as cache:
        target_count = cases + (2 if final else 0)
        if cache.count() != target_count:
            raise AssertionError(
                f"RESTART_ROW_COUNT_CHANGED:{cache.count()}!={target_count}"
            )
        for index in range(cases):
            original, expected = sample(index)

            def forbidden_model(_text: str) -> str:
                raise AssertionError("CACHE_HIT_RECALLED_FAKE_MODEL")

            result = cache.translate_or_get("ja", "es", original, forbidden_model)
            if result != expected:
                raise AssertionError("CACHE_RESTART_RESULT_CHANGED:" + str(index))
        if final:
            for original, expected in (
                ("友人は水泳部です。", "Mi amigo pertenece al club de natación."),
                ("学校に999人がいます。", "Hay 999 personas en la escuela."),
            ):
                result = cache.translate_or_get(
                    "ja", "es", original,
                    lambda _text: (_ for _ in ()).throw(
                        AssertionError("CACHE_FINAL_RETRANSLATED")
                    ),
                )
                if result != expected:
                    raise AssertionError("CACHE_FINAL_VALUE_CHANGED")
    print("FRESH_PROCESS_REPLAY_OK", flush=True)
    return 0


def stale_update(workspace: Path, replay_only: bool) -> int:
    original = "友人は水泳部です。"
    expected = "Mi amigo pertenece al club de natación."

    def quality_gate(value: str) -> None:
        if "es un club" in value or "pertenece al club" not in value:
            raise TranslationRejected("STALE_SEMANTIC_RELATIONSHIP")

    with DurableTranslationCache(workspace / "cache") as cache:
        if not replay_only and cache.get(
            "ja", "es", original, quality_validator=quality_gate
        ) is not None:
            raise AssertionError("STALE_INVALID_ROW_WAS_ACCEPTED")
        def model(_text: str) -> str:
            if replay_only:
                raise AssertionError("STALE_UPGRADE_RETRANSLATED")
            with sqlite3.connect(audit_database(workspace), timeout=30) as audit:
                record_attempt(audit, "stale", "upgrade")
            return expected
        result = cache.translate_or_get(
            "ja", "es", original, model, quality_validator=quality_gate
        )
        if result != expected:
            raise AssertionError("STALE_ROW_NOT_REPLACED")
    print("STALE_REPLAY_OK" if replay_only else "STALE_UPGRADE_OK", flush=True)
    return 0


def crash_worker(workspace: Path) -> int:
    with DurableTranslationCache(workspace / "cache") as cache:
        def crash(_text: str) -> str:
            print("CRASH_INSIDE_SINGLEFLIGHT", flush=True)
            os._exit(39)
        cache.translate_or_get(
            "ja", "es", "学校に999人がいます。", crash
        )
    raise AssertionError("CRASH_WORKER_UNEXPECTEDLY_RETURNED")


def recover_worker(workspace: Path) -> int:
    original = "学校に999人がいます。"
    expected = "Hay 999 personas en la escuela."
    with DurableTranslationCache(workspace / "cache") as cache:
        if cache.get("ja", "es", original) is not None:
            raise AssertionError("CRASH_PERSISTED_INCOMPLETE_RESULT")
        def model(_text: str) -> str:
            with sqlite3.connect(audit_database(workspace), timeout=30) as audit:
                record_attempt(audit, "crash", "recovered")
            return expected
        if cache.translate_or_get("ja", "es", original, model) != expected:
            raise AssertionError("CRASH_RECOVERY_RESULT_INVALID")
    print("CRASH_RECOVERY_OK", flush=True)
    return 0


def child_command(workspace: Path, mode: str, **options: int) -> list[str]:
    command = [sys.executable, "-m", "tools.cache_stress", mode,
               "--workspace", str(workspace)]
    for key, value in options.items():
        command.extend(["--" + key.replace("_", "-"), str(value)])
    return command


def execute_child(workspace: Path, mode: str, *, expected_code: int = 0,
                  **options: int) -> str:
    process = subprocess.run(
        child_command(workspace, mode, **options),
        capture_output=True, text=True, encoding="utf-8", timeout=95
    )
    if process.returncode != expected_code:
        raise AssertionError(
            f"CACHE_CHILD_{mode}_EXIT_{process.returncode}_EXPECTED_{expected_code}"
            f":{process.stdout[-700:]}:{process.stderr[-700:]}"
        )
    return process.stdout


def stress(workspace: Path, cases: int = DEFAULT_CASES,
           workers: int = DEFAULT_WORKERS) -> int:
    if workspace.exists():
        raise ValueError("CACHE_STRESS_REQUIRES_FRESH_WORKSPACE")
    if not (1 <= cases <= 120 and 2 <= workers <= 16):
        raise ValueError("CACHE_STRESS_WORKLOAD_OUT_OF_BOUNDS")
    workspace.mkdir(parents=True)
    receipt = {
        "schema": "public-singleflight-durability-v1",
        "kind": "SYNTHETIC_FAKE_MODEL_NOT_NEURAL_PROOF",
        "unique_sources": cases,
        "concurrent_workers": workers,
        "total_requests": cases * workers,
        "fake_model_calls": None,
        "duplicate_fake_model_calls": None,
        "restart_without_model_calls": False,
        "stale_policy_recovered": False,
        "worker_crash_recovered": False,
        "errors": [],
    }
    processes = []
    try:
        setup_audit(workspace)
        with DurableTranslationCache(workspace / "cache") as cache:
            if cache.count() != 0:
                raise AssertionError("CACHE_STRESS_NONEMPTY_START")
        for worker_id in range(workers):
            processes.append(subprocess.Popen(
                child_command(
                    workspace, "worker", worker_id=worker_id, cases=cases
                ),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8"
            ))
        (workspace / "start.flag").write_text("go\n", encoding="utf-8")
        for index, child in enumerate(processes):
            stdout, stderr = child.communicate(timeout=95)
            if child.returncode != 0 or "STRESS_WORKER_OK" not in stdout:
                raise AssertionError(
                    f"CONCURRENT_WORKER_{index}_FAILED_{child.returncode}:"
                    f"{stdout[-500:]}:{stderr[-500:]}"
                )
        with sqlite3.connect(audit_database(workspace), timeout=30) as audit:
            rows = audit.execute(
                "SELECT source_id, COUNT(*) FROM attempts GROUP BY source_id"
            ).fetchall()
        calls = sum(int(n) for _, n in rows)
        duplicates = sum(max(int(n) - 1, 0) for _, n in rows)
        receipt["fake_model_calls"] = calls
        receipt["duplicate_fake_model_calls"] = duplicates
        if len(rows) != cases or calls != cases or duplicates != 0:
            raise AssertionError(
                f"DUPLICATE_INFERENCE:{calls}_FOR_{cases}_UNIQUE:{rows[:8]}"
            )
        if "FRESH_PROCESS_REPLAY_OK" not in execute_child(
            workspace, "verify", cases=cases
        ):
            raise AssertionError("COLD_REPLAY_NO_SUCCESS_MARKER")
        receipt["restart_without_model_calls"] = True

        with DurableTranslationCache(workspace / "cache") as cache:
            cache.put(
                "ja", "es", "友人は水泳部です。",
                "Mi amigo es un club de natación."
            )
        if "STALE_UPGRADE_OK" not in execute_child(workspace, "stale-upgrade"):
            raise AssertionError("STALE_UPGRADE_NOT_CONFIRMED")
        if "STALE_REPLAY_OK" not in execute_child(workspace, "stale-replay"):
            raise AssertionError("STALE_REPLAY_NOT_CONFIRMED")
        receipt["stale_policy_recovered"] = True

        output = execute_child(
            workspace, "crash", expected_code=39
        )
        if "CRASH_INSIDE_SINGLEFLIGHT" not in output:
            raise AssertionError("CRASH_NOT_INSIDE_SINGLEFLIGHT")
        if "CRASH_RECOVERY_OK" not in execute_child(workspace, "recover"):
            raise AssertionError("LOCK_STUCK_AFTER_CRASH")
        receipt["worker_crash_recovered"] = True
        if "FRESH_PROCESS_REPLAY_OK" not in execute_child(
            workspace, "verify", cases=cases, final=1
        ):
            raise AssertionError("FINAL_REPLAY_NO_SUCCESS_MARKER")
        with sqlite3.connect(audit_database(workspace), timeout=30) as audit:
            remaining = audit.execute(
                "SELECT source_id, COUNT(*) FROM attempts "
                "WHERE source_id IN ('stale','crash') GROUP BY source_id"
            ).fetchall()
        if sorted(remaining) != [("crash", 1), ("stale", 1)]:
            raise AssertionError("STALE_OR_CRASH_DUPLICATE_ATTEMPT:" + str(remaining))
    except Exception as exc:
        receipt["errors"].append(type(exc).__name__ + ":" + str(exc)[:900])
    finally:
        for p in processes:
            if p.poll() is None:
                p.kill()
                p.communicate()
        receipt["status"] = "PASS" if not receipt["errors"] else "FAIL"
        (workspace / "cache-stress-report.json").write_text(
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8"
        )
        print("CACHE_STRESS_REPORT " +
              json.dumps(receipt, ensure_ascii=True, sort_keys=True), flush=True)
    return 0 if not receipt["errors"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=(
        "stress", "worker", "verify", "stale-upgrade",
        "stale-replay", "crash", "recover"
    ))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cases", type=int, default=DEFAULT_CASES)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--worker-id", type=int, default=0)
    parser.add_argument("--final", type=int, choices=(0, 1), default=0)
    args = parser.parse_args()
    if args.mode == "stress":
        return stress(args.workspace, args.cases, args.workers)
    if args.mode == "worker":
        return worker(args.workspace, args.worker_id, args.cases)
    if args.mode == "verify":
        return verify_fresh_process(args.workspace, args.cases, bool(args.final))
    if args.mode == "stale-upgrade":
        return stale_update(args.workspace, False)
    if args.mode == "stale-replay":
        return stale_update(args.workspace, True)
    if args.mode == "crash":
        return crash_worker(args.workspace)
    return recover_worker(args.workspace)


if __name__ == "__main__":
    sys.exit(main())
