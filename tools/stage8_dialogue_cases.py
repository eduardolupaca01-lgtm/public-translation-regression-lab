"""Stage8 Japanese-to-Spanish fresh synthetic RPG/dialogue evaluation.

Sources are frozen before model inference. They do not include any Spanish
reference answer, exemplar, seeded translation, or case-specific prompt.
This is a new PUBLIC SYNTHETIC challenge set, not an externally blind test.
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
from tools.stage5_dialogue_cases import STAGE5_CASES
from tools.stage6_dialogue_cases import STAGE6_CASES
from tools.stage7_dialogue_cases import STAGE7_CASES
from translation_lab.pipeline import TranslationRejected


@dataclass(frozen=True)
class Stage8Case:
    id: str
    japanese: str
    risk: str


STAGE8_CASES: tuple[Stage8Case, ...] = (
    Stage8Case(
        "letter_younger_brother",
        "ミナは弟に手紙を渡しましたが、弟はまだ彼女に返していません。",
        "Mina gives letter to younger brother; brother has not returned it",
    ),
    Stage8Case(
        "rain_stops_choice",
        "雨が止んだ場合は外で待ってください。まだ降っていれば中で待ってください。",
        "Wait outside only if rain stops; if still raining wait inside",
    ),
    Stage8Case(
        "variable_sword_sell_not_shield",
        "\\N[3]「\\V[8]が2より多ければ剣を売ってください。盾は売らないでください。」",
        "Strictly greater than two triggers sword sale but forbids shield sale",
    ),
    Stage8Case(
        "shop_hours_sunday",
        "店は午前10時に開き、午後6時に閉まります。日曜日には開きません。",
        "Opening 10 AM, closing 6 PM, Sunday closed",
    ),
    Stage8Case(
        "taro_hana_mika_witness",
        "ハナが駅を出たのを太郎は見ましたが、ミカは見ていません。",
        "Taro saw Hana leaving station, Mika did not",
    ),
    Stage8Case(
        "red_blue_bag_stones",
        "赤い袋に石が四つ、青い袋に石が一つあります。青い袋からは取らないでください。",
        "Four stones in red bag, one in blue, do not take from blue",
    ),
    Stage8Case(
        "younger_brother_bridge_station",
        "弟が橋の向こう側にいるはずです。いなければ、駅の後ろで探してください。",
        "Brother expected across bridge; otherwise look behind station",
    ),
    Stage8Case(
        "npc_first_second_speakers",
        "\\N[1]「私は先に行きません。」\r\n\\N[2]「わかりました。私が先に進みます。」",
        "One speaker refuses to go first, second volunteers; CRLF and codes",
    ),
    Stage8Case(
        "medicine_three_two_one",
        "薬を三つ買いましたが、二つは使わず、一つだけ使いました。",
        "Bought 3 medicines, 2 unused, used 1",
    ),
    Stage8Case(
        "variable_boundary_two_cases",
        "\\V[5]が4以下なら、この扉を開けないでください。5以上なら開けてもかまいません。",
        "Variable <=4 forbids opening; >=5 permits; scope and inequality",
    ),
    Stage8Case(
        "reserve_wednesday_friday",
        "予約は水曜日ではなく金曜日に変更されました。木曜日には来ないでください。",
        "Wednesday cancelled, Friday booked, Thursday prohibited",
    ),
    Stage8Case(
        "two_speakers_aria_sara",
        "\\N[4]「アリアは鍵を持っています。」\r\n\\N[8]「では、サラではなくアリアに聞きましょう。」",
        "Aria owns key; ask Aria, not Sara; two speaker codes and CRLF",
    ),
)


def source_sets_disjoint() -> bool:
    current = [row.japanese for row in STAGE8_CASES]
    previous = (
        [row.japanese for row in INDEPENDENT_CASES]
        + [row.japanese for row in HOLDOUT_CASES]
        + [row.japanese for row in STRESS_CASES]
        + [row.japanese for row in STAGE5_CASES]
        + [row.japanese for row in STAGE6_CASES]
        + [row.japanese for row in STAGE7_CASES]
    )
    return (
        len(current) == 12
        and len(set(current)) == 12
        and len({row.id for row in STAGE8_CASES}) == 12
        and not set(current).intersection(previous)
    )


def manifest() -> dict:
    cases = [
        {"case": row.id, "source": row.japanese, "risk": row.risk}
        for row in STAGE8_CASES
    ]
    sha = hashlib.sha256(
        json.dumps(cases, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "schema": "ja-es-stage8-twelve-source-only-manifest-v1",
        "count": len(cases),
        "sha256": sha,
        "source_only": True,
        "reference_spanish_provided_to_model": False,
        "model_inference_executed": False,
        "professional_quality_approved": False,
        "human_review_complete": False,
        "evaluation_scope": "published_synthetic_not_externally_blind",
        "cases": cases,
    }


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in normalized if not unicodedata.combining(c))


# Word-family checks are screens, not reference answers. Each must survive,
# but additional meaning and grammar can still fail undetected.
# Spanish permits a null subject: first-person inflection (e.g. "iré") is
# sufficient evidence; an explicit "yo" is not grammatically required.
_FIRST_PERSON_MOVEMENT = re.compile(
    r"\b(?:voy|ire|avanzo|avanzare|sigo|seguire|salgo|saldre|paso|pasare|parto|partire)\b"
    r"|\bme\s+(?:adelanto|adelantare)\b"
)
_FIRST_PERSON_MARKER = re.compile(r"\byo\b|" + _FIRST_PERSON_MOVEMENT.pattern)
_NEGATED_FIRST_PERSON_MOVEMENT = re.compile(
    r"\b(?:no|nunca)\s+(?:me\s+)?"
    r"(?:voy|ire|avanzo|avanzare|sigo|seguire|salgo|saldre|paso|pasare|parto|partire|adelanto|adelantare)\b"
)


def _speaker_segment(folded_text: str, speaker_id: int) -> str:
    """Return only one RPG speaker's text, ending at the next speaker code."""
    match = re.search(
        rf"\\n\[{speaker_id}\](.*?)(?=\\n\[\d+\]|$)",
        folded_text,
        flags=re.DOTALL,
    )
    return match.group(1) if match else ""


