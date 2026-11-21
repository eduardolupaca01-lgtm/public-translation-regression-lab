"""Independent second-stage 20-case Japanese -> English -> Spanish quality gate.

The synthetic source dialogues are new and disjoint from the first ten-case
pivot holdout and the development corpus. The models receive only Japanese
source text. This evaluator uses independent semantic checks, structural
validation, raw-output receipts, and a cold SQLite replay. It does not contain
prepared target translations, glossary repairs, or human approvals.
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
import unicodedata

from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import (
    TranslationRejected,
    contextualize_name_code_source,
    restore_contextual_name_codes,
    translate_checked,
    validate_translation,
)
from translation_lab.review_queue import ReviewQueue
from translation_lab.restart import verify_candidate_persistence

JA_EN_MODEL_ID = "Helsinki-NLP/opus-mt-ja-en"
EN_ES_MODEL_ID = "Helsinki-NLP/opus-mt-en-es"
DECLARED_LICENSE = "apache-2.0"


@dataclass(frozen=True)
class IndependentCase:
    id: str
    japanese: str
    required_groups: tuple[tuple[str, ...], ...]


# Authored independently for stage two. Do not copy cases from the first
# holdout or expose target-language references to the inference process.
SEMANTIC_POLICY_VERSION = "independent_holdout_v2_semantic_calibration"


INDEPENDENT_CASES: tuple[IndependentCase, ...] = (
    IndependentCase(
        "meeting_time_contrast",
        "会議は午後二時ではなく、午後四時に始まります。",
        (("reunión", "junta"), ("empez", "empiez", "comenz", "comienz", "inici"),
         ("4", "cuatro", "16:00"), ("2", "dos", "14:00"),
         ("tarde", "p.m.", "pm")),
    ),
    IndependentCase(
        "key_ownership",
        "田中さんは鍵を持っていますが、佐藤さんは持っていません。",
        (("tanaka",), ("sato",), ("llave",), ("tiene", "posee"), ("no",)),
    ),
    IndependentCase(
        "bridge_left_turn",
        "橋を渡った後、最初の信号を左に曲がってください。",
        (("puente",), ("semáforo", "señal de tráfico"),
         ("primer", "primera"), ("izquierda",), ("cruz", "atraves")),
    ),
    IndependentCase(
        "envelope_color_counts",
        "赤い封筒が二枚、青い封筒が五枚あります。",
        (("sobre", "sobres"), ("rojo",), ("azul",),
         ("2", "dos"), ("5", "cinco")),
    ),
    IndependentCase(
        "file_do_not_delete",
        "このファイルは削除しないでください。別のフォルダーに保存してください。",
        (("archivo", "fichero"), ("no",), ("bor", "elimin", "suprim"),
         ("guard", "almacen"), ("otra carpeta", "carpeta distinta",
                                "carpeta diferente")),
    ),
    IndependentCase(
        "email_before_meeting",
        "先にメールを送ってから、会議室に来てください。",
        (("correo", "email"), ("reunión", "conferencia"), ("sala de reuniones",
                                             "sala de reunión", "sala de conferencias"),
         ("env", "mand"), ("primero", "antes", "después", "luego")),
    ),
    IndependentCase(
        "ordered_books_arrived",
        "注文した本は三冊ではなく、二冊届きました。",
        (("libro",), ("3", "tres"), ("2", "dos"),
         ("lleg", "recib"), ("ped", "orden")),
    ),
    IndependentCase(
        "colder_today_weaker_wind",
        "今日は昨日より寒いですが、風は弱いです。",
        (("hoy",), ("ayer",), ("frío",), ("viento",), ("débil", "suave", "flojo")),
    ),
    IndependentCase(
        "children_permission_and_prohibition",
        "子どもたちはこの部屋に入ってもいいですが、走ってはいけません。",
        (("niño", "menor", "infante"), ("habitación", "sala"),
         ("entr",), ("corr",), ("no",)),
    ),
    IndependentCase(
        "blue_umbrella_owner",
        "青い傘は私のものではなく、妹のものです。",
        (("paraguas",), ("azul",), ("mío", "pertenece"), ("hermana",),
         ("menor", "pequeña", "hermanita")),
    ),
    IndependentCase(
        "shop_yesterday_today",
        "昨日は店が開いていましたが、今日は休業です。",
        (("ayer",), ("hoy",), ("tienda", "local"),
         ("abiert",), ("cerrad", "descanso")),
    ),
    IndependentCase(
        "woman_by_window",
        "窓のそばに座っている女性は、私の新しい先生です。",
        (("mujer",), ("ventana",), ("sentad",),
         ("profesora", "maestra", "docente"), ("nueva",)),
    ),
    IndependentCase(
        "reservation_tuesday_to_thursday",
        "予約は火曜日から木曜日に変更されました。",
        (("reserva", "cita"), ("martes",), ("jueves",),
         ("camb", "modific", "traslad", "pas")),
    ),
    IndependentCase(
        "cooked_and_washed_dishes",
        "彼は料理だけでなく、皿洗いもしました。",
        (("cocin", "prepar"), ("lav",), ("plato",), ("también", "además",
                                            "no solo", "sino también")),
    ),
    IndependentCase(
        "check_document_before_signing",
        "この書類に署名する前に、内容を確認しなければなりません。",
        (("documento", "formulario"), ("firm",), ("contenido",),
         ("revis", "verific", "comprob"), ("debe", "tiene que",
                                           "es necesario", "hay que", "se debe")),
    ),
    IndependentCase(
        "miss_train_take_taxi",
        "もし電車に間に合わなければ、タクシーで行きます。",
        (("tren",), ("taxi",), ("si",), ("pierde", "pierd", "perd", "lleg", "logr", "no llega",
                                        "no alcanza")),
    ),
    IndependentCase(
        "luggage_reception_or_room",
        "荷物は受付に預けましたか。それとも部屋に持って行きましたか。",
        (("equipaje", "maleta", "bolso"), ("recepción", "mostrador"),
         ("habitación", "cuarto"), ("dej", "deposit"),
         ("llev", "transport")),
    ),
    IndependentCase(
        "called_but_no_reply",
        "私は彼に電話しましたが、彼はまだ返事をしていません。",
        (("llam",), ("no",), ("respond", "contest"),
         ("todavía", "aún")),
    ),
    IndependentCase(
        "price_normal_vs_today",
        "この商品は通常1000円ですが、今日は800円で買えます。",
        (("producto", "artículo"), ("1000", "mil"), ("800", "ochocientos"),
         ("yen",), ("hoy",), ("normalmente", "habitualmente")),
    ),
    IndependentCase(
        "name_code_two_line_schedule",
        "明日、\\N[3]は午後6時に戻ります。\r\n受付は午前9時に開きます。",
        (("mañana",), ("6", "seis"), ("9", "nueve"),
         ("recepción",), ("abr",), ("volver", "regres"),
         ("tarde", "p.m.", "pm"), ("a. m.", "am", "mañana")),
    ),
)


def _fold(value: str) -> str:
    """Case/diacritic/meridiem normalization for Spanish surface variants."""
    value = unicodedata.normalize("NFKD", value.casefold().replace("\u00a0", " "))
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"(?<!\w)([ap])\s*\.\s*m\s*\.?(?!\w)", r"\1m", value)
    return re.sub(r"\s+", " ", value).strip()


def _has(text: str, *patterns: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _near(text: str, left: str, right: str, window: int = 55) -> bool:
    return bool(
        re.search(left + rf".{{0,{window}}}" + right, text)
        or re.search(right + rf".{{0,{window}}}" + left, text)
    )


def _semantic_errors(case: IndependentCase, spanish: str) -> list[str]:
    folded = _fold(spanish)
    errors: list[str] = []
    missing = [
        list(group) for group in case.required_groups
        if not any(_fold(option) in folded for option in group)
    ]
    if missing:
        errors.append("MISSING_REQUIRED_CONCEPT_GROUPS")

    if case.id == "meeting_time_contrast":
        rejects_two = _has(
            folded,
            r"\bno\b.{0,45}\b(?:2|dos|14:00)\b",
            r"\b(?:en lugar de|en vez de)\b.{0,35}\b(?:2|dos|14:00)\b",
        )
        four_starts_meeting = _has(
            folded,
            r"\b(?:reunion|junta)\b.{0,70}\b(?:empez|empiez|comenz|comienz|inici)\w*\b.{0,60}\b(?:4|cuatro|16:00)\b",
            r"\b(?:4|cuatro|16:00)\b.{0,45}\b(?:empez|empiez|comenz|comienz|inici)\w*\b",
        )
        four_is_afternoon = _has(
            folded,
            r"\b(?:4|cuatro|16:00)\b.{0,30}\b(?:tarde|pm)\b",
            r"\b(?:4|cuatro)\s*pm\b",
        ) or _has(
            folded,
            r"\b(?:2|dos|14:00)\b.{0,25}\b(?:tarde|pm)\b.{0,45}\b(?:sino|en lugar de|en vez de|no)\b.{0,30}\b(?:4|cuatro|16:00)\b",
            r"\b(?:4|cuatro|16:00)\b.{0,35}\b(?:sino|en lugar de|en vez de|no)\b.{0,30}\b(?:2|dos|14:00)\b.{0,25}\b(?:tarde|pm)\b",
        )
        # The second time must be affirmative. Do not accept "dos..., no a
        # las cuatro" merely because the same tokens appear in the sentence.
        four_denied = _has(
            folded,
            r"\b(?:no|ni)\s+(?:a\s+las\s+)?(?:4|cuatro|16:00)\b",
            r"\bno\s+(?:empiez|empez|comienz|comenz|inici)\w*"
            r".{0,30}\b(?:4|cuatro|16:00)\b",
            r"\b(?:4|cuatro|16:00)\b.{0,18}\b(?:de la manana|am)\b",
        )
        if (
            not rejects_two or not four_starts_meeting
            or not four_is_afternoon or four_denied
        ):
            errors.append("MEETING_TIME_CONTRAST_OR_POLARITY_CHANGED")

    elif case.id == "key_ownership":
        parts = [
            part.strip() for part in re.split(r"\bpero\b|[;.!?]+", folded)
            if part.strip()
        ]
        tanaka_has_key = any(
            re.search(r"\btanaka\b", part)
            and re.search(r"\bllave\b", part)
            and re.search(r"\b(?:tien|posee)\w*\b", part)
            for part in parts
        )
        sato_lacks_key = any(
            re.search(r"\bsato\b", part)
            and re.search(r"\bno\b", part)
            and re.search(r"\b(?:tien|posee)\w*\b", part)
            for part in parts
        )
        if not tanaka_has_key or not sato_lacks_key:
            errors.append("KEY_POSSESSION_ASSIGNED_TO_WRONG_PERSON")

    elif case.id == "bridge_left_turn":
        after_crossing = _has(
            folded,
            r"(?:despues de|tras|al)\s+(?:cruzar|atravesar|pasar)\s+"
            r"(?:el\s+)?puente",
            r"una vez que.{0,35}puente",
        )
        first_signal = _has(
            folded,
            r"\bprimer\w*\b.{0,30}\b(?:semaforo|senal de trafico)\b",
            r"\b(?:semaforo|senal de trafico)\b.{0,30}\bprimer\w*\b",
        )
        left_turn = _has(
            folded,
            r"\b(?:gir|dobl|tome|tomar)\w*\b.{0,25}\bizquierda\b",
            r"\bizquierda\b.{0,25}\b(?:gir|dobl)\w*\b",
        )
        if not after_crossing or not first_signal or not left_turn:
            errors.append("BRIDGE_ROUTE_ORDER_OR_DIRECTION_CHANGED")

    elif case.id == "envelope_color_counts":
        two_red = bool(
            re.search(r"\b(?:2|dos)\b.{0,45}\broj\w*\b", folded)
        )
        five_blue = bool(
            re.search(r"\b(?:5|cinco)\b.{0,45}\bazul\w*\b", folded)
        )
        if not two_red or not five_blue:
            errors.append("ENVELOPE_COLOR_COUNT_MISMATCH")

    elif case.id == "file_do_not_delete":
        no_delete = _has(
            folded,
            r"\bno\b.{0,30}\b(?:bor\w*|elimin\w*|suprim\w*)\b",
        )
        save_elsewhere = _has(
            folded,
            r"\b(?:guard|almacen)\w*\b.{0,55}\b(?:otra|diferente|distinta)\s+carpeta\b",
            r"\b(?:otra|diferente|distinta)\s+carpeta\b.{0,45}\b(?:guard|almacen)\w*\b",
        )
        if not no_delete or not save_elsewhere:
            errors.append("FILE_DELETE_OR_SAVE_INSTRUCTION_CHANGED")

    elif case.id == "email_before_meeting":
        email_first = _has(
            folded,
            r"\b(?:envie|mande)\w*.{0,25}\bprimero\b.{0,30}\bcorreo\b.{0,65}\b(?:despues|luego)\b",
            r"\bprimero\b.{0,25}\b(?:envie|mande)\w*.{0,25}\bcorreo\b.{0,65}\b(?:despues|luego)\b",
            r"\bdespues de (?:enviar|mandar) (?:el )?correo\b",
            r"\bcorreo\b.{0,45}\bantes de venir\b",
        )
        come_to_room = _has(
            folded,
            r"\b(?:venga|acuda|dirijase|pase|venir)\w*.{0,55}\b(?:sala de reuniones|sala de reunion|sala de conferencias)\b",
            r"\b(?:sala de reuniones|sala de reunion|sala de conferencias)\b.{0,35}\b(?:venga|acuda|dirijase|pase|venir)\w*\b",
        )
        invented_recipient = _has(
            folded,
            r"\b(?:envie|envia|mande|manda)(?:nos|me|le|les)\b",
            r"\b(?:envie|envia|mande|manda)\b.{0,25}\b(?:a nosotros|a nosotras|para nosotros|para nosotras|para mi)\b",
        )
        if not email_first or not come_to_room:
            errors.append("EMAIL_AND_MEETING_SEQUENCE_CHANGED")
        if invented_recipient:
            errors.append("EMAIL_RECIPIENT_INVENTED")

    elif case.id == "ordered_books_arrived":
        three_excluded = _has(
            folded,
            r"\bno\b.{0,40}\b(?:3|tres)\b",
            r"\b(?:3|tres)\b.{0,35}\bno\b",
        )
        two_arrived = _near(
            folded, r"\b(?:2|dos)\b", r"\b(?:lleg|recib)\w*\b", 80
        )
        affirmative_two_contrast = _has(
            folded,
            r"\bno\b.{0,35}\b(?:3|tres)\b.{0,25}\bsino(?:\s+que)?\b.{0,18}\b(?:2|dos)\b",
        )
        two_is_not_negated = affirmative_two_contrast or not _has(
            folded, r"\bno\b.{0,22}\b(?:2|dos)\b"
        )
        arrival_denied_after_two = _has(
            folded,
            r"\b(?:2|dos)\b.{0,35}[.!?]\s*no\b.{0,18}\b(?:lleg|recib)\w*\b",
            r"\bsino(?:\s+que)?\s+(?:solo\s+)?(?:2|dos)\b.{0,35}[.!?]\s*no\b.{0,18}\b(?:lleg|recib)\w*\b",
        )
        arrival_negated_before_two = _has(
            folded, r"\bno\b.{0,18}\b(?:lleg|recib)\w*\b"
        )
        arrival_not_negated = (
            not arrival_negated_before_two or affirmative_two_contrast
        ) and not arrival_denied_after_two
        if (
            not three_excluded or not two_arrived or not two_is_not_negated
            or not arrival_not_negated
        ):
            errors.append("DELIVERED_BOOK_QUANTITY_CHANGED")

    elif case.id == "colder_today_weaker_wind":
        colder_than_yesterday = _has(
            folded,
            r"\bhoy\b.{0,45}\bmas frio que ayer\b",
            r"\bmas frio hoy que ayer\b",
        )
        weak_wind = _has(
            folded,
            r"\bviento\b.{0,25}\b(?:debil|suave|flojo)\b",
            r"\b(?:debil|suave|flojo)\b.{0,25}\bviento\b",
        )
        if not colder_than_yesterday or not weak_wind:
            errors.append("WEATHER_COMPARISON_CHANGED")

    elif case.id == "children_permission_and_prohibition":
        may_enter = _has(
            folded,
            r"\b(?:pueden|tienen permiso para|esta permitido|se permite)\b"
            r".{0,35}\bentr\w*\b",
        )
        must_not_run = _has(
            folded,
            r"\bno\b.{0,25}\b(?:corr\w*)\b",
            r"\bprohibido\b.{0,20}\bcorrer\b",
            r"\bno deben correr\b",
        )
        if not may_enter or not must_not_run:
            errors.append("CHILDREN_PERMISSION_OR_PROHIBITION_INVERTED")

    elif case.id == "blue_umbrella_owner":
        blue_umbrella = _has(
            folded, r"\bparaguas\b.{0,20}\bazul\b",
            r"\bazul\b.{0,20}\bparaguas\b",
        )
        not_mine = _has(
            folded, r"\bno es mio\b", r"\bno me pertenece\b",
            r"\bno es de mi propiedad\b",
        )
        sister_owns = _has(
            folded, r"\bmi hermana menor\b", r"\bde mi hermana\b",
            r"\bpertenece a mi hermana\b", r"\bde mi hermanita\b",
        )
        younger_sister = _has(
            folded, r"\bhermana menor\b", r"\bhermana pequena\b",
            r"\bhermanita\b",
        )
        if not blue_umbrella or not not_mine or not sister_owns or not younger_sister:
            errors.append("UMBRELLA_OWNER_OR_SIBLING_AGE_CHANGED")

    elif case.id == "shop_yesterday_today":
        parts = [
            part.strip() for part in re.split(r"\bpero\b|[;.!?]+", folded)
            if part.strip()
        ]
        yesterday_open = any(
            re.search(r"\bayer\b", part)
            and re.search(r"\b(?:abiert\w*|abrio)\b", part)
            and re.search(r"\b(?:tienda|local)\b", part)
            for part in parts
        )
        today_closed = (
            bool(re.search(r"\b(?:tienda|local)\b", folded))
            and any(
                re.search(r"\bhoy\b", part)
                and re.search(r"\b(?:cerrad\w*|descanso|no abre)\b", part)
                for part in parts
            )
        )
        if not yesterday_open or not today_closed:
            errors.append("SHOP_DAY_STATUS_SWAPPED")

    elif case.id == "woman_by_window":
        woman_at_window = _has(
            folded,
            r"\bmujer\b.{0,55}\b(?:sentad\w*)\b.{0,35}\bventana\b",
            r"\bventana\b.{0,55}\bmujer\b.{0,35}\b(?:sentad\w*)\b",
        )
        new_teacher = _has(
            folded, r"\bmi nueva (?:profesora|maestra|docente)\b",
            r"\b(?:profesora|maestra|docente) nueva\b",
        )
        if not woman_at_window or not new_teacher:
            errors.append("WOMAN_LOCATION_OR_TEACHER_ROLE_LOST")

    elif case.id == "reservation_tuesday_to_thursday":
        direction = _has(
            folded,
            r"\bdel martes al jueves\b",
            r"\bde martes a jueves\b",
            r"\bmartes\b.{0,35}\b(?:al|hasta el)\s+jueves\b",
        )
        if not direction or not _has(folded, r"\b(?:camb|modific|traslad|pas)\w*\b"):
            errors.append("RESERVATION_CHANGE_DIRECTION_LOST")

    elif case.id == "cooked_and_washed_dishes":
        both_actions = _has(
            folded,
            r"\bcocin\w*\b.{0,80}\blav\w*\b.{0,25}\bplatos\b",
            r"\blav\w*\b.{0,25}\bplatos\b.{0,80}\bcocin\w*\b",
            r"\bprepar\w*\b.{0,25}\bcomida\b.{0,80}\blav\w*\b.{0,25}\bplatos\b",
            r"\blav\w*\b.{0,25}\bplatos\b.{0,80}\bprepar\w*\b.{0,25}\bcomida\b",
        )
        additive = _has(
            folded,
            r"\bno solo\b.{0,100}\bsino que tambien\b",
            r"\bno solamente\b.{0,100}\bsino que tambien\b",
            r"\bcocin\w*\b.{0,55}\by tambien\b",
            r"\bprepar\w*\b.{0,35}\bcomida\b.{0,55}\by tambien\b",
        )
        if not both_actions or not additive:
            errors.append("COOKING_OR_DISHWASHING_ADDITIVE_MEANING_LOST")

    elif case.id == "check_document_before_signing":
        before_signing = _has(
            folded,
            r"\bantes de firm\w*\b",
            r"\bprevio a firm\w*\b",
        )
        must_check = _has(
            folded,
            r"\b(?:debe|deben|tiene que|es necesario|hay que|se debe)\b.{0,45}\b(?:revis|verific|comprob)\w*\b.{0,35}\bcontenido\b",
            r"\b(?:revis|verific|comprob)\w*\b.{0,35}\bcontenido\b.{0,35}\b(?:debe|deben|tiene que|es necesario|hay que|se debe)\b",
        )
        if not before_signing or not must_check:
            errors.append("DOCUMENT_REVIEW_OBLIGATION_OR_ORDER_CHANGED")

    elif case.id == "miss_train_take_taxi":
        # A successful train connection is NOT the same condition as missing
        # the train. In particular, positive "si logro/llego" must be rejected.
        miss_train_condition = _has(
            folded,
            r"\bsi\b.{0,55}\bno\s+(?:alcanz|lleg|logr)\w*"
            r".{0,35}\btren\b",
            r"\bsi\b.{0,55}\b(?:pierd|perd)\w*.{0,35}\btren\b",
        )
        loss_is_negated = _has(
            folded,
            r"\bsi\b.{0,55}\bno\s+(?:pierd|perd)\w*.{0,35}\btren\b",
        )
        taxi_consequence = _has(
            folded,
            r"\b(?:iremos|ire|vamos|voy|tomare|tomaremos)"
            r"\b.{0,25}\btaxi\b",
            r"\btaxi\b.{0,25}\b(?:iremos|ire|vamos|voy|tomare|tomaremos)\b",
        )
        taxi_not_negated = not _has(
            folded,
            r"\bno\b.{0,20}\b(?:iremos|ire|vamos|voy|tomare|tomaremos)"
            r"\b.{0,20}\btaxi\b",
        )
        if (
            not miss_train_condition or loss_is_negated
            or not taxi_consequence or not taxi_not_negated
        ):
            errors.append("MISSED_TRAIN_CONDITION_OR_TAXI_CONSEQUENCE_CHANGED")

    elif case.id == "luggage_reception_or_room":
        left_at_reception = _has(
            folded,
            r"\b(?:dej|deposit)\w*\b.{0,45}\b(?:recepcion|mostrador)\b",
            r"\b(?:recepcion|mostrador)\b.{0,35}\b(?:dej|deposit)\w*\b",
        )
        carried_to_room = _has(
            folded,
            r"\b(?:llev|transport)\w*\b.{0,45}\b(?:habitacion|cuarto)\b",
            r"\b(?:habitacion|cuarto)\b.{0,35}\b(?:llev|transport)\w*\b",
        )
        alternatives = _has(folded, r"\bo\b", r"\bo bien\b", r"\ben cambio\b")
        if not left_at_reception or not carried_to_room or not alternatives:
            errors.append("LUGGAGE_ALTERNATIVES_CHANGED")

    elif case.id == "called_but_no_reply":
        called_him = _has(
            folded, r"\b(?:lo|le)\s+llam\w*\b", r"\bllam\w*\b.{0,25}\b(?:el|a el)\b"
        )
        no_reply_yet = _has(
            folded,
            r"\bno ha (?:respondido|contestado)\b",
            r"\b(?:todavia|aun) no (?:responde|contesta)\b",
            r"\bno me ha (?:respondido|contestado)\b",
        )
        if not called_him or not no_reply_yet:
            errors.append("CALL_OR_NO_REPLY_MEANING_CHANGED")

    elif case.id == "price_normal_vs_today":
        price_parts = [
            part.strip() for part in re.split(r"\bpero\b|[;.!?]+", folded)
            if part.strip()
        ]
        normal_price = any(
            _has(part, r"\b(?:normalmente|habitualmente)\b")
            and _has(part, r"\b(?:1000|mil)\b")
            and _has(part, r"\byen\w*\b")
            for part in price_parts
        )
        today_price = any(
            _has(part, r"\bhoy\b")
            and _has(part, r"\b(?:800|ochocientos)\b")
            and _has(part, r"\byen\w*\b")
            for part in price_parts
        )
        if not normal_price or not today_price:
            errors.append("PRICE_OR_TEMPORAL_COMPARISON_CHANGED")

    elif case.id == "name_code_two_line_schedule":
        lines = [_fold(line) for line in spanish.splitlines()]
        if len(lines) != 2:
            errors.append("SCHEDULE_LINE_COUNT_CHANGED")
        else:
            first = lines[0]
            second = lines[1]
            first_line_ok = (
                r"\N[3]" in spanish.splitlines()[0]
                and _has(first, r"\bmanana\b")
                and _has(first, r"\b(?:volver|regres)\w*\b")
                and _has(first, r"\b(?:6|seis)\b")
                and _has(first, r"\b(?:tarde|pm)\b")
            )
            second_line_ok = (
                _has(second, r"\brecepcion\b")
                and _has(second, r"\babr\w*\b")
                and _has(second, r"\b(?:9|nueve)\b")
                and _has(second, r"\b(?:de la manana|am)\b")
            )
            if not first_line_ok or not second_line_ok:
                errors.append("NAME_CODE_OR_LINE_TIME_ASSIGNMENT_CHANGED")

    return errors


def _require_semantic_fidelity(case: IndependentCase, spanish: str) -> None:
    problems = _semantic_errors(case, spanish)
    if problems:
        raise TranslationRejected(
            "INDEPENDENT_HOLDOUT_SEMANTIC_FAILURE:"
            + json.dumps(problems, ensure_ascii=False)
        )


def _load_models():
    """Load only the two public Apache-2.0 Marian models used by stage one."""
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    torch.set_num_threads(2)

    def load_one(model_id: str, source: str, target: str):
        tokenizer = AutoTokenizer.from_pretrained(
            model_id, trust_remote_code=False
        )
        model = AutoModelForSeq2SeqLM.from_pretrained(
            model_id, trust_remote_code=False
        )
        model.eval()

        class Translator:
            def translate(self, text: str) -> str:
                if not isinstance(text, str) or not text.strip():
                    raise RuntimeError("INDEPENDENT_MODEL_EMPTY_SOURCE:" + model_id)
                encoded = tokenizer(
                    [text], return_tensors="pt", truncation=False
                )
                if encoded["input_ids"].shape[-1] > 512:
                    raise RuntimeError("INDEPENDENT_MODEL_CONTEXT_EXCEEDED:" + model_id)
                with torch.inference_mode():
                    generated = model.generate(
                        **encoded, max_new_tokens=256, num_beams=4,
                        renormalize_logits=True,
                    )
                decoded = tokenizer.batch_decode(
                    generated, skip_special_tokens=True
                )
                if len(decoded) != 1 or not isinstance(decoded[0], str):
                    raise RuntimeError("INDEPENDENT_MODEL_INVALID_OUTPUT:" + model_id)
                return decoded[0]

        provenance = {
            "model_id": model_id,
            "architecture": model.__class__.__name__,
            "source": source,
            "target": target,
            "declared_license": DECLARED_LICENSE,
            "model_page": "https://huggingface.co/" + model_id,
            "trust_remote_code": False,
        }
        return Translator(), provenance

    ja_en, ja_en_provenance = load_one(JA_EN_MODEL_ID, "ja", "en")
    en_es, en_es_provenance = load_one(EN_ES_MODEL_ID, "en", "es")
    return ja_en, en_es, [ja_en_provenance, en_es_provenance]


def _save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def translate_phase(workspace: Path) -> int:
    if workspace.exists():
        raise RuntimeError("INDEPENDENT_HOLDOUT_WORKSPACE_MUST_BE_NEW")
    workspace.mkdir(parents=True)
    report = {
        "schema": "public-independent-ja-en-es-quality-v1",
        "kind": "REAL_NEURAL_PUBLIC_TWO_STAGE_MARIAN_INDEPENDENT_20_CASES",
        "route": ["ja-en", "en-es"],
        "expected_models": [
            {"model_id": JA_EN_MODEL_ID, "declared_license": DECLARED_LICENSE},
            {"model_id": EN_ES_MODEL_ID, "declared_license": DECLARED_LICENSE},
        ],
        "evaluation_policy": {
            "holdout_cases": len(INDEPENDENT_CASES),
            "disjoint_from_first_pivot_holdout": True,
            "source_paraphrases": False,
            "target_language_repairs": False,
            "prepared_translations_in_inference": False,
            "glossary_edits": False,
            "human_approvals": False,
            "case_specific_retries": False,
            "uniform_segmentation_modes": [
                "document_context", "line_context", "sentence_context"
            ],
            "selection": "first_candidate_passing_independent_semantic_policy",
            "numeric_literals_sent_to_model": True,
            "contextual_name_code_aliases": True,
            "structural_protection_only": True,
            "all_cases_required": True,
            "semantic_policy_version": SEMANTIC_POLICY_VERSION,
        },
        "backend_executed": False,
        "models": [],
        "cases": [],
    }
    started = time.monotonic()
    try:
        ja_en, en_es, provenance = _load_models()
        if (
            len(provenance) != 2
            or [item.get("model_id") for item in provenance]
            != [JA_EN_MODEL_ID, EN_ES_MODEL_ID]
            or any(item.get("declared_license") != DECLARED_LICENSE
                   for item in provenance)
        ):
            raise RuntimeError("INDEPENDENT_MODEL_PROVENANCE_INVALID")
        report["backend_executed"] = True
        report["models"] = provenance

        with (
            DurableTranslationCache(workspace / "cache") as cache,
            ReviewQueue(workspace / "cache") as review_queue,
        ):
            for case in INDEPENDENT_CASES:
                ja_en_attempts: list[dict] = []
                en_es_attempts: list[dict] = []
                candidate_box: list[str] = []
                entry = {
                    "case": case.id,
                    "source": case.japanese,
                    "status": "rejected",
                    "ja_en_raw_attempts": ja_en_attempts,
                    "en_es_raw_attempts": en_es_attempts,
                }

                def producer(source_text: str) -> str:
                    model_source, name_codes = contextualize_name_code_source(
                        source_text
                    )
                    rejected_modes: list[dict[str, str]] = []
                    for mode, segmentation in (
                        ("document_context", "document"),
                        ("line_context", "lines"),
                        ("sentence_context", True),
                    ):
                        english_box: list[str] = []

                        def translate_ja_en(fragment: str) -> str:
                            value = ja_en.translate(fragment)
                            ja_en_attempts.append({
                                "mode": mode,
                                "source_fragment": fragment[:240],
                                "raw_output": value[:700],
                            })
                            return value

                        def translate_en_es(fragment: str) -> str:
                            value = en_es.translate(fragment)
                            en_es_attempts.append({
                                "mode": mode,
                                "source_fragment": fragment[:240],
                                "raw_output": value[:700],
                            })
                            return value

                        try:
                            english = translate_checked(
                                model_source,
                                translate_ja_en,
                                source="ja",
                                protect_numbers=False,
                                split_model_sentences=segmentation,
                            )
                            english_box.append(english)
                            spanish = translate_checked(
                                english,
                                translate_en_es,
                                source="en",
                                protect_numbers=False,
                                split_model_sentences=segmentation,
                            )
                            spanish = restore_contextual_name_codes(
                                spanish, name_codes
                            )
                            validate_translation(
                                source_text, spanish, source="ja"
                            )
                            candidate_box.append(spanish)
                            _require_semantic_fidelity(case, spanish)
                            entry["intermediate_english"] = english[:1800]
                            entry["accepted_segmentation_mode"] = mode
                            entry["rejected_segmentation_modes"] = rejected_modes
                            return spanish
                        except TranslationRejected as exc:
                            if english_box:
                                entry["intermediate_english"] = english_box[-1][:1800]
                            rejected_modes.append({
                                "mode": mode,
                                "reason": str(exc)[:420],
                            })

                    entry["rejected_segmentation_modes"] = rejected_modes
                    raise TranslationRejected(
                        "ALL_INDEPENDENT_SEGMENTATION_MODES_REJECTED:"
                        + json.dumps(rejected_modes, ensure_ascii=False)[:900]
                    )

                try:
                    translated = cache.translate_or_get(
                        "ja", "es", case.japanese, producer,
                        quality_validator=lambda candidate, current=case:
                            _require_semantic_fidelity(current, candidate),
                    )
                    validate_translation(case.japanese, translated, source="ja")
                    entry["status"] = "accepted"
                    entry["translated"] = translated
                    entry["sha256"] = hashlib.sha256(
                        translated.encode("utf-8")
                    ).hexdigest()
                except Exception as exc:
                    entry["error"] = type(exc).__name__ + ":" + str(exc)[:900]
                    item = review_queue.enqueue(
                        "ja", "es", case.japanese,
                        candidate_box[-1] if candidate_box else "",
                        reason=entry["error"],
                        context={
                            "case_id": case.id,
                            "semantic_policy": SEMANTIC_POLICY_VERSION,
                            "route": ["ja-en", "en-es"],
                            "model_provenance": provenance,
                            "intermediate_english": entry.get(
                                "intermediate_english", ""
                            ),
                            "ja_en_raw_attempts": ja_en_attempts,
                            "en_es_raw_attempts": en_es_attempts,
                        },
                    )
                    entry["review_item_id"] = item.item_id
                    entry["review_status"] = item.status

                report["cases"].append(entry)
                print(
                    "INDEPENDENT_HOLDOUT_CASE " + case.id + " "
                    + entry["status"] + " " + entry.get("error", ""),
                    flush=True,
                )

            report["cache_rows"] = cache.count()
            report["review_queue_pending"] = review_queue.count("pending")
            report["review_queue_total"] = review_queue.count()
            review_queue.export_snapshot(workspace / "review-queue.json")
    except Exception as exc:
        report["setup_error"] = type(exc).__name__ + ":" + str(exc)[:1000]
        print("INDEPENDENT_HOLDOUT_SETUP_FAILURE " + report["setup_error"], flush=True)

    report["accepted"] = sum(
        row["status"] == "accepted" for row in report["cases"]
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
    _save_json(workspace / "independent-report.json", report)
    print(
        "INDEPENDENT_HOLDOUT_REPORT "
        + json.dumps(report, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if report["status"] == "PASS" else 1


def verify_phase(workspace: Path) -> int:
    report_path = workspace / "independent-report.json"
    if not report_path.is_file():
        print("INDEPENDENT_HOLDOUT_RESTART_FAIL_NO_REPORT", flush=True)
        return 1

    report = json.loads(report_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    quality_errors: list[str] = []
    persistence_errors: list[str] = []
    by_id = {case.id: case for case in INDEPENDENT_CASES}
    rows = report.get("cases", [])
    accepted = [row for row in rows if row.get("status") == "accepted"]

    if not report.get("backend_executed"):
        errors.append("INDEPENDENT_NEURAL_INFERENCE_NOT_EXECUTED")
    actual_models = report.get("models", [])
    expected_models = report.get("expected_models", [])
    if len(actual_models) != 2 or len(expected_models) != 2:
        errors.append("INDEPENDENT_MODEL_PROVENANCE_CARDINALITY_INVALID")
    else:
        for observed, expected in zip(actual_models, expected_models):
            if observed.get("model_id") != expected.get("model_id"):
                errors.append("INDEPENDENT_MODEL_ID_CHANGED")
            if observed.get("declared_license") != DECLARED_LICENSE:
                errors.append("INDEPENDENT_MODEL_LICENSE_CHANGED")

    if len(rows) != len(INDEPENDENT_CASES):
        errors.append("INDEPENDENT_REPORT_CASE_COUNT_CHANGED")
    if len(accepted) != len(INDEPENDENT_CASES):
        quality_errors.append("INDEPENDENT_HOLDOUT_NOT_FULLY_ACCEPTED")

    db_path = workspace / "cache" / "translation-cache.sqlite3"
    if not db_path.is_file():
        persistence_errors.append("INDEPENDENT_SQLITE_DATABASE_MISSING")
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
                    prefix="INDEPENDENT",
                )
            )

            for row in accepted:
                case = by_id.get(row.get("case"))
                if case is None:
                    errors.append("INDEPENDENT_UNKNOWN_CASE:" + str(row.get("case")))
                    continue
                translated = row.get("translated", "")
                try:
                    validate_translation(case.japanese, translated, source="ja")
                    _require_semantic_fidelity(case, translated)
                except TranslationRejected as exc:
                    quality_errors.append(
                        "INDEPENDENT_REPORT_TRANSLATION_INVALID:"
                        + case.id + ":" + str(exc)[:180]
                    )
                    continue

                cached = cache.get(
                    "ja", "es", case.japanese,
                    quality_validator=lambda candidate, current=case:
                        _require_semantic_fidelity(current, candidate),
                )
                if cached != translated:
                    persistence_errors.append(
                        "INDEPENDENT_CACHE_CONTENT_CHANGED:" + case.id
                    )
                    continue
                try:
                    replay = cache.translate_or_get(
                        "ja", "es", case.japanese,
                        lambda _unused: (_ for _ in ()).throw(
                            AssertionError("INDEPENDENT_CACHE_MISS_RECALLED_MODEL")
                        ),
                        quality_validator=lambda candidate, current=case:
                            _require_semantic_fidelity(current, candidate),
                    )
                    if replay != translated:
                        persistence_errors.append(
                            "INDEPENDENT_REPLAY_MISMATCH:" + case.id
                        )
                except Exception as exc:
                    persistence_errors.append(
                        "INDEPENDENT_REPLAY_FAILED:"
                        + case.id + ":" + str(exc)[:180]
                    )

    proof = {
        "schema": "public-independent-ja-en-es-restart-v2",
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
    _save_json(workspace / "independent-restart-proof.json", proof)
    print(
        "INDEPENDENT_HOLDOUT_RESTART_PROOF "
        + json.dumps(proof, ensure_ascii=True, sort_keys=True),
        flush=True,
    )
    return 0 if not errors and not persistence_errors else 1



def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    if args.phase == "translate":
        return translate_phase(args.workspace)
    return verify_phase(args.workspace)


if __name__ == "__main__":
    sys.exit(main())
