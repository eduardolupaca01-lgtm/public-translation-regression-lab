"""Stage6: frozen source-only Japanese RPG dialogues for genuine neural inference.

No Spanish reference translations are present in the source manifest or in
the model prompt. Public research cases are not an external blind benchmark.
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
from translation_lab.pipeline import TranslationRejected


@dataclass(frozen=True)
class Stage6Case:
    id: str
    japanese: str
    risk: str


STAGE6_CASES: tuple[Stage6Case, ...] = (
    Stage6Case(
        "npc_two_condition_variables",
        "\\N[4]「\\V[9]が0なら、扉を開けられません。\\V[9]が1なら、開けられます。」",
        "Two explicit variable conditions with opposite permissions and RPG markers",
    ),
    Stage6Case(
        "shop_tomorrow_day_after",
        "店は明日の午後8時に閉まります。あさっては午前9時に開きます。",
        "Tomorrow versus day after tomorrow and evening versus morning",
    ),
    Stage6Case(
        "search_not_found_roles",
        "みんなは彼を探していますが、まだ誰も彼を見つけていません。",
        "Everyone seeks him but nobody has found him, never reverse roles",
    ),
    Stage6Case(
        "sword_companion_return",
        "この剣は彼女のものです。袋に入れてから、彼女に返してください。",
        "Feminine Spanish object and order of putting away and returning",
    ),
    Stage6Case(
        "sibling_map_chain",
        "兄は妹に地図を渡しました。妹はその地図を私に見せました。",
        "Older brother hands the map to younger sister who shows it to speaker",
    ),
    Stage6Case(
        "permission_changed_today",
        "昨日は中に入ってもよかったですが、今日は入ってはいけません。",
        "Yesterday permitted, today forbidden",
    ),
    Stage6Case(
        "two_speakers_departure_crlf",
        "\\N[2]「私はまだ出発しません。」\r\n\\N[8]「では、私が先に行きます。」",
        "Two distinct speakers, first stays, second goes first, protected CRLF",
    ),
    Stage6Case(
        "green_appearance_apple",
        "青いリンゴがあります。見た目は緑色ですが、味は甘いです。",
        "Japanese color convention with explicit green visual and sweet taste",
    ),
    Stage6Case(
        "two_item_cost_total",
        "剣は1500円で、盾は900円です。両方買うと2400円になります。",
        "Sword, shield, individual prices and combined total",
    ),
    Stage6Case(
        "before_after_bridge_left",
        "橋の手前で止まってください。橋を渡った後、右ではなく左に曲がってください。",
        "Stop before bridge, cross, turn left not right",
    ),
    Stage6Case(
        "files_delete_only_old",
        "古いファイルは消してもいいですが、新しいファイルは絶対に消さないでください。",
        "Old file may be deleted, new file absolutely must not be deleted",
    ),
    Stage6Case(
        "herb_qty_condition",
        "薬草を三つ以上持っていたら、一つ売ってください。二つしかなければ、売らないでください。",
        "If at least three sell one; if only two sell none",
    ),
    Stage6Case(
        "rebook_saturday_not_thursday",
        "予約は木曜日ではなく土曜日の朝に変更しました。金曜日には来ないでください。",
        "Thursday cancelled, Saturday morning chosen, Friday prohibited",
    ),
    Stage6Case(
        "train_one_hour_delay",
        "電車が一時間遅れたので、会議の開始は午前10時から11時に変わりました。",
        "One-hour train delay causes meeting start to change from 10 to 11 AM",
    ),
    Stage6Case(
        "luggage_opposite_conditions",
        "荷物を受付に置くなら、部屋には持ち込まないでください。部屋に持って行くなら、受付には置かないでください。",
        "Reception versus room, two exclusive conditional instructions",
    ),
    Stage6Case(
        "two_speakers_ask_sara",
        "\\N[5]「サラが鍵を持っています。」\r\n\\N[3]「では、トムではなくサラに聞きましょう。」",
        "Sara has key, ask Sara not Tom, two protected speakers and CRLF",
    ),
)


def source_sets_disjoint() -> bool:
    current = [c.japanese for c in STAGE6_CASES]
    previous = (
        [c.japanese for c in INDEPENDENT_CASES]
        + [c.japanese for c in HOLDOUT_CASES]
        + [c.japanese for c in STRESS_CASES]
        + [c.japanese for c in STAGE5_CASES]
    )
    return (
        len(STAGE6_CASES) == 16
        and len(current) == len(set(current))
        and len({c.id for c in STAGE6_CASES}) == len(current)
        and not (set(current) & set(previous))
    )


def manifest() -> dict:
    entries = [
        {"case": case.id, "source": case.japanese, "risk": case.risk}
        for case in STAGE6_CASES
    ]
    raw = json.dumps(entries, ensure_ascii=False, sort_keys=True)
    return {
        "schema": "ja-es-stage6-sixteen-dialogues-source-manifest-v1",
        "count": len(entries),
        "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "source_only": True,
        "spanish_reference_provided_to_model": False,
        "published_research_not_blind": True,
        "model_executed": False,
        "human_bilingual_approval": False,
        "cases": entries,
    }


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(c for c in normalized if not unicodedata.combining(c))


# The checks below are conservative: they catch missing indispensable
# concepts and known role inversions, but cannot prove every nuance. Exact
# spelling or one specific Spanish sentence must never be required.
REQUIRED: dict[str, tuple[tuple[str, str], ...]] = {
    "npc_two_condition_variables": (
        (r"\b(?:si|en\s+caso\s+de)\b", "VARIABLE_IF_CLAUSE_MISSING"),
        (r"\b(?:0|cero)\b", "VARIABLE_ZERO_LOST"),
        (r"\b(?:1|uno)\b", "VARIABLE_ONE_LOST"),
        (r"\b(?:puerta|porton)\b", "DOOR_LOST"),
        (r"\b(?:no\s+(?:se\s+puede|puedes|puede|podras|podra|sera\s+posible)|imposible|"
         r"no\s+(?:abrir|abrira|abriras))\b", "ZERO_BLOCKING_ACTION_LOST"),
    ),
    "shop_tomorrow_day_after": (
        (r"\bmanana\b", "TOMORROW_LOST"),
        (r"\b(?:pasado\s+manana|dia\s+siguiente|dos\s+dias)\b", "DAY_AFTER_TOMORROW_LOST"),
        (r"\b(?:8|ocho)\b", "EIGHT_PM_MISSING"),
        (r"\b(?:9|nueve)\b", "NINE_AM_MISSING"),
    ),
    "search_not_found_roles": (
        (r"\b(?:todos|todas|gente|personas)\b", "SEARCHERS_MISSING"),
        (r"\b(?:busc|encontr)\w*\b", "SEARCH_ACTION_MISSING"),
        (r"\b(?:nadie|ninguna\s+persona)\b", "NO_ONE_MISSING"),
        (r"\b(?:encontr|hall|localiz)\w*\b", "FIND_ACTION_MISSING"),
    ),
    "sword_companion_return": (
        (r"\b(?:espada|sable)\b", "SWORD_OBJECT_MISSING"),
        (r"\b(?:ella|suya)\b", "FEMALE_OWNER_LOST"),
        (r"\b(?:bolsa|funda|estuche|saco)\b", "BAG_MISSING"),
        (r"\b(?:devuel|regres|entreg)\w*\b", "RETURN_ACTION_LOST"),
    ),
    "sibling_map_chain": (
        (r"\b(?:hermano\s+mayor)\b", "OLDER_BROTHER_LOST"),
        (r"\b(?:hermana\s+menor|hermanita)\b", "YOUNGER_SISTER_LOST"),
        (r"\bmapa\b", "MAP_OBJECT_LOST"),
        (r"\b(?:mostr|ensen|exhib)\w*\b", "SHOW_ACTION_LOST"),
    ),
    "permission_changed_today": (
        (r"\bayer\b", "YESTERDAY_LOST"),
        (r"\bhoy\b", "TODAY_LOST"),
        (r"\b(?:pod[ie]|podr|permit|autoriz)\w*\b", "PAST_PERMISSION_LOST"),
        (r"\b(?:no|prohib|impid)\w*\b", "CURRENT_PROHIBITION_LOST"),
    ),
    "two_speakers_departure_crlf": (
        (r"\b(?:todavia|aun)\b", "FIRST_NOT_YET_LOST"),
        (r"\b(?:no|ni)\b", "FIRST_DEPARTURE_NEGATION_LOST"),
        (r"\b(?:primero|antes|adelante|por\s+delante)\b", "SECOND_GOES_FIRST_LOST"),
    ),
    "green_appearance_apple": (
        (r"\bmanzan\w*\b", "APPLE_MISSING"),
        (r"\bverde\w*\b", "VISUAL_GREEN_LOST"),
        (r"\b(?:dulce|dulces)\b", "SWEET_TASTE_LOST"),
    ),
    "two_item_cost_total": (
        (r"\b1500\b", "SWORD_PRICE_MISSING"),
        (r"\b900\b", "SHIELD_PRICE_MISSING"),
        (r"\b2400\b", "COMBINED_PRICE_MISSING"),
        (r"\b(?:espada|sable)\b", "SWORD_MISSING"),
        (r"\b(?:escudo)\b", "SHIELD_MISSING"),
    ),
    "before_after_bridge_left": (
        (r"\bpuente\b", "BRIDGE_MISSING"),
        (r"\b(?:antes|frente|delante|previo|previa)\b", "STOP_BEFORE_BRIDGE_LOST"),
        (r"\b(?:izquierda)\b", "LEFT_DIRECTION_LOST"),
        (r"\b(?:derecha)\b", "NEGATED_RIGHT_DIRECTION_LOST"),
    ),
    "files_delete_only_old": (
        (r"\b(?:viej[oa]s?|antigu[oa]s?)\b", "OLD_FILE_LOST"),
        (r"\bnuev[oa]s?\b", "NEW_FILE_LOST"),
        (r"\b(?:archivos?|ficheros?)\b", "FILE_LOST"),
        (r"\b(?:elimin|borr|suprim)\w*\b", "DELETION_ACTION_LOST"),
        (r"\b(?:no|nunca|jamas|prohibid)\w*\b", "NEW_FILE_PROHIBITION_LOST"),
    ),
    "herb_qty_condition": (
        (r"\b(?:hierba|hierbas|plantas)\b", "HERBS_LOST"),
        (r"\b(?:tres|3)\b", "THREE_THRESHOLD_LOST"),
        (r"\b(?:dos|2)\b", "TWO_THRESHOLD_LOST"),
        (r"\b(?:una|uno|1)\b", "ONE_ITEM_TO_SELL_LOST"),
        (r"\b(?:si|en\s+caso)\b", "QUANTITY_CONDITIONS_LOST"),
        (r"\b(?:no|ningun|nada)\b", "TWO_ITEMS_NO_SALE_LOST"),
    ),
    "rebook_saturday_not_thursday": (
        (r"\bjueves\b", "THURSDAY_LOST"),
        (r"\bsabado\b", "SATURDAY_LOST"),
        (r"\bviernes\b", "FRIDAY_LOST"),
        (r"\b(?:manana|temprano)\b", "MORNING_LOST"),
        (r"\b(?:no|sino|en\s+lugar)\b", "NEGATED_DAY_CONTRAST_LOST"),
    ),
    "train_one_hour_delay": (
        (r"\b(?:tren|ferrocarril)\b", "TRAIN_LOST"),
        (r"\b(?:retras|demor|tard)\w*\b", "DELAY_LOST"),
        (r"\b(?:una\s+hora|1\s+hora)\b", "ONE_HOUR_DELAY_LOST"),
        (r"\b(?:10|diez)\b", "ORIGINAL_TEN_MISSING"),
        (r"\b(?:11|once)\b", "NEW_ELEVEN_MISSING"),
    ),
    "luggage_opposite_conditions": (
        (r"\b(?:equipaje|maleta|maletas)\b", "LUGGAGE_MISSING"),
        (r"\b(?:recepcion|mostrador)\b", "RECEPTION_MISSING"),
        (r"\b(?:habitacion|cuarto)\b", "ROOM_MISSING"),
        (r"\b(?:si|en\s+caso)\b", "CONDITIONAL_BRANCH_MISSING"),
        (r"\b(?:no|evita|prohibid)\w*\b", "EXCLUSIVE_PROHIBITION_MISSING"),
    ),
    "two_speakers_ask_sara": (
        (r"\bsara\b", "SARA_MISSING"),
        (r"\btom\b", "TOM_MISSING"),
        (r"\b(?:llave|llaves)\b", "KEY_MISSING"),
        (r"\b(?:pregunt|consult|hablar)\w*\b", "ASK_ACTION_MISSING"),
        (r"\b(?:no|sino|en\s+lugar)\b", "ASK_SARA_NOT_TOM_LOST"),
    ),
}


def _semantic_errors(case: Stage6Case, translation: str) -> list[str]:
    value = _fold(translation)
    errors: list[str] = []
    for pattern, code in REQUIRED[case.id]:
        if not re.search(pattern, value):
            errors.append(code)
    if case.id == "npc_two_condition_variables":
        # Both opposing conditions must survive, including their distinct
        # outcomes. The source has two conditional sentences.
        if len(re.findall(r"\bsi\b|\ben\s+caso\b", value)) < 2:
            errors.append("TWO_EXPLICIT_VARIABLE_CONDITIONS_MISSING")
    if case.id == "search_not_found_roles":
        # 'Todos lo buscan, pero aún no lo han encontrado' expresses that
        # none of the searchers found him: it is not a role inversion.
        # Permit this general Spanish collective paraphrase only when
        # the searching collective AND the object pronoun are explicit.
        collective = re.search(
            r"\b(?:todos|todas|todo\s+el\s+mundo|toda\s+la\s+gente)\b", value
        )
        collective_not_found = re.search(
            r"\bno\s+(?:lo|le)\s+han\s+"
            r"(?:encontrado|hallado|localizado)\b", value
        )
        if collective and collective_not_found:
            errors = [e for e in errors if e not in (
                "NO_ONE_MISSING", "SEARCHERS_MISSING"
            )]
        if re.search(
            r"\b(?:el|ella)\s+no\s+(?:ha|habia|habia\s+logrado)\s+"
            r"encontrar?\w*\s+a\s+nadie\b", value
        ) or re.search(
            r"\b(?:el|ella)\s+no\s+ha\s+encontrado\s+a\s+nadie\b", value
        ):
            errors.append("FOUND_PERSON_ROLE_REVERSED")
    if case.id == "sword_companion_return":
        if re.search(r"\b(?:devuelvelo|devolvelo|devuelvalo|regresalo)\b", value):
            errors.append("SPANISH_SWORD_OBJECT_GENDER_WRONG")
    if case.id == "files_delete_only_old":
        if re.search(r"\b(?:no\s+borre|no\s+elimine)\s+(?:el|un)\s+archivo\s+viejo\b", value):
            errors.append("OLD_FILE_PERMISSION_REVERSED")
    if case.id == "green_appearance_apple":
        if re.search(r"\b(?:no\s+es\s+verde|nunca\s+verde)\b", value):
            errors.append("EXPLICIT_GREEN_APPEARANCE_NEGATED")
    # These checks apply to every game-text translation, not just an
    # individual input. Passing keywords is insufficient for Spanish grammar.
    if re.search(r"\b(?:el|un)\s+espada\b", value):
        errors.append("SPANISH_SWORD_ARTICLE_GENDER_MISMATCH")
    if "サラ" in case.japanese and (
        re.search(r"\bsara\b", value)
        and re.search(r"\bsarah\b", value)
    ):
        errors.append("INCONSISTENT_SARA_NAME_SPELLING")
    return errors


def context_review_flags(case: Stage6Case, translation: str) -> list[str]:
    """Potential nuance/fluency uncertainty, never a professional approval."""
    value = _fold(translation)
    result: list[str] = []
    if case.id == "permission_changed_today" and re.search(
        r"\bay(er)?\b.{0,80}\bpodria(?:s|mos|n)?\s+haber\s+entrado\b",
        value,
    ):
        result.append("PAST_PERMISSION_VS_COUNTERFACTUAL_POSSIBILITY_REVIEW")
    if case.id == "search_not_found_roles" and (
        re.search(r"\btodo\s+el\s+mundo\b", value)
        and re.search(r"\bno\s+lo\s+han\s+encontrado\b", value)
    ):
        result.append("COLLECTIVE_SUBJECT_AGREEMENT_REVIEW")
    if case.id == "green_appearance_apple" and (
        re.search(r"\bmanzana\s+azul\b", value)
        and re.search(r"\bverde\b", value)
    ):
        result.append("AOI_APPLE_LITERAL_COLOR_CONTEXT_REVIEW")
    return result


def require_stage6_semantics(case: Stage6Case, translation: str) -> None:
    errors = _semantic_errors(case, translation)
    if errors:
        raise TranslationRejected("STAGE6_SEMANTIC_FAILURE:" + "|".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not source_sets_disjoint():
        raise RuntimeError("STAGE6_SOURCES_OVERLAP_PREVIOUS_SET")
    frozen = manifest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        frozen, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n", encoding="utf-8")
    print("STAGE6_SOURCE_MANIFEST " + json.dumps({
        "count": frozen["count"], "sha256": frozen["sha256"],
        "spanish_reference_provided_to_model": False,
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
