"""Generic source-only katakana readings for model context, never target repairs.

The same Japanese syllabary algorithm runs for every source fragment. It does
not contain prepared Spanish sentences, character-specific translations, or
output substitutions. Ordinary katakana words may also receive readings.
"""
from __future__ import annotations

import re

_KANA = dict(pair.split(":") for pair in """ア:a イ:i ウ:u エ:e オ:o カ:ka キ:ki ク:ku ケ:ke コ:ko
サ:sa シ:shi ス:su セ:se ソ:so タ:ta チ:chi ツ:tsu テ:te ト:to
ナ:na ニ:ni ヌ:nu ネ:ne ノ:no ハ:ha ヒ:hi フ:fu ヘ:he ホ:ho
マ:ma ミ:mi ム:mu メ:me モ:mo ヤ:ya ユ:yu ヨ:yo
ラ:ra リ:ri ル:ru レ:re ロ:ro ワ:wa ヲ:o ン:n
ガ:ga ギ:gi グ:gu ゲ:ge ゴ:go ザ:za ジ:ji ズ:zu ゼ:ze ゾ:zo
ダ:da ヂ:ji ヅ:zu デ:de ド:do バ:ba ビ:bi ブ:bu ベ:be ボ:bo
パ:pa ピ:pi プ:pu ペ:pe ポ:po ヴ:vu
ァ:a ィ:i ゥ:u ェ:e ォ:o ャ:ya ュ:yu ョ:yo""".split())
_YOON = {
    "キ": "ky", "ギ": "gy", "シ": "sh", "ジ": "j", "チ": "ch",
    "ニ": "ny", "ヒ": "hy", "ビ": "by", "ピ": "py",
    "ミ": "my", "リ": "ry",
}
_EXTRA = {
    "ティ": "ti", "ディ": "di", "トゥ": "tu", "ドゥ": "du",
    "ファ": "fa", "フィ": "fi", "フェ": "fe", "フォ": "fo",
    "ウィ": "wi", "ウェ": "we", "ウォ": "wo",
    "シェ": "she", "ジェ": "je", "チェ": "che",
}
_SMALL_Y = {"ャ": "a", "ュ": "u", "ョ": "o"}
_KATAKANA_RUN = re.compile(r"[ァ-ヶー]{2,}")


def katakana_romanization(token: str) -> str:
    """Transliterate only input kana; never infer a longer proper name."""
    sounds: list[str] = []
    i = 0
    while i < len(token):
        char = token[i]
        next_char = token[i + 1] if i + 1 < len(token) else ""
        pair = token[i:i + 2]
        if pair in _EXTRA:
            sounds.append(_EXTRA[pair])
            i += 2
        elif char in _YOON and next_char in _SMALL_Y:
            sounds.append(_YOON[char] + _SMALL_Y[next_char])
            i += 2
        elif char == "ッ":
            following = _KANA.get(next_char, "")
            if following.startswith("ch"):
                sounds.append("t")
            elif following.startswith("sh"):
                sounds.append("s")
            elif following and following[0] not in "aeioun":
                sounds.append(following[0])
            i += 1
        elif char == "ー":
            vowels = re.findall(r"[aeiou]", "".join(sounds))
            if vowels:
                sounds.append(vowels[-1])
            i += 1
        else:
            if char not in _KANA:
                return ""
            sounds.append(_KANA[char])
            i += 1
    return "".join(sounds).capitalize()


def source_katakana_readings(source: str) -> tuple[tuple[str, str], ...]:
    """Deduplicated source-derived readings, not Spanish target references."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for token in _KATAKANA_RUN.findall(source):
        if token in seen or len(token) > 20:
            continue
        seen.add(token)
        romanization = katakana_romanization(token)
        if romanization:
            found.append((token, romanization))
    return tuple(found)


def phonetic_sidecar(source: str) -> str:
    """Append name-pronunciation hints only; do not alter the source or output."""
    readings = source_katakana_readings(source)
    if not readings:
        return ""
    pairs = "; ".join(f"{kana} = {romaji}" for kana, romaji in readings)
    return (
        "\n\nSource-derived Japanese katakana pronunciation notes "
        "(NOT Spanish translations or additional source text):\n"
        + pairs
        + "\nUse these phonetic readings ONLY if the Japanese item is a personal "
        "proper name. Never lengthen a name, insert syllables, or print this "
        "note. Translate only the original Japanese text."
    )
