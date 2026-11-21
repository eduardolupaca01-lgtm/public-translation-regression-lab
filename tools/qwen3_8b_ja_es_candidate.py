"""Evaluate a pinned Qwen3-8B model for direct Japanese -> Spanish.

The published 20-case set is used only as a development regression benchmark,
not as a blind holdout or production approval. The model is run locally through
llama.cpp; no hosted translation API or target-language reference is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import (
    TranslationRejected,
    translate_checked,
    validate_translation,
)
from translation_lab.review_queue import ReviewQueue
from tools.independent_pivot_holdout import (
    INDEPENDENT_CASES,
    SEMANTIC_POLICY_VERSION,
    _require_semantic_fidelity,
)
from translation_lab.restart import verify_candidate_persistence

MODEL_REPO = "Qwen/Qwen3-8B-GGUF"
MODEL_REVISION = "7c41481f57cb95916b40956ab2f0b139b296d974"
MODEL_FILENAME = "Qwen3-8B-Q4_K_M.gguf"
MODEL_SHA256 = "d98cdcbd03e17ce47681435b5150e34c1417f50b5c0019dd560e4882c5745785"
BASE_MODEL = "Qwen/Qwen3-8B"
DECLARED_LICENSE = "apache-2.0"
QUANTIZATION = "Q4_K_M"
LLAMA_CPP_RELEASE = "b12584"
LLAMA_CPP_ASSET = (
    "https://github.com/ggml-org/llama.cpp/releases/download/"
    "b12584/llama-b12584-bin-ubuntu-x64.tar.gz"
)
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8080
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
SERVER_CONTEXT = 4096
SERVER_THREADS = 2
PROTECT_NUMBERS = False
CONTEXTUALIZE_NAME_CODES = False
PROTECT_LITERALS_IN_CONTEXT = True
MAX_OUTPUT_TOKENS = 512

SYSTEM_PROMPT = """You are a professional Japanese-to-Spanish (Latin America) translator.
Translate the complete Japanese source faithfully and naturally. Do not summarize,
explain, embellish, infer missing facts, or add information.

Accuracy rules:
- Preserve exactly who does what, grammatical person and number, and the source's
  tense and aspect. Do not change a completed action into a habitual action.
- Preserve negation, permission, prohibition, conditions, comparisons, contrast,
  sequence, and cause-and-effect relationships.
- Preserve quantities, dates, times, currency units, colors, names, and family
  relationships, including whether a sibling is younger or older. In particular,
  妹 means "hermana menor" and 姉 means "hermana mayor"; never omit that age.
- Do not invent a recipient, speaker, object, location, or instruction. If the
  Japanese source omits the agent, prefer an impersonal Spanish construction
  ("hay que" or "se debe") unless context identifies the speaker. Never add an
  indirect-object pronoun such as "nos", "me", or "le" without a stated recipient.
- Preserve event type. 届く and 届きました mean arrive or be delivered, not publish;
  冊 counts physical books, not publication volumes.
- Translate Japanese contrast, additive, conditional, and obligation constructions
  without dropping either side or changing their logical relationship.
- Keep every Arabic digit sequence visible and exactly as written; do not hide it
  behind placeholders, add thousands separators, or spell it out. Preserve each
  number's unit and temporal qualifier. When Japanese uses number words, preserve
  their numeric meaning. Repeat currency units or meridiem when needed for clarity.
- Use clear, neutral Latin American Spanish. Preserve the source's level of
  politeness where Spanish grammar permits.
- Keep every line and sentence's meaning. Do not merge or reorder independent lines.
- Preserve original RPG control codes such as \\N[3] and \\V[12] exactly once
  and unchanged. They are game commands or variables, not numbers to translate.
  A name code represents one named character: treat it as a singular person,
  never as plural characters, a generic noun, or text to translate. Do not impose
  Japanese word order on Spanish.
