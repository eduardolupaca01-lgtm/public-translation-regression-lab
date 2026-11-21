"""Frozen Stage5 Japanese-only multi-turn, speaker and semantic challenge set.

Sixteen synthetic examples, disjoint from the published 20 development, 10
dialogue and 12 RPG sources. Source-only model inputs: no Spanish references,
case-specific prompts, translations, fixes, or manual approvals.
The source-aware rubric is public research, NOT an external blind benchmark.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from tools.independent_pivot_holdout import INDEPENDENT_CASES
from tools.unseen_holdout import HOLDOUT_CASES
from tools.stage4_rpg_stress_cases import STRESS_CASES
from translation_lab.pipeline import TranslationRejected


@dataclass(frozen=True)
class DialogueCase:
    id: str
    japanese: str
    risk: str


STAGE5_CASES: tuple[DialogueCase, ...] = (
    DialogueCase(
        "unseen_courier",
        "配達人は昨夜来たと言いました。しかし、朝まで誰もその人を見ていませんでした。",
        "Reported speech, witness/object direction and anterior past",
    ),
    DialogueCase(
        "mika_sword_return",
        "これはミカの剣です。私のものではありません。明日、彼女に返してください。",
        "Named owner, feminine sword object, return and temporal instruction",
    ),
    DialogueCase(
        "map_we_go_together",
        "妹が地図を見つけたら、私たちは一緒に森へ行きます。まだ見つかっていません。",
        "Younger sister, conditional, explicit plural first-person",
    ),
    DialogueCase(
        "ticket_two_prices",
        "係員は切符が1200円だと言いました。しかし券売機には800円と表示されています。",
        "Two monetary values, reported claim versus machine display",
    ),
    DialogueCase(
        "two_speakers_door",
        "\\N[2]「私は扉を開けません。」\r\n\\N[5]「では、私が開けます。」",
        "Different agents, opposite intentions, two control codes and CRLF",
    ),
    DialogueCase(
        "meeting_am_not_pm",
        "会議は午後7時ではなく、午前7時に始まります。遅れないでください。",
        "Morning/evening correction and negative imperative",
    ),
    DialogueCase(
        "rain_outside_inside",
        "雨が降っていなければ外で待ってください。降り始めたら中に入ってください。",
        "Negated rain condition; entering after it starts",
    ),
    DialogueCase(
        "sara_tom_unequal_exchange",
        "サラはトムに鍵を渡しましたが、トムはサラに地図を返しませんでした。",
        "Named giver, recipient, different returned object and negation",
    ),
    DialogueCase(
        "friday_to_monday",
        "予約を金曜日から月曜日に変更しました。火曜日ではありません。",
        "Before/after weekdays with excluded Tuesday",
    ),
    DialogueCase(
        "herbs_owned_sold",
        "赤い薬草を四つ持っていますが、青い薬草は一つもありません。二つだけ売ってください。",
        "Possession, quantity, color, negated inventory, only two sold",
    ),
    DialogueCase(
        "reception_code_zero",
        "受付は明日の午前8時に開きます。\r\n\\V[4]が0なら入れません。",
        "Variable comparison to zero, consequence, time and CRLF",
    ),
    DialogueCase(
        "aoi_apple_explicit_green",
        "箱の中に青いリンゴが一つあります。色は緑に見えます。",
        "Japanese conventional blue/green and explicit green appearance",
    ),
    DialogueCase(
        "speaker_not_back_not_leaving",
        "\\N[7]「彼はまだ戻っていません。私も帰りません。」",
        "He has not returned, I will not leave; distinct agents",
    ),
    DialogueCase(
        "shop_until_four",
        "今日は午後4時まで店が開いています。明日は終日休業です。",
        "Open until four PM, closed all day tomorrow",
    ),
    DialogueCase(
        "left_stairs_not_right",
        "右の階段ではなく、左の階段を上って、二階の最初の部屋に入ってください。",
        "Right negated, left affirmed; second floor first room",
    ),
    DialogueCase(
        "children_pond_prohibition",
        "子どもは庭で遊んでもいいですが、池には近づいてはいけません。大人も同じです。",
        "Permission, prohibition, scope extended to adults",
    ),
)


def manifest() -> dict:
    rows = [
        {"case": x.id, "source": x.japanese, "risk": x.risk}
        for x in STAGE5_CASES
    ]
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    return {
        "schema": "ja-es-stage5-sixteen-source-manifest-v1",
        "count": len(rows),
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "source_only": True,
        "includes_spanish_reference_answers": False,
        "model_inference_executed": False,
        "professional_quality_approved": False,
        "status": "published_exploratory_not_blind",
        "cases": rows,
    }


def source_sets_disjoint() -> bool:
    sources = [c.japanese for c in STAGE5_CASES]
    older = (
        [c.japanese for c in INDEPENDENT_CASES]
        + [c.japanese for c in HOLDOUT_CASES]
        + [c.japanese for c in STRESS_CASES]
    )
    return len(sources) == len(set(sources)) and not (set(sources) & set(older))


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(x for x in normalized if not unicodedata.combining(x))


def _semantic_errors(sample: DialogueCase, spanish: str) -> list[str]:
    """Minimal conservative language checks for known Japanese relations.

    These inspect model output AFTER inference only, never provide answers to
    the model, and cannot establish general-purpose bilingual correctness.
    """
    t = _fold(spanish)
    errors: list[str] = []
    def require(pattern: str, issue: str):
        if not re.search(pattern, t):
            errors.append(issue)

    if sample.id == "unseen_courier":
        require(r"\b(?:nadie|ninguna\s+persona)\b", "WITNESS_NO_ONE_MISSING")
        require(r"\b(?:visto|vio|vieron|observado|encontro)\b",
                "WITNESS_SEEING_EVENT_MISSING")
        if re.search(r"\bno\s+(?:ha|habia)\s+visto\s+a\s+nadie\b", t):
            errors.append("WITNESS_ACTOR_REVERSED")
        # The original is about nobody seeing the courier; require a
        # compatible grammatical construction, not just isolated keywords.
        require(
            r"\b(?:nadie|ninguna\s+persona)\b.{0,65}\b(?:lo|le|al\s+repartidor|"
            r"al\s+mensajero|a\s+esa\s+persona)\b.{0,40}"
            r"\b(?:visto|vio|ve|observo|encontro)\b|"
            r"\bno\s+(?:lo|le)\s+ha\s+visto\s+nadie\b|"
            r"\b(?:nadie)\s+(?:habia|ha|vio|ve)\s+visto\s+(?:al\s+repartidor|"
            r"al\s+mensajero|a\s+esa\s+persona|lo)\b",
            "WITNESS_OBJECT_RELATION_UNVERIFIED",
        )

    elif sample.id == "mika_sword_return":
        require(r"\bmika\b", "SWORD_OWNER_NAME_MISSING")
        require(r"\b(?:espada|sable|arma)\b", "SWORD_OBJECT_MISSING")
        require(r"\b(?:manana|dia\s+siguiente)\b", "SWORD_RETURN_DAY_MISSING")
        if re.search(r"\b(?:devuelvelo|devuelvalo|devolvelo|regresalo)\b", t):
            errors.append("SWORD_FEMININE_OBJECT_MASCULINE_PRONOUN")

    elif sample.id == "map_we_go_together":
        require(r"\b(?:hermana\s+menor|hermanita)\b",
                "YOUNGER_SISTER_SPECIFICITY_LOST")
        require(r"\bmapa\b", "MAP_MISSING")
        require(r"\bbosque\b", "FOREST_MISSING")
        require(r"\b(?:iremos|vamos|nosotras|nosotros|partiremos)\b",
                "EXPLICIT_WE_PLURAL_AGENT_LOST")
        if re.search(r"\b(?:pienso|planeo)\s+ir\b.{0,70}\bjunt[oa]s\b", t):
            errors.append("SINGULAR_VS_PLURAL_INTENT_AGREEMENT")

    elif sample.id == "ticket_two_prices":
        require(r"\b1200\b", "ORIGINAL_TICKET_PRICE_MISSING")
        require(r"\b800\b", "MACHINE_TICKET_PRICE_MISSING")
        require(r"\b(?:boleto|billete|pasaje|entrada)\b", "TICKET_CONCEPT_MISSING")
        require(r"\b(?:maquina|expendedor|pantalla|venta)\b",
                "MACHINE_DISPLAY_RELATION_MISSING")

    elif sample.id == "two_speakers_door":
        require(r"\b(?:puerta|porton)\b", "DOOR_MISSING")
        require(r"\b(?:no\s+(?:voy|pienso|quiero)\s+a\s+abrir|no\s+abrir[ea]|"
                r"no\s+la\s+abrir[ea]|me\s+niego\s+a\s+abrir)\b",
                "FIRST_SPEAKER_REFUSAL_MISSING")
        require(r"\b(?:yo\s+(?:la\s+)?abrire|(?:la\s+)?abrire|yo\s+la\s+abro|"
                r"yo\s+la\s+voy\s+a\s+abrir|me\s+encargo)\b",
                "SECOND_SPEAKER_OFFERS_OPENING_MISSING")

    elif sample.id == "meeting_am_not_pm":
        require(r"\b(?:manana|a\.?\s*m\.?)\b", "MORNING_MEETING_TIME_MISSING")
        require(r"\b(?:tarde|noche|p\.?\s*m\.?)\b", "NEGATED_EVENING_TIME_MISSING")
        require(r"\b(?:no|sino|en\s+lugar)\b", "MEETING_TIME_CONTRAST_MISSING")

    elif sample.id == "rain_outside_inside":
        require(r"\b(?:no\s+(?:esta\s+)?lloviendo|no\s+llueve|"
                r"deja\s+de\s+llover|no\s+hay\s+lluvia)\b",
                "RAIN_NEGATIVE_CONDITION_LOST")
        require(r"\b(?:afuera|fuera|exterior)\b", "WAIT_OUTSIDE_LOST")
        require(r"\b(?:dentro|adentro|interior|entr[ea])\b", "ENTER_INSIDE_LOST")

    elif sample.id == "sara_tom_unequal_exchange":
        require(r"\bsara\b", "SARA_MISSING")
        require(r"\btom\b", "TOM_MISSING")
        require(r"\b(?:llave|llaves)\b", "GIVEN_KEY_MISSING")
        require(r"\bmapa\b", "NOT_RETURNED_MAP_MISSING")
        require(r"\b(?:no|nunca|jamas)\b", "MAP_RETURN_NEGATION_MISSING")

    elif sample.id == "friday_to_monday":
        for key, word in (("FRIDAY", "viernes"), ("MONDAY", "lunes"),
                          ("TUESDAY", "martes")):
            require(r"\b" + word + r"\b", key + "_CONTRAST_MISSING")
        require(r"\b(?:no|sino|tampoco)\b", "EXCLUDED_TUESDAY_LOST")

    elif sample.id == "herbs_owned_sold":
        require(r"\b(?:cuatro|4)\b", "FOUR_RED_HERBS_MISSING")
        require(r"\b(?:dos|2)\b", "ONLY_TWO_FOR_SALE_MISSING")
        require(r"\b(?:roja|rojo|rojas|rojos)\b", "RED_HERBS_MISSING")
        require(r"\b(?:azul|azules)\b", "BLUE_HERBS_MISSING")
        require(r"\b(?:no|ninguna|ningun|ni\s+una)\b",
                "BLUE_INVENTORY_NEGATION_LOST")

    elif sample.id == "reception_code_zero":
        require(r"\b(?:recepcion|mostrador)\b", "RECEPTION_MISSING")
        require(r"\b(?:manana|dia\s+siguiente)\b", "RECEPTION_DAY_MISSING")
        require(r"\b(?:ocho|8)\b", "RECEPTION_TIME_MISSING")
        require(r"\b0\b", "VARIABLE_ZERO_CONDITION_MISSING")
        require(r"\b(?:no\s+(?:se\s+puede|podra|podras|puedes|podes|podrian)\s+"
                r"(?:entrar|ingresar)|entrada\s+prohibida|no\s+se\s+permite\s+entrar)\b",
                "ZERO_FORBIDS_ENTRY_LOST")

    elif sample.id == "aoi_apple_explicit_green":
        require(r"\b(?:manzana|manzanas)\b", "APPLE_MISSING")
        require(r"\b(?:verde|verdes)\b", "EXPLICIT_GREEN_APPEARANCE_LOST")
        require(r"\b(?:una|un|1)\b", "SINGLE_APPLE_MISSING")

    elif sample.id == "speaker_not_back_not_leaving":
        require(r"\b(?:todavia|aun)\b", "HE_NOT_YET_RETURNED_MISSING")
        require(r"\b(?:no\s+ha\s+(?:vuelto|regresado)|no\s+volvio|no\s+regreso)\b",
                "HE_RETURN_NEGATION_LOST")
        require(r"\b(?:yo|tampoco|ni\s+yo)\b", "SPEAKER_AGENT_MISSING")
        require(r"\b(?:no\s+(?:me\s+)?(?:voy|ire|regreso|volvere|marcho)|"
                r"tampoco\s+(?:me\s+)?(?:voy|ire|regreso|volvere|marcho))\b",
                "SPEAKER_LEAVING_NEGATION_LOST")

    elif sample.id == "shop_until_four":
        require(r"\b(?:hoy)\b", "SHOP_TODAY_MISSING")
        require(r"\b(?:manana)\b", "SHOP_TOMORROW_MISSING")
        require(r"\b(?:cuatro|4)\b", "SHOP_CLOSING_HOUR_MISSING")
        require(r"\b(?:hasta)\b", "SHOP_UNTIL_CLOSING_MISSING")
        require(r"\b(?:cerrad|no\s+abr|no\s+estara\s+abiert)\w*",
                "SHOP_TOMORROW_CLOSED_MISSING")

    elif sample.id == "left_stairs_not_right":
        require(r"\b(?:izquierda)\b", "LEFT_STAIR_DIRECTION_LOST")
        require(r"\b(?:derecha)\b", "NEGATED_RIGHT_STAIR_DIRECTION_LOST")
        require(r"\b(?:segundo|segunda|2)\b", "SECOND_FLOOR_LOST")
        require(r"\b(?:primero|primera|1)\b", "FIRST_ROOM_LOST")
        require(r"\b(?:escalera|escaleras)\b", "STAIRS_OBJECT_LOST")

    elif sample.id == "children_pond_prohibition":
        require(r"\b(?:ninos|ninas|menores|chicos)\b", "CHILDREN_AGENT_LOST")
        require(r"\b(?:pueden|permitido|permite|esta\s+bien)\b",
                "GARDEN_PERMISSION_LOST")
        require(r"\b(?:estanque|laguna|laguito)\b", "POND_LOCATION_LOST")
        require(r"\b(?:no|prohibido|prohibe)\b", "POND_PROHIBITION_LOST")
        require(r"\b(?:adultos|adultas|mayores)\b", "ADULTS_SAME_RULE_LOST")
    return errors


def require_stage5_semantics(sample: DialogueCase, spanish: str) -> None:
    failures = _semantic_errors(sample, spanish)
    if failures:
        raise TranslationRejected("STAGE5_SEMANTIC_FAILURE:" + "|".join(failures))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not source_sets_disjoint():
        raise RuntimeError("STAGE5_SOURCE_OVERLAPS_PRIOR_RESEARCH")
    result = manifest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print("STAGE5_SOURCE_MANIFEST " + json.dumps({
        "count": result["count"], "sha256": result["sha256"],
        "source_only": True, "status": result["status"],
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
