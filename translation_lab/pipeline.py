"""Source-independent structural protection for offline translation.

This is an intentionally PUBLIC, model-free reference implementation.
No game archives, language model weights, or private code are imported.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Mapping

# Independent, deliberately conservative subset of RPG control syntax.
# Keep code arguments (including numbers and Japanese names) immutable.
RPG_CODE = re.compile(
    r"(?:\\|\x1b)(?:[A-Za-z]{1,12}<[^>\r\n]{1,128}>"
    r"|[A-Za-z]{1,12}\[[^\]\r\n]{1,80}\]"
    r"|[{}$.|!><^\\]|[A-Za-z]{1,12})"
    r"|%[1-9]\d*|%[sdf]"
    r"|\$\{[A-Za-z_][A-Za-z_0-9]{0,80}\}"
    r"|</?[A-Za-z][^<>]{0,160}>"
)
NUMERIC = r"(?<![0-9０-９])[0-9０-９]+(?![0-9０-９])"
JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
SENTENCE_END = re.compile(r"[。!?！？]+(?:[」』】）》]*)")
LINE_END = re.compile(r"(\r\n|\r|\n)$")


def _target_sentences(text: str) -> list[str]:
    """Split Spanish/English sentences without breaking a. m. or p. m."""
    stripped = text.strip(" \t\u3000")
    if not stripped:
        return []
    return [
        part.strip(" \t\u3000")
        for part in re.split(
            r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡])",
            stripped,
        )
        if part.strip(" \t\u3000")
    ]


def _restore_document_line_breaks(source: str, translated: str) -> str:
    """Reapply source line boundaries when target sentence counts align."""
    source_parts = _split_preserving_newlines(source)
    source_lines = source_parts[::2]
    source_breaks = source_parts[1::2]
    if not source_breaks:
        return translated

    source_sentence_counts = [
        len([part for part in split_sentences(line) if part.strip(" \t\u3000")])
        for line in source_lines
    ]
    if any(count == 0 for count in source_sentence_counts):
        raise TranslationRejected("DOCUMENT_LAYOUT_ALIGNMENT_FAILED")

    target_parts = _split_preserving_newlines(translated)
    target_lines = target_parts[::2]
    target_sentence_counts = [len(_target_sentences(line)) for line in target_lines]

    if (
        len(target_lines) == len(source_lines)
        and target_sentence_counts == source_sentence_counts
    ):
        return "".join(
            target_lines[index]
            + (source_breaks[index] if index < len(source_breaks) else "")
            for index in range(len(source_lines))
        )

    flattened = " ".join(line.strip(" \t\u3000") for line in target_lines if line.strip(" \t\u3000"))
    target_sentences = _target_sentences(flattened)
    if len(target_sentences) != sum(source_sentence_counts):
        raise TranslationRejected("DOCUMENT_LAYOUT_ALIGNMENT_FAILED")

    rebuilt = []
    cursor = 0
    for index, count in enumerate(source_sentence_counts):
        rebuilt.append(" ".join(target_sentences[cursor:cursor + count]))
        cursor += count
        if index < len(source_breaks):
            rebuilt.append(source_breaks[index])
    return "".join(rebuilt)
INTERNAL_MARKER = re.compile(
    r"\\V\[(?:9876[5-9]\d|987[7-9]\d{2}|98[89]\d{3}|99\d{4})\]"
    r"|ZXQTX760(?:NUM|TERM)\d+QXZ|ZXQPLB[A-Z]+QXZ"
)
DOCUMENT_LAYOUT_MARKER = re.compile(r"ZXQPLB[A-Z]+QXZ")


class TranslationRejected(ValueError):
    """The source or translation violated a strict structural invariant."""


def code_parts(text: str) -> list[tuple[bool, str]]:
    """Return (is_original_control_code, literal_fragment) without dropping text."""
    result: list[tuple[bool, str]] = []
    start = 0
    for match in RPG_CODE.finditer(text):
        if match.start() != start:
            result.append((False, text[start:match.start()]))
        result.append((True, match.group(0)))
        start = match.end()
    if start < len(text):
        result.append((False, text[start:]))
    if "".join(fragment for _, fragment in result) != text:
        raise TranslationRejected("RPG_SOURCE_CHARACTER_LOSS")
    return result


def split_sentences(text: str) -> list[str]:
    """Split on sentence ends and keep every original character in order."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not text:
        return [""]
    pieces = re.split(r"(\r\n|\r|\n)", text)
    out: list[str] = []
    for i, part in enumerate(pieces):
        if i % 2:
            out.append(part)
            continue
        start = 0
        for match in SENTENCE_END.finditer(part):
            out.append(part[start:match.end()])
            start = match.end()
        if start != len(part):
            out.append(part[start:])
    if "".join(out) != text:
        raise TranslationRejected("SENTENCE_SPLIT_LOST_SOURCE")
    return out


