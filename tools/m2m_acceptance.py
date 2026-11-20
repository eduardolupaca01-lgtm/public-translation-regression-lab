"""Real public M2M100 multilingual Japanese-to-Spanish model acceptance.

Uses the official MIT-licensed facebook/m2m100_418M model in a temporary CI
directory. It imports neither private games nor original neural packages.
The exact same 12 strict semantic and SQLite acceptance checks are reused.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from tools.direct_marian_acceptance import run
from tools.neural_acceptance import verify_phase

MODEL_ID = "facebook/m2m100_418M"


def _load_public_m2m_model():
    import torch
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

    torch.set_num_threads(2)
    tokenizer = M2M100Tokenizer.from_pretrained(
        MODEL_ID, src_lang="ja", trust_remote_code=False
    )
    if not hasattr(tokenizer, "get_lang_id"):
        raise RuntimeError("PUBLIC_M2M100_MISSING_LANGUAGE_CODES")
    spanish_id = tokenizer.get_lang_id("es")
    if not isinstance(spanish_id, int):
        raise RuntimeError("PUBLIC_M2M100_SPANISH_LANGUAGE_ID_INVALID")
    model = M2M100ForConditionalGeneration.from_pretrained(
        MODEL_ID, trust_remote_code=False
    )
    model.eval()

    class _M2M:
        def translate(self, text: str) -> str:
            if not isinstance(text, str) or not text.strip():
                raise RuntimeError("M2M100_NON_TEXT_OR_EMPTY_SOURCE")
            encoded = tokenizer([text], return_tensors="pt", truncation=False)
            if encoded["input_ids"].shape[-1] > 512:
                raise RuntimeError("M2M100_CONTEXT_WINDOW_EXCEEDED")
            with torch.inference_mode():
                generated = model.generate(
                    **encoded, forced_bos_token_id=spanish_id,
                    max_new_tokens=256, num_beams=4,
                    renormalize_logits=True,
                )
            result = tokenizer.batch_decode(generated, skip_special_tokens=True)
            if len(result) != 1 or not isinstance(result[0], str):
                raise RuntimeError("M2M100_INVALID_MODEL_OUTPUT")
            return result[0]

    return _M2M(), [{
        "model_id": MODEL_ID,
        "architecture": model.__class__.__name__,
        "source": "ja", "target": "es",
        "declared_license": "mit",
        "model_page": "https://huggingface.co/" + MODEL_ID,
        "trust_remote_code": False,
        "forced_bos_token_id_for_es": spanish_id,
    }]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    if args.phase == "translate":
        return run(
            args.workspace,
            model_loader=_load_public_m2m_model,
            model_kind="REAL_NEURAL_PUBLIC_M2M100_NOT_ORIGINAL_PRIVATE_MODEL",
        )
    return verify_phase(args.workspace)


if __name__ == "__main__":
    sys.exit(main())
