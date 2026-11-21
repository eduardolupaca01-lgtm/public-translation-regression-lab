"""Exploratory RPG neural stress test, structurally strict but NOT human-approved.

Twelve source-only Japanese challenges, same uniform research model as the
quality calibration experiment. Accepted means *structural validation only*.
Detailed human bilingual review of meanings is ALWAYS required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.stage4_rpg_stress_cases import STRESS_CASES, manifest
from tools.stage4_source_complete_candidate import (
    GENERATION_VARIANT, SOURCE_PROMPT_SHA256, load_quality_model,
)
from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import TranslationRejected, translate_checked, validate_translation
from translation_lab.review_queue import ReviewQueue
from translation_lab.restart import verify_candidate_persistence


MODES = (
    ("document_context", "document"),
    ("line_context", "lines"),
    ("sentence_context", True),
)


def _write(path: Path, obj: dict):
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def translate_phase(workspace: Path, llama_server: Path | None, model_loader=None) -> int:
    if workspace.exists():
        raise RuntimeError("STAGE4_RPG_WORKSPACE_MUST_BE_NEW")
    workspace.mkdir(parents=True)
    frozen = manifest()
    _write(workspace / "rpg-source-manifest.json", frozen)
    report = {
        "schema": "ja-es-stage4-rpg-exploratory-neural-v1",
        "kind": "EXPLORATORY_RESEARCH_NOT_LINGUISTIC_APPROVAL",
        "sources_only": True,
        "generation_variant": GENERATION_VARIANT,
        "translation_system_prompt_sha256": SOURCE_PROMPT_SHA256,
        "target_repairs": False,
        "case_specific_prompts": False,
        "reference_spanish_provided_to_model": False,
        "human_approvals": False,
        "model_executed": False,
        "professional_quality_approved": False,
        "bilingual_review_required": True,
        "required": len(STRESS_CASES),
        "manifest_sha256": frozen["sha256"],
        "cases": [],
    }
    model = None
    try:
        if model_loader is not None:
            model, provenance = model_loader()
        elif llama_server is None:
            raise RuntimeError("STAGE4_RPG_LLAMA_SERVER_PATH_REQUIRED")
        else:
            model, provenance = load_quality_model(llama_server, workspace)
        report["model_provenance"] = provenance
        report["model_executed"] = True

        with (
            DurableTranslationCache(workspace / "cache") as cache,
            ReviewQueue(workspace / "cache") as reviews,
        ):
            for sample in STRESS_CASES:
                row = {
                    "case": sample.id,
                    "source": sample.japanese,
                    "risk": sample.risk,
                    "status": "rejected",
                    "raw_model_attempts": [],
                    "rejected_modes": [],
                }
                proposals: list[str] = []

                def produce(source: str):
                    for mode, layout in MODES:
                        def model_piece(fragment: str):
                            raw = model.translate(fragment)
                            row["raw_model_attempts"].append({
                                "mode": mode,
                                "source_fragment": fragment,
                                "raw_output": raw,
                            })
                            return raw

                        try:
                            value = translate_checked(
                                source,
                                model_piece,
                                source="ja",
                                protect_numbers=False,
                                contextualize_name_codes=False,
                                split_model_sentences=layout,
                                protect_literals_in_context=True,
                            )
                            proposals.append(value)
                            validate_translation(source, value, source="ja")
                            row["accepted_mode"] = mode
                            return value
                        except Exception as exc:
                            row["rejected_modes"].append({
                                "mode": mode,
                                "reason": type(exc).__name__ + ":" + str(exc)[:450],
                            })
                    raise TranslationRejected("STAGE4_RPG_ALL_UNIFORM_MODES_REJECTED")

                try:
                    output = cache.translate_or_get(
                        "ja", "es", sample.japanese, produce,
                        quality_validator=lambda x, src=sample.japanese:
                            validate_translation(src, x, source="ja"),
                    )
                    validate_translation(sample.japanese, output, source="ja")
                    row["translated"] = output
                    row["sha256"] = hashlib.sha256(output.encode("utf-8")).hexdigest()
                    row["status"] = "structurally_accepted"
                    row["human_bilingual_review_pending"] = True
                except Exception as exc:
                    row["error"] = type(exc).__name__ + ":" + str(exc)[:500]
                    ticket = reviews.enqueue(
                        "ja", "es", sample.japanese,
                        proposals[-1] if proposals else "",
                        reason=row["error"],
                        context={
                            "case_id": sample.id,
                            "raw_model_attempts": row["raw_model_attempts"],
                            "research_only": True,
                        },
                    )
                    row["review_item_id"] = ticket.item_id
                    row["review_status"] = ticket.status

                report["cases"].append(row)
                print(
                    "STAGE4_RPG_CASE " + sample.id + " " + row["status"],
                    flush=True,
                )
            report["cache_rows"] = cache.count()
            report["review_queue_total"] = reviews.count()
            report["review_queue_pending"] = reviews.count("pending")
            reviews.export_snapshot(workspace / "rpg-review-queue.json")
    except Exception as exc:
        report["setup_error"] = type(exc).__name__ + ":" + str(exc)[:600]
    finally:
        if model is not None and hasattr(model, "close"):
            model.close()

    report["structurally_accepted"] = sum(
        row.get("status") == "structurally_accepted" for row in report["cases"]
    )
    report["rejected"] = len(STRESS_CASES) - report["structurally_accepted"]
    report["status"] = (
        "STRUCTURAL_PASS_BILINGUAL_REVIEW_PENDING"
        if (
            report["model_executed"]
            and report["structurally_accepted"] == len(STRESS_CASES)
            and report.get("cache_rows") == len(STRESS_CASES)
            and report.get("review_queue_total") == 0
        )
        else "RESEARCH_INCOMPLETE"
    )
    _write(workspace / "rpg-neural-report.json", report)
    print(
        "STAGE4_RPG_REPORT "
        + json.dumps({
            "status": report["status"],
            "structurally_accepted": report["structurally_accepted"],
            "rejected": report["rejected"],
            "professional_quality_approved": False,
            "bilingual_review_required": True,
        }, sort_keys=True),
        flush=True,
    )
    return 0 if report["status"] == "STRUCTURAL_PASS_BILINGUAL_REVIEW_PENDING" else 1


def verify_phase(workspace: Path) -> int:
    path = workspace / "rpg-neural-report.json"
    frozen_path = workspace / "rpg-source-manifest.json"
    if not path.is_file() or not frozen_path.is_file():
        print("STAGE4_RPG_RESTART_PROOF_MISSING_RECEIPTS", flush=True)
        return 1
    report = json.loads(path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    expected = {sample.id: sample for sample in STRESS_CASES}
    rows = report.get("cases") or []
    accepted = [x for x in rows if x.get("status") == "structurally_accepted"]
    errors: list[str] = []
    persistence: list[str] = []
    quality: list[str] = []

    if (
        report.get("manifest_sha256") != manifest()["sha256"]
        or frozen.get("cases") != manifest()["cases"]
        or frozen.get("sha256") != manifest()["sha256"]
        or len(rows) != len(expected)
        or {x.get("case") for x in rows} != set(expected)
    ):
        errors.append("STAGE4_RPG_SOURCE_RECEIPTS_CHANGED")
    if not report.get("model_executed"):
        errors.append("STAGE4_RPG_MODEL_NOT_EXECUTED")
    if len(accepted) != len(expected):
        quality.append("STAGE4_RPG_NOT_ALL_CASES_STRUCTURALLY_ACCEPTED")

    cache_path = workspace / "cache" / "translation-cache.sqlite3"
    if not cache_path.is_file():
        persistence.append("STAGE4_RPG_CACHE_DATABASE_MISSING")
    else:
        with (
            DurableTranslationCache(workspace / "cache") as cache,
            ReviewQueue(workspace / "cache") as reviews,
        ):
            persistence.extend(verify_candidate_persistence(
                cache, reviews,
                accepted_count=len(accepted),
                rejected_count=max(0, len(rows) - len(accepted)),
                prefix="STAGE4RPG",
            ))
            for row in accepted:
                sample = expected.get(row.get("case"))
                if sample is None:
                    errors.append("STAGE4_RPG_UNKNOWN_CASE")
                    continue
                translation = row.get("translated", "")
                if row.get("source") != sample.japanese:
                    errors.append("STAGE4_RPG_SOURCE_CHANGED:" + sample.id)
                if row.get("sha256") != hashlib.sha256(
                    translation.encode("utf-8")
                ).hexdigest():
                    persistence.append("STAGE4_RPG_OUTPUT_HASH_CHANGED:" + sample.id)
                try:
                    validate_translation(sample.japanese, translation, source="ja")
                except TranslationRejected:
                    quality.append("STAGE4_RPG_STRUCTURAL_REVALIDATION_FAILED:" + sample.id)
                    continue
                validator = lambda value, src=sample.japanese: validate_translation(
                    src, value, source="ja"
                )
                restored = cache.get(
                    "ja", "es", sample.japanese,
                    quality_validator=validator,
                )
                if restored != translation:
                    persistence.append("STAGE4_RPG_CACHE_CONTENT_CHANGED:" + sample.id)
                    continue
                try:
                    reused = cache.translate_or_get(
                        "ja", "es", sample.japanese,
                        lambda _: (_ for _ in ()).throw(
                            AssertionError("STAGE4_RPG_RECALLED_MODEL")
                        ),
                        quality_validator=validator,
                    )
                    if reused != translation:
                        persistence.append("STAGE4_RPG_CACHE_REPLAY_CHANGED:" + sample.id)
                except Exception as exc:
                    persistence.append(
                        "STAGE4_RPG_CACHE_REPLAY_FAILED:" + sample.id
                        + ":" + type(exc).__name__
                    )

    proof = {
        "schema": "ja-es-stage4-rpg-cold-restart-v1",
        "required": len(expected),
        "structurally_accepted": len(accepted),
        "models_loaded_during_restart": False,
        "bilingual_review_completed": False,
        "professional_quality_approved": False,
        "errors": errors,
        "quality_errors": quality,
        "persistence_errors": persistence,
        "structural_status": "PASS" if not quality else "FAIL",
        "persistence_status": "PASS" if not persistence else "FAIL",
        "status": (
            "STRUCTURAL_PASS_BILINGUAL_REVIEW_PENDING"
            if not (errors or quality or persistence)
            else "QUALITY_FAIL_PERSISTENCE_PASS"
            if not (errors or persistence) else "FAIL"
        ),
    }
    _write(workspace / "rpg-cold-restart-proof.json", proof)
    print("STAGE4_RPG_COLD_RESTART " + json.dumps(proof, sort_keys=True))
    return 0 if not errors and not persistence else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--llama-server", type=Path)
    args = parser.parse_args()
    if args.phase == "translate":
        return translate_phase(args.workspace, args.llama_server)
    return verify_phase(args.workspace)


if __name__ == "__main__":
    raise SystemExit(main())
