"""Strict unseen Japanese-to-Spanish holdout using public NLLB research weights.

This benchmark is intentionally separate from the 12 development cases.
It runs raw model inference through structural protection only: no prepared
Spanish answers, source paraphrases, lexical repair, or case-specific retries.
NLLB is CC-BY-NC-4.0 and this is research-only evidence, not production approval.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
import time

from tools.nllb_research_acceptance import _load_public_research_model
from translation_lab.cache import DurableTranslationCache
from translation_lab.review_queue import ReviewQueue
from translation_lab.pipeline import (
    TranslationRejected,
    translate_checked,
    validate_translation,
)


@dataclass(frozen=True)
class HoldoutCase:
    id: str
    japanese: str
    required_groups: tuple[tuple[str, ...], ...]


# Ten newly authored synthetic dialogues. None of these source strings is in
# tools.neural_acceptance.CASES. The model receives only Japanese source text.
HOLDOUT_CASES: tuple[HoldoutCase, ...] = (
    HoldoutCase(
        "rainy_meeting",
        "明日の午後、駅の前で会いましょう。雨が降ったら、図書館の入口で待っています。",
        (("mañana",), ("tarde",), ("estación",), ("ver", "reun", "encontr"),
         ("lluev", "lluvia"), ("biblioteca",), ("entrada", "puerta"),
         ("esper", "aguard")),
    ),
    HoldoutCase(
        "closed_shop",
        "昨日は薬を買いに行きましたが、店はもう閉まっていました。",
        (("ayer",), ("compr",), ("medicin", "medicament", "farmacia"),
         ("tienda", "local", "establecimiento"), ("cerrad",),
         ("pero", "sin embargo", "aunque")),
    ),
    HoldoutCase(
        "sister_homework",
        "妹はまだ宿題を終えていません。終わったら、一緒に公園へ行くつもりです。",
        (("herman",), ("tarea", "deber"), ("parque",),
         ("termin",), ("no", "aún", "todavía")),
    ),
    HoldoutCase(
        "red_and_blue_apples",
        "この箱には赤いリンゴが三つ入っています。青いリンゴは一つもありません。",
        (("tres", "3"), ("manzan",), ("roj",), ("azul",),
         ("no", "ningun", "ninguna")),
    ),
    HoldoutCase(
        "teacher_and_children",
        "先生は「静かにしてください」と言いましたが、子どもたちは笑い続けました。",
        (("profesor", "maestr", "docente"), ("silencio", "call"),
         ("niñ",), ("riendo", "riéndose", "reí", "risa"), ("sigu", "continu", "segu")),
    ),
    HoldoutCase(
        "delayed_train",
        "電車が遅れているので、会議は三十分後に始まります。",
        (("tren",), ("retras", "demor", "tard"), ("reunión",),
         ("treinta", "30", "media hora"), ("minut", "hora"),
         ("porque", "como", "ya que", "debido", "así que", "por lo que", "por eso")),
    ),
    HoldoutCase(
        "brother_city_roles",
        "兄は東京に住んでいますが、私は大阪に住んでいます。",
        (("herman",), ("tokio",), ("osaka",), ("yo", "vivo")),
    ),
    HoldoutCase(
        "second_corner",
        "この道をまっすぐ進んで、二つ目の角を右に曲がってください。",
        (("recto", "derecho"), ("segund", "2"), ("esquin", "cruce"),
         ("derecha",)),
    ),
    HoldoutCase(
        "speaker_control_code",
        r"\N[7]は明日の午後3時に来ます。",
        (("mañana",), ("tarde", "atardecer"), ("3",),
         ("vendr", "lleg", "viene", "llega")),
    ),
    HoldoutCase(
        "shop_hours_line_break",
        "今日は店が休みです。\r\n明日は午前10時に開きます。",
        (("hoy",), ("tienda", "local"), ("cerrad", "descanso"),
         ("mañana",), ("10",), ("abr", "abiert")),
    ),
)


def _semantic_errors(sample: HoldoutCase, spanish: str) -> list[str]:
    folded = spanish.casefold()
    errors: list[str] = []
    missing = [
        list(group) for group in sample.required_groups
        if not any(option.casefold() in folded for option in group)
    ]
    if missing:
        errors.append("MISSING_CONCEPTS:" + json.dumps(missing, ensure_ascii=False))

    if sample.id == "rainy_meeting":
        if not re.search(
            r"\b(?:si\s+llueve|en\s+caso\s+de\s+lluvia|cuando\s+llueva)\b",
            folded,
        ):
            errors.append("RAIN_CONDITION_RELATION_LOST")
        if not re.search(r"\b(?:esper|aguard)\w*\b", folded):
            errors.append("WAITING_ACTION_LOST")
        if not re.search(r"\b(?:biblioteca)\b", folded) or not re.search(
            r"\b(?:entrada|puerta)\b", folded
        ):
            errors.append("LIBRARY_ENTRANCE_LOCATION_LOST")

    elif sample.id == "closed_shop":
        if not re.search(r"\b(?:ayer)\b", folded):
            errors.append("PAST_DAY_CHANGED")
        if not re.search(r"\b(?:compr|adquir)\w*\b", folded):
            errors.append("PURCHASE_ACTION_LOST")
        if not re.search(r"\b(?:tienda|local|establecimiento)\b", folded):
            errors.append("SHOP_ACTOR_LOST")
        if not re.search(r"\b(?:cerrad|cerró|cerraron)\w*\b", folded):
            errors.append("SHOP_CLOSED_STATE_LOST")

    elif sample.id == "sister_homework":
        clauses = [x.strip() for x in re.split(r"[.!?]+", folded) if x.strip()]
        first = clauses[0] if clauses else ""
        later = " ".join(clauses[1:])
        if not re.search(r"\b(?:herman)\w*\b", first):
            errors.append("SISTER_ACTOR_NOT_IN_HOMEWORK_CLAUSE")
        if not re.search(r"\b(?:no|aún\s+no|todavía\s+no)\b", first):
            errors.append("HOMEWORK_NEGATION_LOST")
        if not re.search(r"\b(?:termin)\w*\b", first):
            errors.append("HOMEWORK_COMPLETION_STATE_LOST")
        if not re.search(r"\b(?:cuando|una\s+vez\s+que|después\s+de\s+que)\s+(?:(?:ella)\s+)?(?:termine|haya\s+terminado|acabe|haya\s+acabado)\b", later):
            errors.append("AFTER_COMPLETION_CONDITION_LOST")
        if not re.search(r"\b(?:parque)\b", later):
            errors.append("FUTURE_PARK_DESTINATION_LOST")
        if not re.search(r"\b(?:junt\w*|con\s+ella|acompañ\w*|llevar\w*|iremos|vamos)\b", later):
            errors.append("TOGETHER_OR_COMPANION_RELATION_LOST")

    elif sample.id == "red_and_blue_apples":
        if not re.search(r"\b(?:tres|3)\b", folded) or not re.search(
            r"\bmanzan\w*\b", folded
        ) or not re.search(r"\broj\w*\b", folded):
            errors.append("RED_APPLE_COUNT_OR_COLOR_LOST")
        blue_is_negated = re.search(
            r"\b(?:no|ningun[oa]?|ni\s+una)\b.{0,55}\bazul\w*\b|"
            r"\bazul\w*\b.{0,35}\b(?:no|ningun[oa]?)\b",
            folded,
        )
        if not blue_is_negated:
            errors.append("BLUE_APPLE_ABSENCE_INVERTED")

    elif sample.id == "teacher_and_children":
        request_present = re.search(
            r"\b(?:pid|solicit|orden|dij)\w*\b.{0,70}\b(?:silencio|call\w*|cáll\w*|guard\w*|hagan)\b",
            folded,
        )
        addressed_to_children = re.search(
            r"\b(?:a\s+los\s+niños|les\s+(?:pid|solicit|orden|dij)\w*|"
            r"cállense|callen|callaran|callasen|se\s+callen|se\s+callaran|"
            r"guarden|guardaran|guardasen|hagan\s+silencio)\b",
            folded,
        )
        if not re.search(r"\b(?:profesor|maestr|docente)\b", folded) or not request_present or not addressed_to_children:
            errors.append("TEACHER_REQUEST_FOR_SILENCE_LOST")
        if re.search(r"\b(?:siguen|continúan)\s+callad\w*\b", folded):
            errors.append("TEACHER_SILENCE_QUOTE_IS_NOT_A_REQUEST")
        if not re.search(r"\bniñ\w*\b", folded):
            errors.append("CHILDREN_ACTOR_LOST")
        if not re.search(r"\b(?:ri\w*|re[ií]\w*|risa\w*)\b", folded):
            errors.append("CHILDREN_LAUGHTER_LOST")
        if not re.search(
            r"\b(?:sigu|continu|segu)\w*\b|no\s+dejaron\s+de|no\s+pararon\s+de",
            folded,
        ):
            errors.append("CONTINUING_LAUGHTER_ASPECT_LOST")

    elif sample.id == "delayed_train":
        if not re.search(
            r"\b(?:porque|como|ya\s+que|debido\s+a|así\s+que|por\s+lo\s+que|por\s+eso)\b",
            folded,
        ):
            errors.append("TRAIN_DELAY_CAUSAL_LINK_LOST")
        if not re.search(r"\b(?:comenz|comienz|empez|empiez|inici)\w*\b", folded):
            errors.append("MEETING_START_ACTION_LOST")
        if not re.search(r"\b(?:treinta|30|media\s+hora)\b", folded):
            errors.append("MEETING_DELAY_DURATION_LOST")
        if not re.search(r"\b(?:minut|hora)\w*\b", folded):
            errors.append("MEETING_DURATION_UNIT_LOST")

    elif sample.id == "brother_city_roles":
        segments = [
            x.strip() for x in re.split(
                r"\b(?:pero|mientras(?:\s+que)?|y)\b|[,;.!?]+", folded
            ) if x.strip()
        ]
        if not any(
            re.search(r"\bherman\w*\b", part) and re.search(r"\btokio\b", part)
            for part in segments
        ):
            errors.append("BROTHER_TOKYO_ROLE_MISMATCH")
        if not any(
            re.search(r"\bosaka\b", part) and
            (re.search(r"\byo\b", part) or re.search(r"\bvivo\b", part))
            for part in segments
        ):
            errors.append("SPEAKER_OSAKA_ROLE_MISMATCH")

    elif sample.id == "second_corner":
        if not re.search(r"\b(?:recto|derecho)\b", folded):
            errors.append("STRAIGHT_AHEAD_INSTRUCTION_LOST")
        if not re.search(r"\b(?:segund\w*|2)\b", folded):
            errors.append("SECOND_CORNER_ORDINAL_CHANGED")
        if not re.search(r"\b(?:esquin\w*|cruce|intersección)\b", folded):
            errors.append("CORNER_LANDMARK_LOST")
        if not re.search(r"\bderecha\b", folded):
            errors.append("RIGHT_TURN_INVERTED")

    elif sample.id == "speaker_control_code":
        if r"\N[7]" not in spanish:
            errors.append("SPEAKER_CONTROL_CODE_NOT_RESTORED")
        if not re.search(r"\b(?:mañana)\b", folded):
            errors.append("ARRIVAL_DAY_CHANGED")
        if not re.search(r"\b(?:tarde|atardecer)\b", folded):
            errors.append("AFTERNOON_PERIOD_LOST")
        clauses = [x.strip() for x in re.split(r"[.!?]+", folded) if x.strip()]
        if not any(
            re.search(r"\bmañana\b", part) and
            re.search(r"\b3\b", part) and
            re.search(r"\btarde\b", part)
            for part in clauses
        ):
            errors.append("ARRIVAL_TIME_CONTEXT_LOST")
        if not any(
            re.search(r"\b(?:vendr|lleg|viene|llega)\w*\b", part) and
            re.search(r"\bmañana\b", part)
            for part in clauses
        ):
            errors.append("ARRIVAL_ACTION_LOST")

    elif sample.id == "shop_hours_line_break":
        lines = folded.splitlines()
        if len(lines) != 2:
            errors.append("SHOP_HOURS_LINE_COUNT_CHANGED")
        else:
            if not all(re.search(p, lines[0]) for p in (
                r"\bhoy\b", r"\b(?:tienda|local)\b", r"\b(?:cerrad|descans)\w*\b"
            )):
                errors.append("TODAY_SHOP_CLOSED_CLAUSE_CHANGED")
            if not all(re.search(p, lines[1]) for p in (
                r"\bmañana\b", r"\b10\b", r"\b(?:abr|abiert)\w*\b"
            )):
                errors.append("TOMORROW_OPENING_TIME_CLAUSE_CHANGED")
    return errors


def _require_semantic_fidelity(sample: HoldoutCase, spanish: str) -> None:
    problems = _semantic_errors(sample, spanish)
    if problems:
        raise TranslationRejected(
            "UNSEEN_HOLDOUT_SEMANTIC_FAILURE:" +
            json.dumps(problems, ensure_ascii=False)
        )


def _save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def translate_phase(workspace: Path) -> int:
    if workspace.exists():
        raise RuntimeError("UNSEEN_HOLDOUT_WORKSPACE_MUST_BE_NEW")
    workspace.mkdir(parents=True)
    report = {
        "schema": "public-nllb-unseen-holdout-v1",
        "kind": "REAL_NEURAL_PUBLIC_NLLB_RESEARCH_NOT_ORIGINAL_PRIVATE_MODEL",
        "evaluation_policy": {
            "holdout_cases": len(HOLDOUT_CASES),
            "source_paraphrases": False,
            "target_language_repairs": False,
            "prepared_translations": False,
            "case_specific_retries": False,
            "structural_pipeline_only": True,
            "all_cases_required": True,
        },
        "backend_executed": False,
        "models": [],
        "cases": [],
    }
    started = time.monotonic()
    try:
        model, provenance = _load_public_research_model()
        report["backend_executed"] = True
        report["models"] = provenance
        with DurableTranslationCache(workspace / "cache") as cache, ReviewQueue(workspace / "cache") as review_queue:
            for sample in HOLDOUT_CASES:
                attempts: list[dict] = []
                entry = {
                    "case": sample.id,
                    "source": sample.japanese,
                    "status": "rejected",
                    "raw_model_attempts": attempts,
                }
                candidate_box: list[str] = []

                def producer(source_text: str) -> str:
                    def model_piece(fragment: str) -> str:
                        value = model.translate(fragment)
                        attempts.append({
                            "source_fragment": fragment[:220],
                            "raw_output": value[:500] if isinstance(value, str) else "",
                        })
                        return value
                    candidate = translate_checked(
                        source_text, model_piece, source="ja",
                        protect_numbers=True,
                        split_model_sentences=True,
                    )
                    candidate_box.append(candidate)
                    _require_semantic_fidelity(sample, candidate)
                    return candidate

                try:
                    value = cache.translate_or_get(
                        "ja", "es", sample.japanese, producer,
                        quality_validator=lambda candidate: _require_semantic_fidelity(
                            sample, candidate
                        ),
                    )
                    validate_translation(sample.japanese, value, source="ja")
                    entry["status"] = "accepted"
                    entry["translated"] = value
                    entry["sha256"] = hashlib.sha256(
                        value.encode("utf-8")
                    ).hexdigest()
                except Exception as exc:
                    entry["error"] = type(exc).__name__ + ":" + str(exc)[:700]
                    review_item = review_queue.enqueue(
                        "ja", "es", sample.japanese,
                        candidate_box[-1] if candidate_box else "",
                        reason=entry["error"],
                        context={
                            "case_id": sample.id,
                            "model_provenance": provenance,
                            "raw_model_attempts": attempts,
                        },
                    )
                    entry["review_item_id"] = review_item.item_id
                    entry["review_status"] = review_item.status
                report["cases"].append(entry)
                print(
                    "UNSEEN_HOLDOUT_CASE " + sample.id + " " +
                    entry["status"] + " " + entry.get("error", ""),
                    flush=True,
                )
            report["cache_rows"] = cache.count()
            report["review_queue_pending"] = review_queue.count("pending")
            report["review_queue_total"] = review_queue.count()
            review_queue.export_snapshot(workspace / "review-queue.json")
    except Exception as exc:
        report["setup_error"] = type(exc).__name__ + ":" + str(exc)[:900]
        print("UNSEEN_HOLDOUT_SETUP_FAILURE " + report["setup_error"], flush=True)

    report["accepted"] = sum(x["status"] == "accepted" for x in report["cases"])
    report["rejected"] = len(HOLDOUT_CASES) - report["accepted"]
    report["required"] = len(HOLDOUT_CASES)
    report["elapsed_seconds"] = round(time.monotonic() - started, 2)
    report["status"] = (
        "PASS" if report["backend_executed"] and
        report["accepted"] == len(HOLDOUT_CASES) else "FAIL"
    )
    _save_json(workspace / "holdout-report.json", report)
    print(
        "UNSEEN_HOLDOUT_REPORT " +
        json.dumps(report, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if report["status"] == "PASS" else 1


def verify_phase(workspace: Path) -> int:
    report_path = workspace / "holdout-report.json"
    if not report_path.is_file():
        print("UNSEEN_HOLDOUT_RESTART_FAIL_NO_REPORT", flush=True)
        return 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    accepted = [x for x in report.get("cases", []) if x.get("status") == "accepted"]
    case_by_id = {x.id: x for x in HOLDOUT_CASES}
    errors: list[str] = []
    if not report.get("backend_executed"):
        errors.append("REAL_NLLB_INFERENCE_NOT_EXECUTED")
    if len(accepted) != len(HOLDOUT_CASES):
        errors.append("HOLDOUT_NOT_FULLY_ACCEPTED")
    db_path = workspace / "cache" / "translation-cache.sqlite3"
    if not db_path.is_file():
        errors.append("HOLDOUT_SQLITE_DATABASE_MISSING")
    else:
        with DurableTranslationCache(workspace / "cache") as cache, ReviewQueue(workspace / "cache") as review_queue:
            if cache.count() != len(accepted) + review_queue.count("approved"):
                errors.append("HOLDOUT_REJECTED_ROW_CACHED_OR_ACCEPTED_ROW_LOST")
            for row in accepted:
                sample = case_by_id.get(row.get("case"))
                if sample is None:
                    errors.append("UNKNOWN_HOLDOUT_CASE:" + str(row.get("case")))
                    continue
                validator = lambda candidate, current=sample: _require_semantic_fidelity(
                    current, candidate
                )
                cached = cache.get(
                    "ja", "es", sample.japanese,
                    quality_validator=validator,
                )
                if cached != row.get("translated"):
                    errors.append("HOLDOUT_CACHE_CONTENT_CHANGED:" + sample.id)
                    continue
                try:
                    replay = cache.translate_or_get(
                        "ja", "es", sample.japanese,
                        lambda _unused: (_ for _ in ()).throw(
                            AssertionError("HOLDOUT_CACHE_MISS_RECALLED_MODEL")
                        ),
                        quality_validator=validator,
                    )
                    if replay != row.get("translated"):
                        errors.append("HOLDOUT_REPLAY_MISMATCH:" + sample.id)
                except Exception as exc:
                    errors.append("HOLDOUT_REPLAY_FAILED:" + sample.id + ":" + str(exc)[:180])
            for row in report.get("cases", []):
                if row.get("status") != "accepted":
                    sample = case_by_id.get(row.get("case"))
                    if sample is None:
                        errors.append("UNKNOWN_REJECTED_HOLDOUT_CASE:" + str(row.get("case")))
                    else:
                        review_item = review_queue.get(row.get("review_item_id", ""))
                        if review_item is None:
                            errors.append("REJECTED_CASE_MISSING_REVIEW_ITEM:" + sample.id)
                        elif (review_item.source, review_item.target, review_item.original) != ("ja", "es", sample.japanese):
                            errors.append("REVIEW_ITEM_SOURCE_MISMATCH:" + sample.id)
                        approved_for_case = [
                            candidate for candidate in review_queue.list_items(status="approved", limit=1000)
                            if (candidate.source, candidate.target, candidate.original) == ("ja", "es", sample.japanese)
                        ]
                        if approved_for_case:
                            approved_correction = approved_for_case[-1].correction
                            promoted = cache.get(
                                "ja", "es", sample.japanese,
                                quality_validator=lambda candidate, current=sample: _require_semantic_fidelity(current, candidate),
                            )
                            if promoted != approved_correction:
                                errors.append("HUMAN_APPROVAL_NOT_IN_ACCEPTED_CACHE:" + sample.id)
                        elif cache.get("ja", "es", sample.japanese) is not None:
                            errors.append("REJECTED_HOLDOUT_WAS_CACHED:" + sample.id)

    proof = {
        "schema": "public-nllb-unseen-holdout-restart-v1",
        "accepted": len(accepted),
        "required": len(HOLDOUT_CASES),
        "backend_executed_before_restart": bool(report.get("backend_executed")),
        "models_loaded_during_restart": False,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
    _save_json(workspace / "holdout-restart-proof.json", proof)
    print(
        "UNSEEN_HOLDOUT_RESTART_PROOF " +
        json.dumps(proof, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    return translate_phase(args.workspace) if args.phase == "translate" else verify_phase(
        args.workspace
    )


if __name__ == "__main__":
    sys.exit(main())
