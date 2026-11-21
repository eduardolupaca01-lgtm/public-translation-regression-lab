"""Uniform Qwen3-8B thinking v3 prompt for source-complete Spanish dialogues.

Same pinned model, sampler and quantization as Stage5; no target-specific
replacements, no Spanish answers from earlier runs, no case-specific prompt.
This is an experiment, not a claim of improved quality until measured.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from tools import qwen3_8b_thinking_ja_es_candidate as thinking
from tools.qwen3_stage3_holdout import THINKING_REQUEST_TIMEOUT_SECONDS
from tools.stage4_source_complete_candidate import (
    SourceCompleteThinkingTranslator, SOURCE_COMPLETE_PROMPT,
)


GENERATION_VARIANT = "uniform_discourse_conditions_grammar_v3"
DISCOURSE_GUIDANCE = """

Additional uniform checks for EVERY source before returning the final Spanish:
- Japanese conditional markers such as なら, たら, ば and 場合 connect a
  condition to its consequence. Express the condition explicitly, such as
  with 'si' or an equivalent natural construction, especially when a game
  variable or a numeric value controls permission, prohibition or entry.
  Never present a bare condition and consequence as unrelated fragments.
- Preserve who performs each action and who receives the object. Confirm
  Spanish direct-object pronouns agree with the noun's grammatical gender;
  'someone sees no one' and 'no one sees someone' are NOT interchangeable.
- Avoid redundantly saying a time word twice; render relative dates such
  as tomorrow and the day after tomorrow naturally and consistently.
- Keep contrasting alternatives separate, including changes to permission
  and negation, quantity thresholds, dates and relative positions.
- Preserve every RPG control code verbatim, exactly as many times as in
  the source, with its surrounding conditional logic, line breaks and
  dialogue roles intact. Never resolve control codes into guessed names.
- Read each finished Spanish sentence for complete grammar before output;
  do not add explanatory notes, reference translations or invented facts.

Apply this same checklist to all inputs without any case-specific examples.
"""
DISCOURSE_V3_GUIDANCE = """

Uniform final bilingual proofreading for ALL Japanese sources:
- Do not equate permission to do something with a hypothetical or unrealised
  opportunity; when Japanese permits an action in the past, express the
  permission or ability in clear Spanish without implying it happened.
- Check grammatical agreement of every Spanish article, adjective, and
  direct-object pronoun with the Spanish noun (e.g. feminine and masculine
  nouns), even after numbers and currency.
- Preserve the original character's name consistently throughout all
  dialogue turns. Do not alter transliteration/spelling between speakers.
- Quantifiers such as 'everyone', 'no one', 'nobody', 'still not' and 'yet'
  identify the actor and scope of an event. Never swap observer and object.
- Render Japanese plurals and adjectives in idiomatic Spanish singular or
  plural. Avoid omitting a negative condition, recipient or connective.
This is the SAME instruction for EVERY input; return only the translation.
"""
SYSTEM_PROMPT = SOURCE_COMPLETE_PROMPT + DISCOURSE_GUIDANCE + DISCOURSE_V3_GUIDANCE
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


class DiscourseThinkingTranslator(SourceCompleteThinkingTranslator):
    @staticmethod
    def build_payload(text: str) -> dict:
        payload = SourceCompleteThinkingTranslator.build_payload(text)
        payload["messages"][0]["content"] = SYSTEM_PROMPT
        return payload


def load_model(llama_server: Path, workspace: Path):
    original, provenance = thinking._load_model(llama_server, workspace)
    sender = original.request_json

    def cpu_budget(url: str, payload: dict, timeout: int) -> dict:
        return sender(
            url, payload, max(timeout, THINKING_REQUEST_TIMEOUT_SECONDS)
        )

    enhanced = DiscourseThinkingTranslator(
        endpoint=original.endpoint,
        process=original.process,
        log_handle=original.log_handle,
        request_json=cpu_budget,
    )
    provenance[0].update({
        "generation_variant": GENERATION_VARIANT,
        "translation_system_prompt_sha256": PROMPT_SHA256,
        "http_request_timeout_seconds": THINKING_REQUEST_TIMEOUT_SECONDS,
        "target_side_repairs": False,
        "reference_spanish_provided_to_model": False,
    })
    return enhanced, provenance
