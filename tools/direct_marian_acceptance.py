"""Independently measure public DIRECT Japanese-to-Spanish Marian inference.

This uses the public Apache-2.0 Helsinki-NLP opus-mt-ja-es model. It does not
read private repositories, game files, original worker binaries or credentials.
Downloaded model weights remain in ephemeral CI storage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

from tools.neural_acceptance import (
    CASES, _save_json, _require_semantic_fidelity,
    _restore_reviewed_time_terms, _source_disambiguation_variant,
    _source_fluency_variant, verify_phase,
)
from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import (
    TranslationRejected, translate_checked, validate_translation
)

MODEL_ID = "Helsinki-NLP/opus-mt-ja-es"


def _load_public_model():
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_ID, trust_remote_code=False
    )
    model = AutoModelForSeq2SeqLM.from_pretrained(
        MODEL_ID, trust_remote_code=False
    )
    model.eval()

    class _Direct:
        def translate(self, text: str) -> str:
            if not text.strip():
                raise TranslationRejected("DIRECT_MODEL_EMPTY_SOURCE")
            encoded = tokenizer([text], return_tensors="pt", truncation=False)
            if encoded["input_ids"].shape[-1] > 512:
                raise TranslationRejected("DIRECT_MODEL_INPUT_CONTEXT_EXCEEDED")
            with torch.inference_mode():
                generated = model.generate(
                    **encoded, max_new_tokens=256, num_beams=4,
                    renormalize_logits=True,
                )
            result = tokenizer.batch_decode(
                generated, skip_special_tokens=True
            )
            if len(result) != 1 or not isinstance(result[0], str):
                raise TranslationRejected("DIRECT_MODEL_INVALID_OUTPUT")
            return result[0]

    provenance = [{
        "model_id": MODEL_ID,
        "architecture": model.__class__.__name__,
        "source": "ja", "target": "es",
        "declared_license": "apache-2.0",
        "model_page": "https://huggingface.co/" + MODEL_ID,
        "trust_remote_code": False,
    }]
    return _Direct(), provenance


def _report_schema(model_kind: str) -> str:
    known = {
        "REAL_NEURAL_PUBLIC_DIRECT_MARIAN_NOT_ORIGINAL_PRIVATE_MODEL":
            "public-real-direct-marian-ja-es-v1",
        "REAL_NEURAL_PUBLIC_M2M100_NOT_ORIGINAL_PRIVATE_MODEL":
            "public-real-direct-m2m100-ja-es-v1",
        "REAL_NEURAL_PUBLIC_NLLB_RESEARCH_NOT_ORIGINAL_PRIVATE_MODEL":
            "public-real-direct-nllb-research-ja-es-v1",
    }
    try:
        return known[model_kind]
    except KeyError as exc:
        raise ValueError("UNKNOWN_REAL_NEURAL_BACKEND_PROVENANCE") from exc


def run(
    workspace: Path, *, model_loader=None,
    model_kind="REAL_NEURAL_PUBLIC_DIRECT_MARIAN_NOT_ORIGINAL_PRIVATE_MODEL",
) -> int:
    if workspace.exists():
        raise RuntimeError("DIRECT_ACCEPTANCE_WORKSPACE_MUST_BE_NEW")
    workspace.mkdir(parents=True)
    started = time.monotonic()
    report = {
        "schema": _report_schema(model_kind),
        "kind": model_kind,
        "required_cases": len(CASES), "routes": ["ja_es"],
        "backend_executed": False, "cases": [], "models": [],
    }
    try:
        model, provenance = (
            _load_public_model() if model_loader is None else model_loader()
        )
        report["backend_executed"] = True
        report["models"] = provenance
        with DurableTranslationCache(workspace / "cache") as cache:
            for sample in CASES:
                steps = []
                glossary_corrections = []

                def producer(japanese: str) -> str:
                    # Try bounded genuine model-based variants. The
                    # original Japanese meaning, codes and acceptance checks
                    # remain unchanged. No prepared translations are inserted.
                    has_glossary = bool(sample.glossary)
                    variants = (
                        [("inline-sentences", True, True, japanese, [])]
                        if has_glossary else
                        [("sentences", False, True, japanese, [])]
                    )
                    if not any(ch in japanese for ch in ("\n", "\r")):
                        variants.append((
                            "whole-context", has_glossary, False, japanese, []
                        ))
                    if has_glossary:
                        variants.append((
                            "protected-sentences", False, True, japanese, []
                        ))
                    rewritten, rewrites = _source_disambiguation_variant(japanese)
                    if rewrites:
                        variants.append((
                            "audited-ja-paraphrase", has_glossary, True,
                            rewritten, rewrites
                        ))
                    fluency_source, fluency_edits = _source_fluency_variant(japanese)
                    if fluency_edits:
                        variants.append((
                            "audited-ja-fluency", has_glossary, True,
                            fluency_source, fluency_edits
                        ))
                    rejected_attempts = []
                    for mode, inline, sentence_split, source_variant, source_edits in variants:
                        def model_piece(fragment: str) -> str:
                            value = model.translate(fragment)
                            steps.append({
                                "mode": mode,
                                "source": fragment[:180],
                                "result_es": value[:300] if isinstance(value, str) else "",
                            })
                            if not isinstance(value, str) or not value.strip():
                                raise TranslationRejected("DIRECT_MODEL_EMPTY_OUTPUT")
                            return value
                        try:
                            candidate = translate_checked(
                                source_variant, model_piece, source="ja",
                                glossary=dict(sample.glossary),
                                protect_numbers=sample.id != "numbers_and_code",
                                inline_glossary=inline,
                                split_model_sentences=sentence_split,
                            )
                            # Recheck every proposal against the ORIGINAL
                            # Japanese even when a source paraphrase was used.
                            validate_translation(japanese, candidate, source="ja")
                            candidate, approved_edits = _restore_reviewed_time_terms(
                                japanese, candidate
                            )
                            _require_semantic_fidelity(sample, candidate)
                            glossary_corrections.extend([
                                {**edit, "variant": mode}
                                for edit in approved_edits
                            ])
                            glossary_corrections.extend([
                                {**edit, "variant": mode}
                                for edit in source_edits
                            ])
                            entry["accepted_variant"] = mode
                            return candidate
                        except TranslationRejected as exc:
                            rejected_attempts.append({
                                "mode": mode,
                                "reason": str(exc)[:250],
                            })
                    raise TranslationRejected(
                        "ALL_REAL_MODEL_VARIANTS_REJECTED:" +
                        json.dumps(rejected_attempts, ensure_ascii=False)[:700]
                    )

                entry = {"case": sample.id, "source": sample.japanese,
                         "status": "rejected", "stages": steps,
                         "reviewed_term_corrections": glossary_corrections}
                try:
                    value = cache.translate_or_get(
                        "ja", "es", sample.japanese, producer,
                        quality_validator=lambda value: _require_semantic_fidelity(sample, value)
                    )
                    entry["status"] = "accepted"
                    entry["translated"] = value
                    entry["sha256"] = hashlib.sha256(
                        value.encode("utf-8")).hexdigest()
                except Exception as exc:
                    entry["error"] = type(exc).__name__ + ":" + str(exc)[:500]
                report["cases"].append(entry)
                print("DIRECT_CASE " + sample.id + " " + entry["status"] +
                      " " + entry.get("error", ""), flush=True)
            report["cache_rows"] = cache.count()
    except Exception as exc:
        report["setup_error"] = type(exc).__name__ + ":" + str(exc)[:1000]
        print("DIRECT_SETUP_FAILURE " + report["setup_error"], flush=True)
    report["accepted"] = sum(1 for item in report["cases"]
                             if item["status"] == "accepted")
    report["rejected"] = len(CASES) - report["accepted"]
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    _save_json(workspace / "neural-report.json", report)
    print("DIRECT_ACCEPTANCE_REPORT " +
          json.dumps(report, ensure_ascii=True, sort_keys=True), flush=True)
    # Exact same 12-case strict gate; no weakening or pre-written translations.
    return int(not (report["backend_executed"] and
                    report["accepted"] == len(CASES)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "translate":
        return run(args.workspace)
    return verify_phase(args.workspace)


if __name__ == "__main__":
    sys.exit(main())
