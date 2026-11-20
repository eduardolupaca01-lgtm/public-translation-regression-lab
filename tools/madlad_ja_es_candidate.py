"""Compare pinned MADLAD-400 direct Japanese -> Spanish candidates.

This is a model-development comparison on the already-published stage-two
20-case set. It is NOT a new blind holdout and cannot approve production.
The frozen case definitions and semantic checks are imported unchanged.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import time

from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import (
    TranslationRejected,
    translate_checked,
    validate_translation,
)
from translation_lab.review_queue import ReviewQueue
from tools.independent_pivot_holdout import (
    INDEPENDENT_CASES,
    _require_semantic_fidelity,
)

MODEL_SPECS = {
    "base": {
        "repo_id": "Nextcloud-AI/madlad400-3b-mt-ct2-int8",
        "revision": "aa32bbdeba7880eff2096ec044cb155a340a9400",
        "target_tag": "<2es>",
        "base_model": "google/madlad400-3b-mt",
        "variant": "MADLAD-400-3B-MT base",
        "declared_license": "apache-2.0",
        "quantization": "int8",
        "model_page": "https://huggingface.co/Nextcloud-AI/madlad400-3b-mt-ct2-int8",
    },
    "es419": {
        "repo_id": "Ugiat/madlad400-3b-mt-es_419-ct2",
        "revision": "5a6603fbcb4ba576682031862cf8bdb2bf89597f",
        "target_tag": "<2es_419>",
        "base_model": "google/madlad400-3b-mt",
        "variant": "MADLAD-400-3B-MT Latin American Spanish fine-tune",
        "declared_license": "apache-2.0",
        "quantization": "int8_float16",
        "model_page": "https://huggingface.co/Ugiat/madlad400-3b-mt-es_419-ct2",
    },
}
CT2_VERSION = "4.8.2"
TRANSFORMERS_VERSION = "4.57.6"


@dataclass
class MadladTranslator:
    tokenizer: object
    translator: object
    target_tag: str

    def translate(self, text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise TranslationRejected("MADLAD_EMPTY_SOURCE")
        prompted = self.target_tag + " " + text
        input_ids = self.tokenizer.encode(prompted)
        if not input_ids or len(input_ids) > 512:
            raise TranslationRejected("MADLAD_INPUT_CONTEXT_INVALID")
        source_tokens = self.tokenizer.convert_ids_to_tokens(input_ids)
        results = self.translator.translate_batch(
            [source_tokens],
            beam_size=4,
            max_decoding_length=256,
            no_repeat_ngram_size=3,
        )
        if len(results) != 1 or not results[0].hypotheses:
            raise TranslationRejected("MADLAD_INVALID_GENERATION")
        output_tokens = results[0].hypotheses[0]
        output_ids = self.tokenizer.convert_tokens_to_ids(output_tokens)
        output = self.tokenizer.decode(
            output_ids, skip_special_tokens=True
        )
        if not isinstance(output, str) or not output.strip():
            raise TranslationRejected("MADLAD_EMPTY_OUTPUT")
        return output.strip()


def _load_model(candidate: str):
    if candidate not in MODEL_SPECS:
        raise ValueError("UNKNOWN_MADLAD_CANDIDATE")
    import ctranslate2
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer

    spec = MODEL_SPECS[candidate]
    if ctranslate2.__version__ != CT2_VERSION:
        raise RuntimeError(
            "MADLAD_CTRANSLATE2_VERSION_MISMATCH:"
            + str(ctranslate2.__version__)
        )
    path = snapshot_download(
        repo_id=spec["repo_id"],
        revision=spec["revision"],
    )
    tokenizer = AutoTokenizer.from_pretrained(
        path, trust_remote_code=False
    )
    translator = ctranslate2.Translator(
        path,
        device="cpu",
        compute_type="int8",
        inter_threads=1,
        intra_threads=2,
    )
    provenance = {
        "candidate": candidate,
        "repo_id": spec["repo_id"],
        "revision": spec["revision"],
        "base_model": spec["base_model"],
        "variant": spec["variant"],
        "target_tag": spec["target_tag"],
        "source": "ja",
        "target": "es-419" if candidate == "es419" else "es",
        "declared_license": spec["declared_license"],
        "quantization": spec["quantization"],
        "runtime": "CTranslate2",
        "runtime_version": ctranslate2.__version__,
        "transformers_version": TRANSFORMERS_VERSION,
        "device": "cpu",
        "trust_remote_code": False,
        "model_page": spec["model_page"],
    }
    return MadladTranslator(tokenizer, translator, spec["target_tag"]), [provenance]


def _save_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def translate_phase(candidate: str, workspace: Path, model_loader=None) -> int:
    if candidate not in MODEL_SPECS:
        raise ValueError("UNKNOWN_MADLAD_CANDIDATE")
    if workspace.exists():
        raise RuntimeError("MADLAD_WORKSPACE_MUST_BE_NEW")
    workspace.mkdir(parents=True)
    spec = MODEL_SPECS[candidate]
    report = {
        "schema": "public-madlad-direct-ja-es-candidate-v1",
        "kind": "REAL_NEURAL_PUBLIC_MADLAD_DIRECT_CANDIDATE_NOT_PRODUCTION_APPROVAL",
        "candidate": candidate,
        "route": ["ja-es"],
        "expected_model": {
            "repo_id": spec["repo_id"],
            "revision": spec["revision"],
            "target_tag": spec["target_tag"],
            "declared_license": spec["declared_license"],
            "quantization": spec["quantization"],
        },
        "evaluation_policy": {
            "cases": len(INDEPENDENT_CASES),
            "case_set_status": "previously_published_development_regression_set_not_blind",
            "frozen_case_definitions_and_semantic_checks": True,
            "source_paraphrases": False,
            "target_repairs": False,
            "glossary_edits": False,
            "human_approvals": False,
            "case_specific_retries": False,
            "uniform_segmentation_modes": [
                "document_context", "line_context", "sentence_context"
            ],
            "numeric_literals_sent_to_model": True,
            "structural_protection_only": True,
            "selection": "first_candidate_passing_frozen_semantic_policy",
            "all_cases_required": True,
        },
        "backend_executed": False,
        "models": [],
        "cases": [],
    }
    started = time.monotonic()
    try:
        model, provenance = (
            _load_model(candidate) if model_loader is None else model_loader(candidate)
        )
        if (
            len(provenance) != 1
            or provenance[0].get("repo_id") != spec["repo_id"]
            or provenance[0].get("revision") != spec["revision"]
            or provenance[0].get("target_tag") != spec["target_tag"]
            or provenance[0].get("declared_license") != spec["declared_license"]
        ):
            raise RuntimeError("MADLAD_MODEL_PROVENANCE_INVALID")
        report["backend_executed"] = True
        report["models"] = provenance

        with (
            DurableTranslationCache(workspace / "cache") as cache,
            ReviewQueue(workspace / "cache") as review_queue,
        ):
            for case in INDEPENDENT_CASES:
                attempts: list[dict] = []
                candidate_box: list[str] = []
                entry = {
                    "case": case.id,
                    "source": case.japanese,
                    "status": "rejected",
                    "raw_model_attempts": attempts,
                }

                def producer(source_text: str) -> str:
                    rejected_modes: list[dict[str, str]] = []
                    for mode, segmentation in (
                        ("document_context", "document"),
                        ("line_context", "lines"),
                        ("sentence_context", True),
                    ):
                        def model_piece(fragment: str) -> str:
                            value = model.translate(fragment)
                            attempts.append({
                                "mode": mode,
                                "source_fragment": fragment[:260],
                                "raw_output": value[:700] if isinstance(value, str) else "",
                            })
                            return value

                        try:
                            translated = translate_checked(
                                source_text,
                                model_piece,
                                source="ja",
                                protect_numbers=False,
                                split_model_sentences=segmentation,
                                contextualize_name_codes=True,
                            )
                            candidate_box.append(translated)
                            validate_translation(
                                source_text, translated, source="ja"
                            )
                            _require_semantic_fidelity(case, translated)
                            entry["accepted_segmentation_mode"] = mode
                            entry["rejected_segmentation_modes"] = rejected_modes
                            return translated
                        except TranslationRejected as exc:
                            rejected_modes.append({
                                "mode": mode,
                                "reason": str(exc)[:500],
                            })

                    entry["rejected_segmentation_modes"] = rejected_modes
                    raise TranslationRejected(
                        "ALL_MADLAD_SEGMENTATION_MODES_REJECTED:"
                        + json.dumps(rejected_modes, ensure_ascii=False)[:1200]
                    )

                try:
                    translated = cache.translate_or_get(
                        "ja",
                        "es",
                        case.japanese,
                        producer,
                        quality_validator=lambda value, current=case:
                            _require_semantic_fidelity(current, value),
                    )
                    validate_translation(case.japanese, translated, source="ja")
                    _require_semantic_fidelity(case, translated)
                    entry["status"] = "accepted"
                    entry["translated"] = translated
                except Exception as exc:
                    entry["error"] = type(exc).__name__ + ":" + str(exc)[:1200]
                    item = review_queue.enqueue(
                        "ja",
                        "es",
                        case.japanese,
                        candidate_box[-1] if candidate_box else "",
                        reason=entry["error"],
                        context={
                            "case_id": case.id,
                            "semantic_policy": "independent_holdout_v1_frozen",
                            "candidate": candidate,
                            "model_provenance": provenance,
                            "raw_model_attempts": attempts,
                        },
                    )
                    entry["review_item_id"] = item.item_id
                    entry["review_status"] = item.status

                report["cases"].append(entry)
                print(
                    "MADLAD_CANDIDATE_CASE "
                    + candidate + " " + case.id + " "
                    + entry["status"] + " " + entry.get("error", ""),
                    flush=True,
                )

            report["cache_rows"] = cache.count()
            report["review_queue_pending"] = review_queue.count("pending")
            report["review_queue_total"] = review_queue.count()
            review_queue.export_snapshot(workspace / "review-queue.json")
    except Exception as exc:
        report["setup_error"] = type(exc).__name__ + ":" + str(exc)[:1200]
        print("MADLAD_CANDIDATE_SETUP_FAILURE " + report["setup_error"], flush=True)

    report["accepted"] = sum(
        row.get("status") == "accepted" for row in report["cases"]
    )
    report["rejected"] = len(INDEPENDENT_CASES) - report["accepted"]
    report["required"] = len(INDEPENDENT_CASES)
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["status"] = (
        "PASS"
        if report["backend_executed"]
        and report["accepted"] == len(INDEPENDENT_CASES)
        else "FAIL"
    )
    _save_json(workspace / "madlad-candidate-report.json", report)
    print(
        "MADLAD_CANDIDATE_REPORT "
        + json.dumps(report, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if report["status"] == "PASS" else 1


def verify_phase(candidate: str, workspace: Path) -> int:
    if candidate not in MODEL_SPECS:
        raise ValueError("UNKNOWN_MADLAD_CANDIDATE")
    report_path = workspace / "madlad-candidate-report.json"
    if not report_path.is_file():
        print("MADLAD_CANDIDATE_RESTART_FAIL_NO_REPORT", flush=True)
        return 1

    spec = MODEL_SPECS[candidate]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = report.get("cases", [])
    accepted = [row for row in rows if row.get("status") == "accepted"]
    errors: list[str] = []

    if report.get("candidate") != candidate:
        errors.append("MADLAD_CANDIDATE_CHANGED")
    if not report.get("backend_executed"):
        errors.append("MADLAD_REAL_INFERENCE_NOT_EXECUTED")
    if report.get("expected_model", {}).get("repo_id") != spec["repo_id"]:
        errors.append("MADLAD_MODEL_REPO_CHANGED")
    if report.get("expected_model", {}).get("revision") != spec["revision"]:
        errors.append("MADLAD_MODEL_REVISION_CHANGED")
    if report.get("expected_model", {}).get("target_tag") != spec["target_tag"]:
        errors.append("MADLAD_TARGET_TAG_CHANGED")
    if len(rows) != len(INDEPENDENT_CASES):
        errors.append("MADLAD_CASE_COUNT_CHANGED")
    if len(accepted) != len(INDEPENDENT_CASES):
        errors.append("MADLAD_NOT_ALL_CASES_ACCEPTED")

    models = report.get("models", [])
    if len(models) != 1:
        errors.append("MADLAD_MODEL_PROVENANCE_CARDINALITY_INVALID")
    else:
        observed = models[0]
        if observed.get("repo_id") != spec["repo_id"]:
            errors.append("MADLAD_MODEL_PROVENANCE_REPO_MISMATCH")
        if observed.get("revision") != spec["revision"]:
            errors.append("MADLAD_MODEL_PROVENANCE_REVISION_MISMATCH")
        if observed.get("target_tag") != spec["target_tag"]:
            errors.append("MADLAD_MODEL_PROVENANCE_TARGET_TAG_MISMATCH")
        if observed.get("declared_license") != spec["declared_license"]:
            errors.append("MADLAD_MODEL_PROVENANCE_LICENSE_MISMATCH")

    db_path = workspace / "cache" / "translation-cache.sqlite3"
    if not db_path.is_file():
        errors.append("MADLAD_SQLITE_DATABASE_MISSING")
    else:
        with (
            DurableTranslationCache(workspace / "cache") as cache,
            ReviewQueue(workspace / "cache") as review_queue,
        ):
            if cache.count() != len(INDEPENDENT_CASES):
                errors.append("MADLAD_CACHE_ROW_COUNT_MISMATCH")
            if review_queue.count("pending") or review_queue.count("approved"):
                errors.append("MADLAD_HUMAN_REVIEW_CHANGED_AUTOMATIC_RESULT")
            if review_queue.count():
                errors.append("MADLAD_REVIEW_QUEUE_NOT_EMPTY")

            case_by_id = {case.id: case for case in INDEPENDENT_CASES}
            for row in accepted:
                case = case_by_id.get(row.get("case"))
                if case is None:
                    errors.append("MADLAD_UNKNOWN_CASE:" + str(row.get("case")))
                    continue
                translated = row.get("translated", "")
                try:
                    validate_translation(case.japanese, translated, source="ja")
                    _require_semantic_fidelity(case, translated)
                except TranslationRejected as exc:
                    errors.append(
                        "MADLAD_TRANSLATION_INVALID:" + case.id + ":" + str(exc)[:220]
                    )
                    continue

                validator = lambda value, current=case: _require_semantic_fidelity(
                    current, value
                )
                cached = cache.get(
                    "ja", "es", case.japanese, quality_validator=validator
                )
                if cached != translated:
                    errors.append("MADLAD_CACHE_CONTENT_CHANGED:" + case.id)
                    continue
                try:
                    replay = cache.translate_or_get(
                        "ja",
                        "es",
                        case.japanese,
                        lambda _unused: (_ for _ in ()).throw(
                            AssertionError("MADLAD_COLD_REPLAY_CALLED_MODEL")
                        ),
                        quality_validator=validator,
                    )
                    if replay != translated:
                        errors.append("MADLAD_REPLAY_MISMATCH:" + case.id)
                except Exception as exc:
                    errors.append(
                        "MADLAD_REPLAY_FAILED:" + case.id + ":" + str(exc)[:220]
                    )

    proof = {
        "schema": "public-madlad-direct-ja-es-restart-v1",
        "candidate": candidate,
        "model_repo": spec["repo_id"],
        "model_revision": spec["revision"],
        "accepted": len(accepted),
        "required": len(INDEPENDENT_CASES),
        "backend_executed_before_restart": bool(report.get("backend_executed")),
        "models_loaded_during_restart": False,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
    _save_json(workspace / "madlad-restart-proof.json", proof)
    print(
        "MADLAD_CANDIDATE_RESTART_PROOF "
        + json.dumps(proof, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--candidate", choices=tuple(MODEL_SPECS), required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "translate":
        return translate_phase(args.candidate, args.workspace)
    return verify_phase(args.candidate, args.workspace)


if __name__ == "__main__":
    sys.exit(main())