REQUIRED: dict[str, tuple[tuple[str, str], ...]] = {
    "letter_younger_brother": (
        (r"\bmina\b", "MINA_NAME_MISSING"),
        (r"\b(?:hermano\s+menor|hermanito)\b", "BROTHER_AGE_ROLE_MISSING"),
        (r"\b(?:carta|misiva)\b", "LETTER_OBJECT_MISSING"),
        (r"\b(?:entreg|dio|paso)\w*\b", "LETTER_GIVEN_ACTION_MISSING"),
        (r"\b(?:devolv|devuel|regres|retorn)\w*\b", "NOT_RETURNED_ACTION_MISSING"),
        (r"\b(?:no|nunca|todavia|aun|sin)\b", "RETURN_NEGATION_MISSING"),
    ),
    "rain_stops_choice": (
        (r"\b(?:lluvia|llov|llueve)\w*\b", "RAIN_MISSING"),
        (r"\b(?:pare|cesa|deja|detiene|escampa|termin)\w*\b", "RAIN_STOPS_MISSING"),
        (r"\b(?:fuera|afuera|exterior)\b", "OUTSIDE_MISSING"),
        (r"\b(?:dentro|adentro|interior)\b", "INSIDE_MISSING"),
        (r"\b(?:si|cuando|en\s+caso)\b", "CONDITION_MISSING"),
        (r"\b(?:esper|aguard)\w*\b", "WAIT_ACTION_MISSING"),
    ),
    "variable_sword_sell_not_shield": (
        (r"\b(?:2|dos)\b", "THRESHOLD_TWO_MISSING"),
        (r"\b(?:mas\s+de|mayor\s+que|superior\s+a)\b", "STRICT_GREATER_MISSING"),
        (r"\b(?:espada|sable)\b", "SWORD_OBJECT_MISSING"),
        (r"\bescudo\b", "SHIELD_OBJECT_MISSING"),
        (r"\b(?:vend|venta)\w*\b", "SELL_ACTION_MISSING"),
        (r"\b(?:no|nunca|jamas)\b", "SHIELD_NO_SALE_MISSING"),
    ),
    "shop_hours_sunday": (
        (r"\b(?:tienda|negocio|comercio|local)\b", "SHOP_MISSING"),
        (r"\b(?:10|diez)\b", "TEN_AM_MISSING"),
        (r"\b(?:6|seis)\b", "SIX_PM_MISSING"),
        (r"\bdomingos?\b", "SUNDAY_MISSING"),
        (r"\b(?:no|cerrad)\w*\b", "SUNDAY_CLOSED_MISSING"),
    ),
    "taro_hana_mika_witness": (
        (r"\btaro\b", "TARO_MISSING"),
        (r"\bhana\b", "HANA_MISSING"),
        (r"\bmika\b", "MIKA_MISSING"),
        (r"\b(?:estacion)\b", "STATION_MISSING"),
        (r"\b(?:sal|part|march)\w*\b", "DEPARTURE_MISSING"),
        (r"\b(?:vio|visto|observ|presenci)\w*\b", "WITNESS_EVENT_MISSING"),
        (r"\b(?:no|nunca)\b", "MIKA_NOT_WITNESS_MISSING"),
    ),
    "red_blue_bag_stones": (
        (r"\b(?:rojo|roja)\w*\b", "RED_BAG_MISSING"),
        (r"\b(?:azul|azules)\b", "BLUE_BAG_MISSING"),
        (r"\b(?:bolsa|saco|mochila)\b", "BAG_OBJECT_MISSING"),
        (r"\b(?:piedra|piedras)\b", "STONE_OBJECT_MISSING"),
        (r"\b(?:4|cuatro)\b", "FOUR_RED_MISSING"),
        (r"\b(?:1|uno|una)\b", "ONE_BLUE_MISSING"),
        (r"\b(?:no|prohibido|evite)\b", "DO_NOT_TAKE_FROM_BLUE_MISSING"),
    ),
    "younger_brother_bridge_station": (
        (r"\b(?:hermano\s+menor|hermanito)\b", "BROTHER_ROLE_MISSING"),
        (r"\bpuente\b", "BRIDGE_MISSING"),
        (r"\b(?:otro\s+lado|al\s+otro\s+lado|mas\s+alla)\b", "ACROSS_BRIDGE_MISSING"),
        (r"\bestacion\b", "STATION_MISSING"),
        (r"\b(?:detras|parte\s+trasera)\b", "BEHIND_STATION_MISSING"),
        (r"\b(?:si|en\s+caso)\b", "IF_NOT_THERE_MISSING"),
    ),
    "npc_first_second_speakers": (
        (r"\byo\b|" + _FIRST_PERSON_MOVEMENT.pattern, "FIRST_PERSON_MISSING"),
        (r"\b(?:no|nunca)\b", "FIRST_SPEAKER_REFUSAL_MISSING"),
        (r"\b(?:adelante|primero|antes|delante)\b", "GO_FIRST_MEANING_MISSING"),
        (r"\b(?:voy|ire|avanz|seguir|sald)\w*\b", "MOVEMENT_MISSING"),
    ),
    "medicine_three_two_one": (
        (r"\b(?:3|tres)\b", "THREE_TOTAL_MISSING"),
        (r"\b(?:2|dos)\b", "TWO_UNUSED_MISSING"),
        (r"\b(?:1|uno|una)\b", "ONE_USED_MISSING"),
        (r"\b(?:compr|adquir)\w*\b", "BOUGHT_ACTION_MISSING"),
        (r"\b(?:no|sin)\b", "TWO_UNUSED_NEGATION_MISSING"),
        (r"\b(?:medicina|medicamento|remedio|pocion)\w*\b", "ITEM_MISSING"),
    ),
    "variable_boundary_two_cases": (
        (r"\b(?:4|cuatro)\b", "LOWER_THRESHOLD_MISSING"),
        (r"\b(?:5|cinco)\b", "UPPER_THRESHOLD_MISSING"),
        (r"\b(?:menor\s+o\s+igual|como\s+maximo|no\s+supera|hasta|(?:4|cuatro)\s+o\s+menos)\b",
         "LOWER_INCLUSIVE_BOUND_MISSING"),
        (r"\b(?:mayor\s+o\s+igual|al\s+menos|como\s+minimo|desde|(?:5|cinco)\s+o\s+mas)\b",
         "UPPER_INCLUSIVE_BOUND_MISSING"),
        (r"\b(?:puerta|porton|entrada)\b", "DOOR_MISSING"),
        (r"\b(?:no|prohibid)\w*\b", "LOWER_FORBIDS_OPENING_MISSING"),
        (r"\b(?:permit|puede|podr)\w*\b|\besta\s+bien\s+(?:abrir\w*|que\s+(?:(?:la|lo)\s+)?abr\w*)\b",
         "UPPER_PERMITS_OPENING_MISSING"),
    ),
    "reserve_wednesday_friday": (
        (r"\bmiercoles\b", "WEDNESDAY_MISSING"),
        (r"\bviernes\b", "FRIDAY_MISSING"),
        (r"\bjueves\b", "THURSDAY_MISSING"),
        (r"\b(?:reserva|reservacion)\b", "RESERVATION_MISSING"),
        (r"\b(?:no|sino|en\s+lugar)\b", "NEGATED_DAY_MISSING"),
    ),
    "two_speakers_aria_sara": (
        (r"\baria\b", "ARIA_NAME_MISSING"),
        (r"\bsara\b", "SARA_NAME_MISSING"),
        (r"\b(?:llave|llaves)\b", "KEY_MISSING"),
        (r"\b(?:pregunt|consult|interrog)\w*\b", "ASK_INFORMATION_MISSING"),
        (r"\b(?:no|sino|en\s+lugar)\b", "NEGATED_SARA_RECIPIENT_MISSING"),
    ),
}


