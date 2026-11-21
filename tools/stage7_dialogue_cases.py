"""Stage7: disjoint source-only Japanese RPG multi-turn stress research.

Published synthetic sources, not an external blind benchmark. The Spanish
rubric is imperfect and intentionally only blocks detectable high-risk losses;
it cannot replace independent bilingual sign-off. Never modify model output.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from tools.independent_pivot_holdout import INDEPENDENT_CASES
from tools.unseen_holdout import HOLDOUT_CASES
from tools.stage4_rpg_stress_cases import STRESS_CASES
from tools.stage5_dialogue_cases import STAGE5_CASES
from tools.stage6_dialogue_cases import STAGE6_CASES
from translation_lab.pipeline import TranslationRejected


@dataclass(frozen=True)
class Stage7Case:
    id: str
    japanese: str
    risk: str


STAGE7_CASES: tuple[Stage7Case, ...] = (
    Stage7Case(
        "npc_gate_two_variables",
        "\\N[9]「\\V[3]が0なら入れません。2なら東の門を開けてください。」",
        "Variable zero forbids entry, two opens eastern gate, code protection",
    ),
    Stage7Case(
        "sara_tom_unread_letter",
        "サラはトムに手紙を渡しました。しかし、トムはまだ読んでいません。",
        "Sender Sara, recipient Tom, Tom still has not read the letter",
    ),
    Stage7Case(
        "not_first_room",
        "一階の最初の部屋ではなく、二階の三番目の部屋に鍵があります。",
        "Key is on second floor third room; first floor first room negated",
    ),
    Stage7Case(
        "shop_discount_only_today",
        "昨日は盾が900円で、今日は700円です。でも明日は売りません。",
        "Two day-specific shield prices, tomorrow no sale",
    ),
    Stage7Case(
        "rpg_two_speakers_sibling",
        "\\N[2]「兄が来たと思いました。」\r\n\\N[6]「違います。来たのは妹です。」",
        "First thought older brother arrived; second corrects younger sister arrived",
    ),
    Stage7Case(
        "torch_bridge_order",
        "橋を渡る前にたいまつを消してください。渡った後、また点けてもかまいません。",
        "Before crossing extinguish torch; after crossing permitted to relight",
    ),
    Stage7Case(
        "nobody_saw_mika_depart",
        "ミカが町を出たそうですが、誰も彼女が出ていくところを見ていません。",
        "Reported departure, but no one witnessed Mika leaving; no role reversal",
    ),
    Stage7Case(
        "younger_sister_joint_trip",
        "妹が宿題を終えたら、私は彼女と一緒に川へ行くつもりです。",
        "Younger sister completion condition; speaker intends to go with her",
    ),
    Stage7Case(
        "six_stones_sell_three",
        "青い石を六個見つけました。三個を売って、残りは持っていてください。",
        "Found six blue stones, sell three, keep remaining",
    ),
    Stage7Case(
        "old_new_docs_reception",
        "古い書類は受付に置いてください。新しい書類はまだ持っていてください。",
        "Leave old documents at reception, continue holding new documents",
    ),
    Stage7Case(
        "train_speaker_time_correction",
        "\\N[7]「電車は午後5時に出ます。」\r\n\\N[1]「いいえ、午後6時に変更されました。」",
        "One speaker says five PM, other corrects to six PM, two protected names",
    ),
    Stage7Case(
        "medicine_variable_strict_gt",
        "\\V[2]が1より大きい場合だけ、薬を一つ使ってください。それ以外なら使わないでください。",
        "Strictly greater than one, use exactly one, otherwise do not use",
    ),
)


def source_sets_disjoint() -> bool:
    now = [c.japanese for c in STAGE7_CASES]
    older = (
        [c.japanese for c in INDEPENDENT_CASES]
        + [c.japanese for c in HOLDOUT_CASES]
        + [c.japanese for c in STRESS_CASES]
        + [c.japanese for c in STAGE5_CASES]
        + [c.japanese for c in STAGE6_CASES]
    )
    return (
        len(STAGE7_CASES) == 12
        and len(set(now)) == len(now)
        and len(set(c.id for c in STAGE7_CASES)) == len(now)
        and not set(now).intersection(older)
    )


def manifest() -> dict:
    items = [{"case": c.id, "source": c.japanese, "risk": c.risk}
             for c in STAGE7_CASES]
    canonical = json.dumps(items, ensure_ascii=False, sort_keys=True)
    return {
        "schema": "ja-es-stage7-twelve-source-only-manifest-v1",
        "count": len(items),
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "source_only": True,
        "reference_spanish_provided_to_model": False,
        "model_inference_executed": False,
        "human_bilingual_approval": False,
        "evaluation_scope": "published_synthetic_research_not_blind",
        "cases": items,
    }


def _fold(text: str) -> str:
    v = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in v if not unicodedata.combining(c))


# Every rule checks concepts independent of any previous Qwen output.
# Alternative Spanish phrasings are deliberately supported where known.
REQUIRED: dict[str, tuple[tuple[str, str], ...]] = {
    "npc_gate_two_variables": (
        (r"\b(?:0|cero)\b", "VARIABLE_ZERO_MISSING"),
        (r"\b(?:2|dos)\b", "VARIABLE_TWO_MISSING"),
        (r"\b(?:si|cuando|en\s+caso)\b", "GATE_CONDITIONALS_LOST"),
        (r"\b(?:este|oriental|este\s+lado|oriente)\b", "EAST_GATE_DIRECTION_LOST"),
        (r"\b(?:puerta|portal|porton|entrada)\b", "GATE_MISSING"),
        (r"\b(?:no|prohibido|impedido|imposible)\b", "ZERO_PROHIBITION_MISSING"),
    ),
    "sara_tom_unread_letter": (
        (r"\bsara\b", "SARA_MISSING"),
        (r"\btom\b", "TOM_MISSING"),
        (r"\b(?:carta|mensaje|correspondencia)\b", "LETTER_MISSING"),
        (r"\b(?:entreg|dio|paso)\w*\b", "HANDOFF_MISSING"),
        (r"\b(?:leido|leer|leyo)\b", "READING_EVENT_MISSING"),
        (r"\b(?:todavia|aun)\b", "STILL_NOT_READ_MISSING"),
        (r"\b(?:no|sin)\b", "UNREAD_NEGATION_MISSING"),
    ),
    "not_first_room": (
        (r"\b(?:primer|primero|primera|1)\b", "FIRST_ROOM_CONTRAST_MISSING"),
        (r"\b(?:segundo|segunda|2)\b", "SECOND_FLOOR_MISSING"),
        (r"\b(?:tercer|tercera|3)\b", "THIRD_ROOM_MISSING"),
        (r"\b(?:llave|llaves)\b", "KEY_MISSING"),
        (r"\b(?:no|sino|en\s+lugar)\b", "NEGATED_LOCATION_MISSING"),
    ),
    "shop_discount_only_today": (
        (r"\b(?:ayer)\b", "YESTERDAY_MISSING"),
        (r"\b(?:hoy)\b", "TODAY_MISSING"),
        (r"\b(?:manana)\b", "TOMORROW_MISSING"),
        (r"\b900\b", "YESTERDAY_NINE_HUNDRED_MISSING"),
        (r"\b700\b", "TODAY_SEVEN_HUNDRED_MISSING"),
        (r"\b(?:escudo|escudos)\b", "SHIELD_MISSING"),
        (r"\b(?:no|dejara\s+de)\b", "TOMORROW_NOT_SELLING_MISSING"),
    ),
    "rpg_two_speakers_sibling": (
        (r"\b(?:hermano\s+mayor)\b", "OLDER_BROTHER_MISSING"),
        (r"\b(?:hermana\s+menor|hermanita)\b", "YOUNGER_SISTER_MISSING"),
        (r"\b(?:crei|pens[eoa]|pense|supuse|imagine)\b", "INITIAL_BELIEF_MISSING"),
        (r"\b(?:no|equivoc|incorrect|en\s+realidad)\b", "CORRECTION_MISSING"),
        (r"\b(?:vino|llego|llegado|venido)\b", "ARRIVAL_EVENT_MISSING"),
    ),
    "torch_bridge_order": (
        (r"\b(?:puente)\b", "BRIDGE_MISSING"),
        (r"\b(?:ant[es]+|previo)\b", "BEFORE_CROSSING_MISSING"),
        (r"\b(?:despues|tras|luego)\b", "AFTER_CROSSING_MISSING"),
        (r"\b(?:antorcha|tea|linterna)\b", "TORCH_MISSING"),
        (r"\b(?:apag|exting)\w*\b", "EXTINGUISH_MISSING"),
        (r"\b(?:encend|prend)\w*\b", "RELIGHT_MISSING"),
    ),
    "nobody_saw_mika_depart": (
        (r"\bmika\b", "MIKA_MISSING"),
        (r"\b(?:pueblo|ciudad)\b", "TOWN_MISSING"),
        (r"\b(?:nadie|ninguna\s+persona)\b", "NO_ONE_MISSING"),
        (r"\b(?:visto|vio|observo|presencio)\b", "SEEING_EVENT_MISSING"),
        (r"\b(?:sal|part|march)\w*\b", "DEPARTURE_EVENT_MISSING"),
        (r"\b(?:no|sin)\b", "NO_WITNESS_NEGATION_MISSING"),
    ),
    "younger_sister_joint_trip": (
        (r"\b(?:hermana\s+menor|hermanita)\b", "YOUNGER_SISTER_MISSING"),
        (r"\b(?:tarea|deber)\w*\b", "HOMEWORK_MISSING"),
        (r"\b(?:acaba|termin|complet)\w*\b", "COMPLETION_CONDITION_MISSING"),
        (r"\b(?:rio|riber|orilla)\w*\b", "RIVER_MISSING"),
        (r"\b(?:con\s+ella|juntos?|juntas?)\b", "COMPANION_RELATION_MISSING"),
    ),
    "six_stones_sell_three": (
        (r"\b(?:seis|6)\b", "SIX_TOTAL_MISSING"),
        (r"\b(?:tres|3)\b", "THREE_TO_SELL_MISSING"),
        (r"\b(?:azul|azules)\b", "BLUE_STONE_COLOR_MISSING"),
        (r"\b(?:piedra|piedras)\b", "STONE_OBJECT_MISSING"),
        (r"\b(?:vend|venda|vender|vende)\w*\b", "SALE_ACTION_MISSING"),
        (r"\b(?:guardar|guard|conserv|qued|mantener|mantenga)\w*\b", "KEEP_REMAINDER_MISSING"),
    ),
    "old_new_docs_reception": (
        (r"\b(?:viej[oa]s?|antigu[oa]s?)\b", "OLD_DOCUMENTS_MISSING"),
        (r"\bnuev[oa]s?\b", "NEW_DOCUMENTS_MISSING"),
        (r"\b(?:documentos?|papeles|formularios?)\b", "DOCUMENTS_MISSING"),
        (r"\b(?:recepcion|mostrador)\b", "RECEPTION_MISSING"),
        (r"\b(?:tenga|ten|mant|conserv|guard)\w*\b", "KEEP_NEW_DOCUMENTS_MISSING"),
    ),
    "train_speaker_time_correction": (
        (r"\b(?:tren|ferrocarril)\b", "TRAIN_MISSING"),
        (r"\b(?:5|cinco)\b", "FIVE_PM_MISSING"),
        (r"\b(?:6|seis)\b", "SIX_PM_MISSING"),
        (r"\b(?:no|equivoc|cambio|cambiado|modific|adelant|reprogram)\w*\b",
         "TIME_CORRECTION_MISSING"),
    ),
    "medicine_variable_strict_gt": (
        (r"\b(?:1|uno)\b", "VARIABLE_THRESHOLD_MISSING"),
        (r"\b(?:mayor\s+que|mas\s+de|superior\s+a|>)\b",
         "STRICT_GREATER_THAN_MISSING"),
        (r"\b(?:si|solo\s+cuando|en\s+caso)\b", "VARIABLE_CONDITION_MISSING"),
        (r"\b(?:una|uno|1)\b", "USE_ONE_MEDICINE_MISSING"),
        (r"\b(?:medicina|medicamento|pocion|remedio)\w*\b", "MEDICINE_MISSING"),
        (r"\b(?:no|nunca|prohibid)\w*\b", "DO_NOT_USE_OTHERWISE_MISSING"),
    ),
}


def _semantic_errors(sample: Stage7Case, translation: str) -> list[str]:
    if sample.id not in REQUIRED:
        return ["UNKNOWN_STAGE7_CASE"]
    v = _fold(translation)
    errors = [code for pattern, code in REQUIRED[sample.id]
              if not re.search(pattern, v)]
    # Universal checks of agreement and confusing recipients.
    if re.search(r"\b(?:el|un)\s+espada\b", v):
        errors.append("SPANISH_SWORD_ARTICLE_GENDER_MISMATCH")
    if "サラ" in sample.japanese and (
        re.search(r"\bsara\b", v) and re.search(r"\bsarah\b", v)
    ):
        errors.append("SARA_SARAH_INCONSISTENT_TRANSCRIPTION")
    if sample.id == "sara_tom_unread_letter" and re.search(
        r"\bsara\s+(?:no\s+)?(?:ha|habia)\s+leido\b", v
    ):
        errors.append("WRONG_PERSON_READ_THE_LETTER")
    if sample.id == "nobody_saw_mika_depart" and re.search(
        r"\b(?:ella|mika)\s+no\s+(?:ha|habia)\s+visto\s+a\s+nadie\b", v
    ):
        errors.append("MIKA_WITNESS_ROLE_REVERSED")
    if sample.id == "medicine_variable_strict_gt" and re.search(
        r"\b(?:igual\s+a|mayor\s+o\s+igual)\b", v
    ):
        errors.append("STRICT_INEQUALITY_CHANGED_TO_INCLUSIVE")
    if sample.id == "torch_bridge_order" and re.search(
        r"\bantes\b.{0,60}\b(?:encender|prender)\b", v
    ):
        errors.append("TORCH_ORDER_REVERSED")
    return errors


def require_stage7_semantics(sample: Stage7Case, translation: str) -> None:
    failures = _semantic_errors(sample, translation)
    if failures:
        raise TranslationRejected("STAGE7_SEMANTIC_FAILURE:" + "|".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not source_sets_disjoint():
        raise RuntimeError("STAGE7_SOURCE_CORPUS_OVERLAPS")
    frozen = manifest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        frozen, ensure_ascii=False, sort_keys=True, indent=2
    ) + "\n", encoding="utf-8")
    print("STAGE7_SOURCE_MANIFEST " + json.dumps({
        "count": frozen["count"], "sha256": frozen["sha256"],
        "human_bilingual_approval": False,
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
