"""Uniform two-pass neural Japanese-to-Spanish research candidate.

The pinned Qwen3-8B model performs a first translation and then a second,
uniform source-aware review pass. Both passes are neural inference, without
case-specific prompt variants, reference targets, scripted target replacement,
human approval, or model-output acceptance bypasses.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from tools import qwen3_8b_careful_ja_es_candidate as careful
from tools import qwen3_8b_ja_es_candidate as base
from translation_lab.pipeline import TranslationRejected

GENERATION_VARIANT = "uniform_neural_two_pass_revision"
SECOND_PASS_SYSTEM = careful.CAREFUL_PROMPT + """

You are independently reviewing a Japanese-to-Spanish translation for
fidelity and natural Latin American Spanish. Compare every completed action,
amount, participant, condition, prohibition, instruction, and time expression
against the Japanese source. Keep the original meaning, no invented actors,
and preserve all original game codes and line breaks. Correct any Spanish
grammar and agreement mistakes. Produce a complete corrected Spanish
translation, even if the draft has omissions. Do not add explanations."""


class TwoPassQwen8BTranslator(careful.CarefulQwen8BTranslator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.review_history: list[dict] = []

    @staticmethod
    def build_review_payload(japanese: str, draft: str) -> dict:
        return {
            "model": "Qwen3-8B-GGUF",
            "messages": [
                {"role": "system", "content": SECOND_PASS_SYSTEM},
                {"role": "user", "content": (
                    "Review the following Japanese source and its Spanish "
                    "draft. Produce only the complete, faithful, grammatical "
                    "Latin American Spanish translation. /no_think\n\n"
                    "Japanese source:\n" + japanese
                    + "\n\nSpanish draft:\n" + draft
                )},
            ],
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 513,
            "max_tokens": base.MAX_OUTPUT_TOKENS,
            "stream": False,
        }

    def translate(self, text: str) -> str:
        draft = super().translate(text)
        trace = {
            "source": text,
            "draft": draft,
            "reviewed": None,
        }
        self.review_history.append(trace)
        try:
            answer = self.request_json(
                self.endpoint + "/v1/chat/completions",
                self.build_review_payload(text, draft),
                180,
            )
        except Exception as exc:
            trace["error"] = type(exc).__name__ + ":" + str(exc)[:240]
            raise TranslationRejected(
                "QWEN8B_TWO_PASS_REVIEW_REQUEST_FAILED:" + trace["error"]
            ) from exc

        choices = answer.get("choices", []) if isinstance(answer, dict) else []
        if not choices or not isinstance(choices[0], dict):
            raise TranslationRejected("QWEN8B_TWO_PASS_INVALID_REVIEW_RESPONSE")
        message = choices[0].get("message", {})
        reviewed = message.get("content") if isinstance(message, dict) else None
        if not isinstance(reviewed, str) or not reviewed.strip():
            raise TranslationRejected("QWEN8B_TWO_PASS_EMPTY_REVIEW_RESPONSE")
        reviewed = reviewed.strip()
        trace["reviewed"] = reviewed
        # Do not silently fall back to the first-pass draft when review fails.
        return reviewed


def _load_two_pass_model(llama_server: Path, workspace: Path):
    original, provenance = base._load_model(llama_server, workspace)
    result = TwoPassQwen8BTranslator(
        endpoint=original.endpoint,
        process=original.process,
        log_handle=original.log_handle,
        request_json=original.request_json,
    )
    provenance[0].update({
        "generation_variant": GENERATION_VARIANT,
        "draft_temperature": 0.25,
        "draft_top_p": 0.93,
        "draft_seed": 512,
        "review_temperature": 0.0,
        "review_top_p": 1.0,
        "review_seed": 513,
    })
    return result, provenance


def translate_phase(workspace: Path, llama_server: Path | None) -> int:
    captured: list[TwoPassQwen8BTranslator] = []

    def loader():
        if llama_server is None:
            raise RuntimeError("QWEN8B_TWO_PASS_LLAMA_SERVER_REQUIRED")
        model, provenance = _load_two_pass_model(llama_server, workspace)
        captured.append(model)
        return model, provenance

    outcome = base.translate_phase(workspace, llama_server, model_loader=loader)
    report_path = workspace / "qwen8b-candidate-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["schema"] = "public-qwen3-8b-two-pass-ja-es-candidate-v1"
    report["kind"] = "REAL_NEURAL_TWO_PASS_QWEN3_8B_RESEARCH_ONLY"
    report["evaluation_policy"]["generation_variant"] = GENERATION_VARIANT
    report["evaluation_policy"]["two_neural_passes_for_every_request"] = True
    report["evaluation_policy"]["scripted_target_repairs"] = False
    report["evaluation_policy"]["human_approvals"] = False
    report["generation_parameters"] = {
        "draft": {"temperature": 0.25, "top_p": 0.93, "seed": 512},
        "review": {"temperature": 0.0, "top_p": 1.0, "seed": 513},
        "same_pinned_model_for_both": True,
    }
    report["neural_review_history"] = (
        captured[0].review_history if captured else []
    )
    base._save_json(report_path, report)
    print(
        "QWEN8B_TWO_PASS_RESULT "
        + json.dumps({
            "status": report.get("status"),
            "accepted": report.get("accepted"),
            "rejected": report.get("rejected"),
            "review_calls": len(report["neural_review_history"]),
        }, sort_keys=True),
        flush=True,
    )
    return outcome


def verify_phase(workspace: Path) -> int:
    result = base.verify_phase(workspace)
    path = workspace / "qwen8b-restart-proof.json"
    if path.is_file():
        proof = json.loads(path.read_text(encoding="utf-8"))
        proof["schema"] = "public-qwen3-8b-two-pass-ja-es-restart-v1"
        proof["generation_variant"] = GENERATION_VARIANT
        base._save_json(path, proof)
    return result


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
    sys.exit(main())
