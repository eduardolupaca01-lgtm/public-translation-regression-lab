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
INTERNAL_MARKER = re.compile(r"\\V\[9876[5-9]\d+\]|ZXQTX760(?:NUM|TERM)\d+QXZ")


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
    patterns = [re.escape(k) for k in sorted(terms, key=len, reverse=True)]
    patterns.append(NUMERIC)
    literal_re = re.compile("|".join(patterns))
    mapping: dict[str, str] = {}
    next_id = 987650

    def replace(match: re.Match[str]) -> str:
        nonlocal next_id
        token = ""
        while next_id <= 999999:
            candidate = r"\V[" + str(next_id) + "]"
            next_id += 1
            if candidate not in text and candidate not in mapping:
                token = candidate
                break
        if not token:
            raise TranslationRejected("INTERNAL_MARKER_SPACE_EXHAUSTED")
        observed = match.group(0)
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


def _join_spanish_sentences(parts: list[str]) -> str:
    """Insert one boundary only where two translated sentences need it."""
    result = ""
    for part in parts:
        if (result and part and result[-1] in ".!?»…”"
                and part[0] in "¿¡«\"(ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyzÁÉÍÓÚÜÑáéíóúüñ"):
            result += " "
        result += part
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
    if source_numbers and source_numbers != _numeric_values_outside_codes(translated):
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


def translate_checked(
    original: str,
    model_translate: Callable[[str], str],
    *,
    source: str = "ja",
    glossary: Mapping[str, str] | None = None,
    required_terms: tuple[str, ...] = (),
) -> str:
    """Route only prose to a supplied model, then validate before caching.

    This harness deliberately provides NO neural model. The caller must supply
    an appropriately licensed translator; public CI uses deterministic fakes.
    """
    protected, mapping = protect_literals(original, source=source, glossary=glossary)
    translated_chunks = []
    for protected_code, fragment in code_parts(protected):
        if protected_code or not fragment or not fragment.strip():
            translated_chunks.append(fragment)
            continue
        sentence_results: list[str] = []
        for sentence in split_sentences(fragment):
            if not sentence or sentence in ("\r\n", "\r", "\n"):
                sentence_results.append(sentence)
                continue
            if not (JAPANESE.search(sentence) or re.search(r"[A-Za-z]", sentence)):
                sentence_results.append(sentence)
                continue
            value = model_translate(sentence)
            if (not isinstance(value, str) or not value.strip()
                    or "\n" in value or "\r" in value):
                raise TranslationRejected("MODEL_RESULT_MALFORMED")
            sentence_results.append(value)
        translated_chunks.append(_join_spanish_sentences(sentence_results))
    intermediate = "".join(translated_chunks)
    restored = restore_layout(original, restore_literals(intermediate, mapping))
    validate_translation(original, restored, source=source, required_terms=required_terms)
    return restored