def protect_literals(
    text: str,
    *,
    source: str = "ja",
    glossary: Mapping[str, str] | None = None,
    protect_numbers: bool = True,
    inline_glossary: bool = False,
) -> tuple[str, dict[str, str]]:
    """Turn approved terms/numbers outside original RPG codes into sentinels.

    \\V[987650] markers are native-looking control codes that the layout splitter
    can preserve without passing them through a neural model. They must be
    restored before any output is shown or saved.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if source not in {"ja", "en"}:
        raise ValueError("Only Japanese or English source is supported")
    terms = dict(glossary or {})
    if source != "ja":
        terms = {}
    if any(not key or not isinstance(key, str) or not isinstance(value, str)
           or not value.strip() or RPG_CODE.search(value)
           for key, value in terms.items()):
        raise ValueError("Unsafe glossary entry")
    if inline_glossary and any(JAPANESE.search(v) for v in terms.values()):
        raise ValueError("Inline glossary cannot contain Japanese")
    patterns = [re.escape(k) for k in sorted(terms, key=len, reverse=True)]
    if protect_numbers:
        patterns.append(NUMERIC)
    if not patterns:
        return text, {}
    literal_re = re.compile("|".join(patterns))
    mapping: dict[str, str] = {}
    next_id = 987650

    def replace(match: re.Match[str]) -> str:
        nonlocal next_id
        observed = match.group(0)
        if inline_glossary and observed in terms:
            # Maintain sentence context for names/roles. Structural numeric
            # sentinels and real RPG codes remain independently protected.
            return terms[observed]
        token = ""
        while next_id <= 999999:
            candidate = r"\V[" + str(next_id) + "]"
            next_id += 1
            if candidate not in text and candidate not in mapping:
                token = candidate
                break
        if not token:
            raise TranslationRejected("INTERNAL_MARKER_SPACE_EXHAUSTED")
        mapping[token] = terms.get(observed, observed)
        return token

    chunks = []
    for protected, fragment in code_parts(text):
        chunks.append(fragment if protected else literal_re.sub(replace, fragment))
    candidate = "".join(chunks)
    if any(candidate.count(token) != 1 for token in mapping):
        raise TranslationRejected("MARKER_COLLISION")
    return candidate, mapping


def _insert_word_separator(left: str, right: str) -> str:
    if not left or not right or left[-1].isspace() or right[0].isspace():
        return ""
    if left[-1] in ":-/." and right[0].isdigit():
        return ""  # 12:30 and 2026-11-19 are not whitespace-delimited.
    before = bool(re.fullmatch(r"[A-Za-zÀ-ÿ0-9]", left[-1]))
    after = bool(re.fullmatch(r"[A-Za-zÀ-ÿ0-9]", right[0]))
    return " " if ((before or left[-1] in ".!?,;:»”…")
                   and (after or right[0] in "¿¡«“\"(")) else ""


def _normalize_prose_punctuation(text: str) -> str:
    """Localize punctuation only outside immutable RPG control code arguments."""
    normalized = []
    for is_code, fragment in code_parts(text):
        if is_code:
            normalized.append(fragment)
            continue
        fragment = fragment.translate(str.maketrans("。！？、", ".!?,"))
        fragment = re.sub(r"([!?])\1+", r"\1", fragment)
        fragment = re.sub(r"(?<=[.!?])(?=[A-Za-zÀ-ÿ¿¡])", " ", fragment)
        normalized.append(fragment)
    return "".join(normalized)


def restore_literals(translated: str, mapping: Mapping[str, str]) -> str:
    """Reject missing/duplicated markers; restore approved terms and numbers."""
    if not isinstance(translated, str):
        raise TranslationRejected("NON_STRING_TRANSLATION")
    for token in mapping:
        if translated.count(token) != 1:
            raise TranslationRejected("MARKER_MISSING_OR_DUPLICATED")
    restored = translated
    for token, value in mapping.items():
        i = restored.index(token)
        left, right = restored[:i], restored[i + len(token):]
        core = value.strip(" \t\u3000")
        # Numeric sentinels are literal, not natural-language words. Preserve
        # adjacencies in HP99, nivel12 and v2.3 instead of inventing spaces.
        numeric = bool(re.fullmatch(r"[0-9０-９]+", core))
        prefix = "" if numeric else _insert_word_separator(left, core)
        suffix = "" if numeric else _insert_word_separator(core, right)
        restored = left + prefix + core + suffix + right
    if any(token in restored for token in mapping):
        raise TranslationRejected("INTERNAL_MARKER_LEAK")
    return _normalize_prose_punctuation(restored)


def _split_preserving_newlines(text: str) -> list[str]:
    return re.split(r"(\r\n|\r|\n)", text)


def restore_layout(source: str, candidate: str) -> str:
    """Keep exact line ending sequence and indentation from the source."""
    original = _split_preserving_newlines(source)
    target = _split_preserving_newlines(candidate)
    if len(original) != len(target):
        raise TranslationRejected("LINE_COUNT_CHANGED")
    out = []
    for index, (a, b) in enumerate(zip(original, target)):
        if index % 2:
            if a != b:
                raise TranslationRejected("LINE_BREAK_CHANGED")
            out.append(a)
        else:
            original_margin = re.match(r"^[ \t\u3000]*", a).group(0)
            original_tail = re.search(r"[ \t\u3000]*$", a).group(0)
            out.append(original_margin + b.strip(" \t\u3000") + original_tail)
    return "".join(out)


def _numeric_values_outside_codes(text: str) -> Counter[str]:
    """Compare Arabic numerals by value, outside native control arguments."""
    values = Counter()
    for is_code, fragment in code_parts(text):
        if not is_code:
            for match in re.finditer(NUMERIC, fragment):
                values[unicodedata.normalize("NFKC", match.group(0))] += 1
    return values


_SPANISH_NUMBER_WORDS: dict[str, tuple[str, ...]] = {
    "0": ("cero",), "2": ("dos",), "3": ("tres",),
    "4": ("cuatro",), "5": ("cinco",), "6": ("seis",),
    "7": ("siete",), "8": ("ocho",), "9": ("nueve",),
    "10": ("diez",), "11": ("once",), "12": ("doce",),
    "13": ("trece",), "14": ("catorce",), "15": ("quince",),
    "16": ("dieciséis", "dieciseis"), "17": ("diecisiete",),
    "18": ("dieciocho",), "19": ("diecinueve",),
    "20": ("veinte",), "21": ("veintiuno", "veintiún"),
    "22": ("veintidós", "veintidos"), "23": ("veintitrés", "veintitres"),
    "24": ("veinticuatro",), "25": ("veinticinco",),
    "26": ("veintiséis", "veintiseis"), "27": ("veintisiete",),
    "28": ("veintiocho",), "29": ("veintinueve",),
    "30": ("treinta",), "40": ("cuarenta",), "50": ("cincuenta",),
    "60": ("sesenta",), "70": ("setenta",), "80": ("ochenta",),
    "90": ("noventa",),
}


def _normalize_spanish_number_words(
    translated: str, source_numbers: Counter[str]
) -> str:
    """Normalize only number words whose values occur in the source."""
    result = translated
    for value in source_numbers:
        for word in _SPANISH_NUMBER_WORDS.get(value, ()):
            result = re.sub(
                r"(?<![A-Za-zÀ-ÿ])" + re.escape(word) + r"(?![A-Za-zÀ-ÿ])",
                value,
                result,
                flags=re.IGNORECASE,
            )
    return result


def _numeric_comparison_candidate(
    original: str, translated: str, source_numbers: Counter[str]
) -> str:
    result = _normalize_spanish_number_words(translated, source_numbers)
    # 3:00 is equivalent to Japanese 3時; added non-zero minutes are not.
    source_has_minutes = bool(
        re.search(r"[0-9０-９]{1,2}[:：][0-9０-９]{2}|[0-9０-９]+分", original)
    )
    if not source_has_minutes:
        result = re.sub(
            r"(?<![0-9０-９])([0-9０-９]{1,2})[:：]00(?![0-9０-９])",
            r"\1",
            result,
        )
    return result


def _join_spanish_sentences(parts: list[tuple[str, str]]) -> str:
    """Rejoin model clauses using source sentence boundaries, not model luck.

    Some compact MT models omit a final full stop. When the Japanese source
    clearly ended a sentence, restore the *boundary*, never missing meaning.
    Do not modify RPG codes, explicit newline markers or numeric literals.
    """
    result = ""
    previous_source = ""
    for original, translated in parts:
        if not translated:
            continue
        if result and translated and not translated[0].isspace():
            previous_ended = bool(
                re.search(r"[。！？!?][」』】）》]*$", previous_source)
            )
            if previous_ended and re.match(r"[A-Za-zÀ-ÿ¿¡«\"(]", translated):
                tail = result.rstrip()
                if tail and not re.search(r"[.!?][»”\"')]*$", tail):
                    result = tail + "."
                if result and not result[-1].isspace():
                    result += " "
        result += translated
        previous_source = original
    return result


def validate_translation(
    original: str,
    translated: str,
    *,
    source: str = "ja",
    required_terms: tuple[str, ...] = (),
) -> None:
    """Structural acceptance checks, NOT a claim of neural semantic accuracy."""
    if not isinstance(translated, str) or not translated.strip():
        raise TranslationRejected("EMPTY_TRANSLATION")
    if "\ufffd" in translated:
        raise TranslationRejected("UNICODE_REPLACEMENT_CHARACTER")
    for marker in INTERNAL_MARKER.findall(translated):
        # Preexisting high-numbered RPG variables are not temporary sentinels.
        if marker not in original:
            raise TranslationRejected("INTERNAL_MARKER_LEAK")
    if [c for protected, c in code_parts(original) if protected] != [
        c for protected, c in code_parts(translated) if protected
    ]:
        raise TranslationRejected("ORIGINAL_CONTROL_CODES_CHANGED")
    source_numbers = _numeric_values_outside_codes(original)
    numeric_candidate = _numeric_comparison_candidate(
        original, translated, source_numbers
    )
    if source_numbers and source_numbers != _numeric_values_outside_codes(numeric_candidate):
        raise TranslationRejected("NUMERIC_LITERAL_CHANGED")
    if [x for x in _split_preserving_newlines(original)[1::2]] != [
        x for x in _split_preserving_newlines(translated)[1::2]
    ]:
        raise TranslationRejected("LINE_BREAK_CHANGED")
    for orig_line, dest_line in zip(
        _split_preserving_newlines(original)[::2],
        _split_preserving_newlines(translated)[::2],
    ):
        if re.match(r"^[ \t\u3000]*", orig_line).group(0) != re.match(
            r"^[ \t\u3000]*", dest_line
        ).group(0):
            raise TranslationRejected("LINE_INDENTATION_CHANGED")
        if re.search(r"[ \t\u3000]*$", orig_line).group(0) != re.search(
            r"[ \t\u3000]*$", dest_line
        ).group(0):
            raise TranslationRejected("LINE_TRAILING_SPACES_CHANGED")
    if source == "ja":
        candidate_prose = "".join(
            fragment for protected, fragment in code_parts(translated)
            if not protected
        )
        if JAPANESE.search(candidate_prose):
            raise TranslationRejected("UNTRANSLATED_JAPANESE_PROSE")
    for keyword in required_terms:
        if keyword.casefold() not in translated.casefold():
            raise TranslationRejected("REQUIRED_SEMANTIC_TERM_MISSING")


def contextualize_name_code_source(original: str) -> tuple[str, tuple[str, ...]]:
    """Expose a name-variable's grammatical role without sending RPG syntax.

    A leading RPG name token followed by a Japanese topic/subject/object
    particle otherwise gets split away from the clause before inference.
    Replace one unambiguous name token with a neutral Japanese noun for the
    model, then restore the exact original token in Spanish output.
    """
    pattern = re.compile(r"\\N\[\d+\](?=[はがをにへと])")
    matches = list(pattern.finditer(original))
    if not matches:
        return original, ()
    unique_codes = {match.group(0) for match in matches}
    if len(matches) != 1 or len(unique_codes) != 1:
        raise TranslationRejected("CONTEXTUAL_NAME_CODE_CARDINALITY_UNSUPPORTED")
    code = matches[0].group(0)
    contextualized = original[:matches[0].start()] + "登場人物" + original[matches[0].end():]
    return contextualized, (code,)


def restore_contextual_name_codes(
    translated: str, codes: tuple[str, ...]
) -> str:
    """Restore name variables after the model has translated their clause."""
    result = translated
    for code in codes:
        alias = re.compile(
            r"\b(?:(?:el|la|un|una|este|esta|ese|esa)\s+)?"
            r"(?:personaje|persona|protagonista|individuo)\b",
            re.IGNORECASE,
        )
        match = alias.search(result)
        if match:
            result = result[:match.start()] + code + " " + result[match.end():].lstrip()
        else:
            # Spanish permits a null subject. Preserve the source's explicit
            # RPG name token even when the model omits the noun phrase.
            result = code + " " + result.lstrip()
    return result


def translate_checked(
    original: str,
    model_translate: Callable[[str], str],
    *,
    source: str = "ja",
    glossary: Mapping[str, str] | None = None,
    required_terms: tuple[str, ...] = (),
    protect_numbers: bool = True,
    inline_glossary: bool = False,
    split_model_sentences: bool | str = True,
    contextualize_name_codes: bool = False,
) -> str:
    """Route only prose to a supplied model, then validate before caching.

    This harness deliberately provides NO neural model. The caller must supply
    an appropriately licensed translator; public CI uses deterministic fakes.
    """
    model_source = original
    contextual_name_codes: tuple[str, ...] = ()
    if contextualize_name_codes and source == "ja":
        model_source, contextual_name_codes = contextualize_name_code_source(original)
    if split_model_sentences not in (True, False, "lines", "document"):
        raise ValueError("UNKNOWN_SENTENCE_SEGMENTATION_MODE")
    protected, mapping = protect_literals(
        model_source, source=source, glossary=glossary,
        protect_numbers=protect_numbers,
        inline_glossary=inline_glossary,
    )
    translated_chunks = []
    for protected_code, fragment in code_parts(protected):
        if protected_code or not fragment or not fragment.strip():
            translated_chunks.append(fragment)
            continue
        sentence_results: list[tuple[str, str]] = []
        if split_model_sentences == "lines":
            sentences = _split_preserving_newlines(fragment)
        elif split_model_sentences == "document":
            sentences = [fragment]
        elif split_model_sentences is True:
            sentences = split_sentences(fragment)
        else:
            sentences = [fragment]
        for sentence in sentences:
            if not sentence or sentence in ("\r\n", "\r", "\n"):
                sentence_results.append((sentence, sentence))
                continue
            if not (JAPANESE.search(sentence) or re.search(r"[A-Za-z]", sentence)):
                sentence_results.append((sentence, sentence))
                continue
            value = model_translate(sentence)
            if (not isinstance(value, str) or not value.strip()
                    or (split_model_sentences != "document"
                        and ("\n" in value or "\r" in value))):
                raise TranslationRejected("MODEL_RESULT_MALFORMED")
            sentence_results.append((sentence, value))
        if split_model_sentences is True:
            translated_chunks.append(_join_spanish_sentences(sentence_results))
        else:
            translated_chunks.append("".join(value for _, value in sentence_results))
    intermediate = "".join(translated_chunks)
    restored_prose = restore_literals(intermediate, mapping)
    if split_model_sentences == "document":
        restored_prose = _restore_document_line_breaks(original, restored_prose)
    restored = restore_layout(
        original,
        restore_contextual_name_codes(restored_prose, contextual_name_codes),
    )
    validate_translation(original, restored, source=source, required_terms=required_terms)
    return restored
