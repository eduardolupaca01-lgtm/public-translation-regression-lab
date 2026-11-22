"""Uniform source-only careful-prompt Qwen3-8B translation experiment.

No reference Spanish answers, post-edit substitutions or human approvals are
passed to the model. The frozen 20-case benchmark and cold cache proof remain
the same as the base candidate; only uniform generation instructions differ.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from tools import qwen3_8b_ja_es_candidate as base

CAREFUL_PROMPT = base.SYSTEM_PROMPT + """

Translate this Japanese source independently from scratch. Preserve every
predicate and its completed or continuing state; preserve numerals, agents,
negations, order, conditions, and all arrival or receipt actions. Write natural,
idiomatic Latin American Spanish with correct gender, number and prepositions.
Keep any unspecified agent of an obligation impersonal. Never invent facts or
replace a complete action with only a noun or quantity description.
Do not rely on a previous draft or a gold translation. Output only Spanish."""


class CarefulQwen8BTranslator(base.Qwen8BTranslator):
    @staticmethod
    def build_payload(text: str) -> dict:
        payload = base.Qwen8BTranslator.build_payload(text)
        payload["messages"][0]["content"] = CAREFUL_PROMPT
        payload["temperature"] = 0.25
        payload["top_p"] = 0.93
        payload["seed"] = 512
        return payload


def _load_careful_model(llama_server: Path, workspace: Path):
    original, provenance = base._load_model(llama_server, workspace)
    wrapped = CarefulQwen8BTranslator(
        endpoint=original.endpoint,
        process=original.process,
        log_handle=original.log_handle,
        request_json=original.request_json,
    )
    provenance[0].update({
        "temperature": 0.25,
        "top_p": 0.93,
        "seed": 512,
        "generation_variant": "uniform_source_only_careful_prompt",
    })
    return wrapped, provenance


def translate_phase(workspace: Path, llama_server: Path | None) -> int:
    def load():
        if llama_server is None:
            raise RuntimeError("CAREFUL_QWEN8B_LLAMA_SERVER_REQUIRED")
        return _load_careful_model(llama_server, workspace)

    result = base.translate_phase(workspace, llama_server, model_loader=load)
    report_path = workspace / "qwen8b-candidate-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["schema"] = "public-qwen3-8b-careful-ja-es-candidate-v1"
    report["kind"] = "REAL_NEURAL_QWEN3_8B_UNIFORM_CAREFUL_PROMPT_RESEARCH_ONLY"
    report["evaluation_policy"]["generation_variant"] = (
        "uniform_source_only_careful_prompt"
    )
    report["evaluation_policy"]["case_specific_retries"] = False
    report["generation_parameters"] = {
        "temperature": 0.25, "top_p": 0.93, "seed": 512,
        "source_only_prompt": True,
    }
    base._save_json(report_path, report)
    print(
        "QWEN8B_CAREFUL_CANDIDATE_RESULT "
        + json.dumps({
            "accepted": report.get("accepted"),
            "rejected": report.get("rejected"),
            "status": report.get("status"),
        }, sort_keys=True),
        flush=True,
    )
    return result


def verify_phase(workspace: Path) -> int:
    result = base.verify_phase(workspace)
    proof_path = workspace / "qwen8b-restart-proof.json"
    if proof_path.is_file():
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
        proof["schema"] = "public-qwen3-8b-careful-ja-es-restart-v1"
        proof["generation_variant"] = "uniform_source_only_careful_prompt"
        base._save_json(proof_path, proof)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--llama-server", type=Path)
    args = parser.parse_args()
    if args.phase == "translate":
        return translate_phase(args.workspace, args.llama_server)
    return verify_phase(args.workspace)


if __name__ == "__main__":
    sys.exit(main())