def _semantic_errors(sample: Stage8Case, spanish: str) -> list[str]:
    if sample.id not in REQUIRED:
        return ["UNKNOWN_CASE"]
    # Numeric control-code indices are NOT prose thresholds. Preserve codes
    # for structural validation, but exclude them from semantic number scans.
    folded = _fold(spanish)
    v = re.sub(r"\\[nv]\[\d+\]", "", folded)
    faults = [code for regex, code in REQUIRED[sample.id] if not re.search(regex, v)]
    if sample.id == "npc_first_second_speakers":
        first_speaker = _speaker_segment(folded, 1)
        second_speaker = _speaker_segment(folded, 2)
        if not first_speaker:
            faults.append("FIRST_SPEAKER_CODE_MISSING")
        else:
            if not _FIRST_PERSON_MARKER.search(first_speaker):
                faults.append("FIRST_SPEAKER_FIRST_PERSON_MISSING")
            if not _NEGATED_FIRST_PERSON_MOVEMENT.search(first_speaker):
                faults.append("FIRST_SPEAKER_REFUSAL_NOT_BOUND_TO_FIRST_PERSON_MOVEMENT")
            if not re.search(r"\b(?:adelante|primero|antes|delante)\b", first_speaker):
                faults.append("FIRST_SPEAKER_GO_FIRST_MEANING_MISSING")
        if not second_speaker:
            faults.append("SECOND_SPEAKER_CODE_MISSING")
        else:
            if not _FIRST_PERSON_MARKER.search(second_speaker):
                faults.append("SECOND_SPEAKER_FIRST_PERSON_MISSING")
            if not re.search(r"\b(?:entiend|entend|comprend)\w*|\b(?:de\s+acuerdo|vale|bien|ok)\b", second_speaker):
                faults.append("SECOND_SPEAKER_ACKNOWLEDGEMENT_MISSING")
            if not _FIRST_PERSON_MOVEMENT.search(second_speaker):
                faults.append("SECOND_SPEAKER_VOLUNTEER_ACTION_MISSING")
            if _NEGATED_FIRST_PERSON_MOVEMENT.search(second_speaker):
                faults.append("SECOND_SPEAKER_WRONGLY_REFUSES_TO_GO_FIRST")
            if not re.search(r"\b(?:adelante|primero|antes|delante)\b", second_speaker):
                faults.append("SECOND_SPEAKER_GO_FIRST_MEANING_MISSING")
    if sample.id == "taro_hana_mika_witness":
        if re.search(r"\bmika\s+(?:si|tambien)\s+(?:la\s+)?(?:vio|ha\s+visto)\b", v):
            faults.append("MIKA_WRONGLY_SEES_HANA")
    if sample.id == "variable_sword_sell_not_shield":
        # A negated command "no venda el escudo" is the RIGHT meaning;
        # flag only an affirmative instruction to sell the shield.
        for match in re.finditer(r"\b(?:venda|vender|vende)\s+el\s+escudo\b", v):
            preceding = v[max(0, match.start() - 35):match.start()]
            if not re.search(r"\b(?:no|nunca|jamas)\s+$", preceding):
                faults.append("SELLS_SHIELD_INSTEAD_OF_SWORD")
    if sample.id == "variable_boundary_two_cases":
        # Check which inclusive bound governs which permission, not only tokens.
        for clause in re.split(r"[.;!?]+", v):
            if re.search(r"\b(?:4|cuatro)\b", clause):
                if re.search(r"\b(?:se\s+puede|puede|permit\w*|esta\s+bien)\b.{0,25}\babr\w*\b", clause) and not re.search(r"\bno\b.{0,20}\b(?:puede|permit\w*|abr\w*)\b", clause):
                    faults.append("LOWER_BOUND_WRONGLY_PERMITS_OPENING")
            if re.search(r"\b(?:5|cinco)\b", clause):
                if re.search(
                    r"\bno\s+(?:(?:se\s+)?(?:puede|debe)\s+abrir\w*|"
                    r"(?:esta\s+bien|esta\s+permitido)\s+(?:que\s+)?"
                    r"(?:(?:la|lo)\s+)?abr\w*|abr\w*)\b",
                    clause,
                ):
                    faults.append("UPPER_BOUND_WRONGLY_FORBIDS_OPENING")
    if sample.id == "two_speakers_aria_sara":
        if re.search(r"\b(?:pregunt|consult)\w*\s+a\s+sara\b", v):
            faults.append("ASKS_SARA_INSTEAD_OF_ARIA")
    if re.search(r"\b(?:el|un)\s+espada\b", v):
        faults.append("SWORD_ARTICLE_GENDER_MISMATCH")
    return faults


def require_stage8_semantics(sample: Stage8Case, spanish: str) -> None:
    faults = _semantic_errors(sample, spanish)
    if faults:
        raise TranslationRejected("STAGE8_SEMANTIC_FAILURE:" + "|".join(faults))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not source_sets_disjoint():
        raise RuntimeError("STAGE8_JAPANESE_SOURCE_OVERLAP")
    doc = manifest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(doc, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print("STAGE8_SOURCE_MANIFEST " + json.dumps({
        "count": doc["count"], "sha256": doc["sha256"],
        "source_only": doc["source_only"],
        "professional_quality_approved": False,
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
