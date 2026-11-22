"""Uniform source-faithful Qwen3-8B thinking translation calibration.

This model candidate uses the SAME pinned local weights, decoding parameters,
20-case provenance gate, and ten Japanese sources as the original stage3.
Only a general translation instruction is added; no case names, reference
Spanish, model-response replacement, manual approvals or lexical edits.
The set is now published calibration data, NOT a blind holdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools import qwen3_8b_thinking_ja_es_candidate as thinking
from tools import qwen3_stage3_holdout as stage3


GENERATION_VARIANT = "uniform_spatial_agent_agreement_calibration_v1"
SOURCE_ACCURACY_GUIDANCE = """

Quality checklist to perform silently before producing the Spanish translation:
1. Keep every spatial relationship and postposition. Distinguish beside,
   behind, in front of, inside, and at a location. Never drop a spatial
   modifier when a natural Spanish prepositional phrase can express it.
2. Preserve all participants and their roles. If one person intends a joint
   action, write a grammatical singular construction with a companion; if a
   genuinely plural subject intends the action, use plural conjugation.
   Check agreement in number and gender across verbs and adverbial phrases.
3. Japanese frequently omits subjects and possessives. Resolve them only
   when the surrounding source establishes the reference. Do not invent a
   narrator, companion, parent, or additional person.
4. For natural-world objects and culturally conventional color expressions,
   distinguish literal surface color from conventional names of green,
   unripe, or ripe fruit. If the context is insufficient, preserve the
   Japanese ambiguity rather than inventing an unusual fantasy property.
5. Verify that each clause, conditional branch, tense, arrival/receipt
   action, numerical qualifier and speaker reference survives in Spanish.
   Keep all RPG code markers and source line breaks exactly as required.
6. Read the *finished* Spanish text for grammar and idiomatic Latin American
   phrasing, then output only that complete translation without explanations.

Apply these SAME principles to EVERY Japanese source, not just examples.
Do not paraphrase or borrow any other model's previous answer.
"""
SOURCE_COMPLETE_PROMPT = thinking.SYSTEM_PROMPT + SOURCE_ACCURACY_GUIDANCE
SOURCE_PROMPT_SHA256 = hashlib.sha256(
    SOURCE_COMPLETE_PROMPT.encode("utf-8")
).hexdigest()


class SourceCompleteThinkingTranslator(thinking.Qwen8BThinkingTranslator):
    @staticmethod
    def build_payload(text: str) -> dict:
        payload = thinking.Qwen8BThinkingTranslator.build_payload(text)
        payload["messages"][0]["content"] = SOURCE_COMPLETE_PROMPT
        return payload


def load_quality_model(llama_server: Path, workspace: Path):
    model, provenance = thinking._load_model(llama_server, workspace)
    original_request = model.request_json

    def request_with_cpu_deadline(url: str, payload: dict, timeout: int) -> dict:
        # The actual text/sampler are unchanged; no case-specific retries.
        return original_request(
            url, payload,
            max(timeout, stage3.THINKING_REQUEST_TIMEOUT_SECONDS),
        )

    calibrated = SourceCompleteThinkingTranslator(
        endpoint=model.endpoint,
        process=model.process,
        log_handle=model.log_handle,
        request_json=request_with_cpu_deadline,
    )
    provenance[0].update({
        "generation_variant": GENERATION_VARIANT,
        "translation_system_prompt_sha256": SOURCE_PROMPT_SHA256,
        "http_request_timeout_seconds":
            stage3.THINKING_REQUEST_TIMEOUT_SECONDS,
        "target_side_repairs": False,
        "reference_spanish_provided_to_model": False,
    })
    return calibrated, provenance


def translate_phase(
    workspace: Path,
    development_report: Path,
    development_restart: Path,
    llama_server: Path,
) -> int:
    def loader():
        return load_quality_model(llama_server, workspace)

    outcome = stage3.translate_phase(
        workspace, development_report, development_restart,
        llama_server, model_loader=loader,
    )
    result_path = workspace / "stage3-report.json"
    if result_path.is_file():
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result.update({
            "generation_variant": GENERATION_VARIANT,
            "translation_system_prompt_sha256": SOURCE_PROMPT_SHA256,
            "evaluation_scope": "published_stage3_calibration_not_blind",
            "original_model_outputs_unchanged": True,
            "reference_translations_provided_to_model": False,
            "research_only": True,
        })
        stage3._write(result_path, result)
        print(
            "STAGE4_CALIBRATION_RESULT "
            + json.dumps({
                "accepted": result.get("accepted"),
                "rejected": result.get("rejected"),
                "status": result.get("status"),
                "generation_variant": GENERATION_VARIANT,
            }, sort_keys=True),
            flush=True,
        )
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--candidate-report", type=Path)
    parser.add_argument("--candidate-restart-proof", type=Path)
    parser.add_argument("--llama-server", type=Path)
    args = parser.parse_args()
    if args.phase == "verify":
        return stage3.verify_phase(args.workspace)
    if not (args.candidate_report and args.candidate_restart_proof and args.llama_server):
        parser.error("translate requires pinned development receipts and llama-server")
    return translate_phase(
        args.workspace,
        args.candidate_report,
        args.candidate_restart_proof,
        args.llama_server,
    )


if __name__ == "__main__":
    raise SystemExit(main())