- Return only the translation. Do not add a heading, quotation marks, notes, or
  commentary."""


def _post_json(url: str, payload: dict, timeout: int = 180) -> dict:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(
            "QWEN8B_SERVER_HTTP_ERROR:" + str(exc.code) + ":" + body
        ) from exc
    except URLError as exc:
        raise RuntimeError("QWEN8B_SERVER_UNAVAILABLE:" + str(exc)[:400]) from exc


class Qwen8BTranslator:
    def __init__(
        self,
        endpoint: str = SERVER_URL,
        *,
        process: subprocess.Popen | None = None,
        log_handle=None,
        request_json: Callable[[str, dict, int], dict] = _post_json,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.process = process
        self.log_handle = log_handle
        self.request_json = request_json

    @staticmethod
    def build_payload(text: str) -> dict:
        return {
            "model": "Qwen3-8B-GGUF",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Translate the following Japanese text into natural, "
                        "faithful Latin American Spanish. Return only the "
                        "translation. /no_think\n\n" + text
                    ),
                },
            ],
            "temperature": 0.0,
            "top_p": 1.0,
            "seed": 42,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "stream": False,
        }

    def translate(self, text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise TranslationRejected("QWEN8B_EMPTY_SOURCE")
        try:
            response = self.request_json(
                self.endpoint + "/v1/chat/completions",
                self.build_payload(text),
                180,
            )
        except Exception as exc:
            raise TranslationRejected(
                "QWEN8B_INFERENCE_REQUEST_FAILED:"
                + type(exc).__name__ + ":" + str(exc)[:500]
            ) from exc

        choices = response.get("choices", []) if isinstance(response, dict) else []
        if not choices or not isinstance(choices[0], dict):
            raise TranslationRejected("QWEN8B_INVALID_CHAT_COMPLETION")
        message = choices[0].get("message", {})
        output = message.get("content") if isinstance(message, dict) else None
        if not isinstance(output, str) or not output.strip():
            raise TranslationRejected("QWEN8B_EMPTY_OR_INVALID_OUTPUT")
        # No target-side repair, normalization, or rewriting is performed.
        return output.strip()

    def close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        if self.log_handle is not None:
            self.log_handle.close()


def _tail(path: Path, count: int = 35) -> str:
    if not path.is_file():
        return ""
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace").splitlines()[-count:]
    )


def _wait_for_server(process: subprocess.Popen, log_path: Path) -> None:
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                "QWEN8B_SERVER_EXITED_BEFORE_HEALTH_CHECK:\n" + _tail(log_path)
            )
        try:
            with urlopen(SERVER_URL + "/health", timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(
        "QWEN8B_SERVER_START_TIMEOUT:\n" + _tail(log_path)
    )


def _load_model(llama_server: Path, workspace: Path):
    from huggingface_hub import hf_hub_download

    model_path = Path(
        hf_hub_download(
            repo_id=MODEL_REPO,
            filename=MODEL_FILENAME,
            revision=MODEL_REVISION,
        )
    )
    digest = hashlib.sha256()
    with model_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    observed_sha = digest.hexdigest()
    if observed_sha != MODEL_SHA256:
        raise RuntimeError("QWEN8B_GGUF_SHA256_MISMATCH:" + observed_sha)

    if not llama_server.is_file():
        raise RuntimeError("QWEN8B_LLAMA_SERVER_BINARY_MISSING:" + str(llama_server))

    log_path = workspace / "llama-server.log"
    log_handle = log_path.open("w", encoding="utf-8")
    command = [
        str(llama_server),
        "--model", str(model_path),
        "--host", SERVER_HOST,
        "--port", str(SERVER_PORT),
        "--ctx-size", str(SERVER_CONTEXT),
        "--threads", str(SERVER_THREADS),
        "--threads-batch", str(SERVER_THREADS),
        "--batch-size", "256",
        "--ubatch-size", "128",
        "--parallel", "1",
    ]
    process = subprocess.Popen(
        command,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_server(process, log_path)
    except Exception:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        log_handle.close()
        raise

    provenance = {
        "repo_id": MODEL_REPO,
        "revision": MODEL_REVISION,
        "filename": MODEL_FILENAME,
        "sha256": observed_sha,
        "base_model": BASE_MODEL,
        "declared_license": DECLARED_LICENSE,
        "quantization": QUANTIZATION,
        "runtime": "llama.cpp",
        "runtime_release": LLAMA_CPP_RELEASE,
        "runtime_asset": LLAMA_CPP_ASSET,
        "source": "ja",
        "target": "es-419",
        "parameters": "8B",
        "context_size": SERVER_CONTEXT,
        "threads": SERVER_THREADS,
        "temperature": 0.0,
        "seed": 42,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "protect_numbers_before_inference": PROTECT_NUMBERS,
        "contextualize_name_codes": CONTEXTUALIZE_NAME_CODES,
        "protect_literals_in_context": PROTECT_LITERALS_IN_CONTEXT,
        "model_page": "https://huggingface.co/" + BASE_MODEL,
        "gguf_page": "https://huggingface.co/" + MODEL_REPO,
        "trust_remote_code": False,
    }
    return Qwen8BTranslator(process=process, log_handle=log_handle), [provenance]


def _save_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def translate_phase(
    workspace: Path,
    llama_server: Path | None,
    model_loader=None,
) -> int:
    if workspace.exists():
        raise RuntimeError("QWEN8B_WORKSPACE_MUST_BE_NEW")
    workspace.mkdir(parents=True)
    report = {
        "schema": "public-qwen3-8b-direct-ja-es-candidate-v1",
        "kind": "REAL_NEURAL_LOCAL_QWEN3_8B_DIRECT_JA_ES_NOT_PRODUCTION_APPROVAL",
        "route": ["ja-es"],
        "expected_model": {
            "repo_id": MODEL_REPO,
            "revision": MODEL_REVISION,
            "filename": MODEL_FILENAME,
            "sha256": MODEL_SHA256,
            "base_model": BASE_MODEL,
            "declared_license": DECLARED_LICENSE,
            "quantization": QUANTIZATION,
            "runtime_release": LLAMA_CPP_RELEASE,
        },
        "evaluation_policy": {
            "cases": len(INDEPENDENT_CASES),
            "case_set_status": "published_development_regression_set_not_blind",
            "case_sources_unchanged": True,
            "semantic_policy_version": SEMANTIC_POLICY_VERSION,
            "source_paraphrases": False,
            "target_repairs": False,
            "glossary_edits": False,
            "human_approvals": False,
            "case_specific_retries": False,
            "uniform_segmentation_modes": [
                "document_context", "line_context", "sentence_context"
            ],
            "numeric_literals_sent_to_model": True,
            "numeric_literals_protected_before_inference": PROTECT_NUMBERS,
            "control_codes_protected_in_original_position": True,
            "contextual_name_code_aliases": False,
            "protected_literals_remain_in_model_context": PROTECT_LITERALS_IN_CONTEXT,
            "protected_literal_markers_must_appear_exactly_once": True,
            "protected_literal_order_may_change_for_target_grammar": True,
            "selection": "first_candidate_passing_versioned_semantic_policy",
            "all_cases_required": True,
        },
        "backend_executed": False,
        "models": [],
        "cases": [],
    }
    started = time.monotonic()
    model = None
    try:
        if model_loader is None:
            if llama_server is None:
                raise RuntimeError("QWEN8B_LLAMA_SERVER_PATH_REQUIRED")
            model, provenance = _load_model(llama_server, workspace)
        else:
            model, provenance = model_loader()
        spec = report["expected_model"]
        if (
            len(provenance) != 1
            or provenance[0].get("repo_id") != spec["repo_id"]
            or provenance[0].get("revision") != spec["revision"]
            or provenance[0].get("sha256") != spec["sha256"]
            or provenance[0].get("declared_license") != DECLARED_LICENSE
        ):
            raise RuntimeError("QWEN8B_MODEL_PROVENANCE_INVALID")
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
                                "raw_output": value[:900],
                            })
                            return value

                        try:
                            translated = translate_checked(
                                source_text,
                                model_piece,
                                source="ja",
                                protect_numbers=PROTECT_NUMBERS,
                                split_model_sentences=segmentation,
                                contextualize_name_codes=CONTEXTUALIZE_NAME_CODES,
                                protect_literals_in_context=PROTECT_LITERALS_IN_CONTEXT,
                            )
                            candidate_box.append(translated)
                            validate_translation(
                                source_text, translated, source="ja"
                            )
                            _require_semantic_fidelity(case, translated)
                            entry["accepted_segmentation_mode"] = mode
                            entry["rejected_segmentation_modes"] = rejected_modes
                            return translated
                        except Exception as exc:
                            rejected_modes.append({
                                "mode": mode,
                                "reason": type(exc).__name__ + ":" + str(exc)[:650],
                            })

                    entry["rejected_segmentation_modes"] = rejected_modes
                    raise TranslationRejected(
                        "ALL_QWEN8B_SEGMENTATION_MODES_REJECTED:"
                        + json.dumps(rejected_modes, ensure_ascii=False)[:1500]
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
                    entry["error"] = type(exc).__name__ + ":" + str(exc)[:1500]
                    item = review_queue.enqueue(
                        "ja",
                        "es",
                        case.japanese,
                        candidate_box[-1] if candidate_box else "",
                        reason=entry["error"],
                        context={
                            "case_id": case.id,
                            "semantic_policy": SEMANTIC_POLICY_VERSION,
                            "model_provenance": provenance,
                            "raw_model_attempts": attempts,
                        },
                    )
                    entry["review_item_id"] = item.item_id
                    entry["review_status"] = item.status

                report["cases"].append(entry)
                print(
                    "QWEN8B_CANDIDATE_CASE " + case.id + " "
                    + entry["status"] + " " + entry.get("error", ""),
                    flush=True,
                )

            report["cache_rows"] = cache.count()
            report["review_queue_pending"] = review_queue.count("pending")
            report["review_queue_total"] = review_queue.count()
            review_queue.export_snapshot(workspace / "review-queue.json")
    except Exception as exc:
        report["setup_error"] = type(exc).__name__ + ":" + str(exc)[:1500]
        print("QWEN8B_CANDIDATE_SETUP_FAILURE " + report["setup_error"], flush=True)
    finally:
        if model is not None and hasattr(model, "close"):
            model.close()

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
    _save_json(workspace / "qwen8b-candidate-report.json", report)
    print(
        "QWEN8B_CANDIDATE_REPORT "
        + json.dumps(report, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if report["status"] == "PASS" else 1


def verify_phase(workspace: Path) -> int:
    report_path = workspace / "qwen8b-candidate-report.json"
    if not report_path.is_file():
        print("QWEN8B_CANDIDATE_RESTART_FAIL_NO_REPORT", flush=True)
        return 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = report.get("cases", [])
    accepted = [row for row in rows if row.get("status") == "accepted"]
    errors: list[str] = []
    quality_errors: list[str] = []
    persistence_errors: list[str] = []

    if not report.get("backend_executed"):
        errors.append("QWEN8B_REAL_INFERENCE_NOT_EXECUTED")
    expected = report.get("expected_model", {})
    if expected.get("repo_id") != MODEL_REPO:
        errors.append("QWEN8B_MODEL_REPO_CHANGED")
    if expected.get("revision") != MODEL_REVISION:
        errors.append("QWEN8B_MODEL_REVISION_CHANGED")
    if expected.get("sha256") != MODEL_SHA256:
        errors.append("QWEN8B_MODEL_SHA256_CHANGED")
    if expected.get("runtime_release") != LLAMA_CPP_RELEASE:
        errors.append("QWEN8B_RUNTIME_RELEASE_CHANGED")
    if len(rows) != len(INDEPENDENT_CASES):
        errors.append("QWEN8B_CASE_COUNT_CHANGED")
    if len(accepted) != len(INDEPENDENT_CASES):
        quality_errors.append("QWEN8B_NOT_ALL_CASES_ACCEPTED")

    models = report.get("models", [])
    if len(models) != 1:
        errors.append("QWEN8B_MODEL_PROVENANCE_CARDINALITY_INVALID")
    else:
        observed = models[0]
        if observed.get("repo_id") != MODEL_REPO:
            errors.append("QWEN8B_MODEL_PROVENANCE_REPO_MISMATCH")
        if observed.get("revision") != MODEL_REVISION:
            errors.append("QWEN8B_MODEL_PROVENANCE_REVISION_MISMATCH")
        if observed.get("sha256") != MODEL_SHA256:
            errors.append("QWEN8B_MODEL_PROVENANCE_SHA256_MISMATCH")
        if observed.get("declared_license") != DECLARED_LICENSE:
            errors.append("QWEN8B_MODEL_PROVENANCE_LICENSE_MISMATCH")

    db_path = workspace / "cache" / "translation-cache.sqlite3"
    if not db_path.is_file():
        errors.append("QWEN8B_SQLITE_DATABASE_MISSING")
    else:
        with (
            DurableTranslationCache(workspace / "cache") as cache,
            ReviewQueue(workspace / "cache") as review_queue,
        ):
            persistence_errors.extend(
                verify_candidate_persistence(
                    cache,
                    review_queue,
                    accepted_count=len(accepted),
                    rejected_count=max(0, len(rows) - len(accepted)),
                    prefix="QWEN8B",
                )
            )

            case_by_id = {case.id: case for case in INDEPENDENT_CASES}
            for row in accepted:
                case = case_by_id.get(row.get("case"))
                if case is None:
                    errors.append("QWEN8B_UNKNOWN_CASE:" + str(row.get("case")))
                    continue
                translated = row.get("translated", "")
                try:
                    validate_translation(case.japanese, translated, source="ja")
                    _require_semantic_fidelity(case, translated)
                except TranslationRejected as exc:
                    quality_errors.append(
                        "QWEN8B_TRANSLATION_INVALID:" + case.id + ":" + str(exc)[:220]
                    )
                    continue

                validator = lambda value, current=case: _require_semantic_fidelity(
                    current, value
                )
                cached = cache.get(
                    "ja", "es", case.japanese, quality_validator=validator
                )
                if cached != translated:
                    persistence_errors.append("QWEN8B_CACHE_CONTENT_CHANGED:" + case.id)
                    continue
                try:
                    replay = cache.translate_or_get(
                        "ja",
                        "es",
                        case.japanese,
                        lambda _unused: (_ for _ in ()).throw(
                            AssertionError("QWEN8B_COLD_REPLAY_CALLED_MODEL")
                        ),
                        quality_validator=validator,
                    )
                    if replay != translated:
                        persistence_errors.append("QWEN8B_REPLAY_MISMATCH:" + case.id)
                except Exception as exc:
                    persistence_errors.append(
                        "QWEN8B_REPLAY_FAILED:" + case.id + ":" + str(exc)[:220]
                    )

    proof = {
        "schema": "public-qwen3-direct-ja-es-restart-v1",
        "accepted": len(accepted),
        "required": len(INDEPENDENT_CASES),
        "backend_executed_before_restart": bool(report.get("backend_executed")),
        "models_loaded_during_restart": False,
        "errors": errors,
        "quality_errors": quality_errors,
        "persistence_errors": persistence_errors,
        "quality_status": "PASS" if not quality_errors else "FAIL",
        "persistence_status": "PASS" if not persistence_errors else "FAIL",
        "status": (
            "PASS" if not errors and not quality_errors and not persistence_errors
            else "QUALITY_FAIL_PERSISTENCE_PASS"
            if not errors and not persistence_errors
            else "FAIL"
        ),
    }
    _save_json(workspace / "qwen8b-restart-proof.json", proof)
    print(
        "QWEN8B_CANDIDATE_RESTART_PROOF "
        + json.dumps(proof, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if not errors and not persistence_errors else 1


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
