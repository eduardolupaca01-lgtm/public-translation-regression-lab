"""Benchmark NLLB 600M Japanese-to-Spanish using only public research weights.

IMPORTANT: The upstream model is CC-BY-NC-4.0 and explicitly research-only.
Its results are NOT licensed or certified for commercial production. The
download is ephemeral and no model weights or private software enter Git.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from tools.direct_marian_acceptance import run
from tools.neural_acceptance import verify_phase

MODEL_ID = "facebook/nllb-200-distilled-600M"


def _load_public_research_model():
    import torch
    from transformers import AutoModelForSeq2SeqLM, NllbTokenizerFast

    torch.set_num_threads(2)
    tokenizer = NllbTokenizerFast.from_pretrained(
        MODEL_ID, src_lang="jpn_Jpan", trust_remote_code=False,
    )
    target_lang_id = tokenizer.convert_tokens_to_ids("spa_Latn")
    if (not isinstance(target_lang_id, int) or
            target_lang_id == tokenizer.unk_token_id):
        raise RuntimeError("NLLB_TARGET_LANG_TOKEN_NOT_FOUND")
    model = AutoModelForSeq2SeqLM.from_pretrained(
        MODEL_ID, trust_remote_code=False,
    )
    model.eval()

    class _Nllb:
        def translate(self, text: str) -> str:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("NLLB_NON_TEXT_OR_EMPTY_SOURCE")
            tokens = tokenizer([text], return_tensors="pt", truncation=False)
            if tokens["input_ids"].shape[-1] > 512:
                raise ValueError("NLLB_MAX_SOURCE_TOKENS_EXCEEDED")
            with torch.inference_mode():
                generated = model.generate(
                    **tokens,
                    forced_bos_token_id=target_lang_id,
                    max_new_tokens=256,
                    num_beams=4,
                    renormalize_logits=True,
                )
            candidates = tokenizer.batch_decode(
                generated, skip_special_tokens=True,
            )
            if len(candidates) != 1 or not isinstance(candidates[0], str):
                raise ValueError("NLLB_RESULT_MALFORMED")
            return candidates[0]

    metadata = [{
        "model_id": MODEL_ID,
        "architecture": model.__class__.__name__,
        "source": "jpn_Jpan",
        "target": "spa_Latn",
        "declared_license": "cc-by-nc-4.0",
        "research_only_not_production": True,
        "model_page": "https://huggingface.co/" + MODEL_ID,
        "trust_remote_code": False,
        "forced_bos_token_id": target_lang_id,
    }]
    return _Nllb(), metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("translate", "verify"))
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    if args.phase == "verify":
        return verify_phase(args.workspace)
    return run(
        args.workspace,
        model_loader=_load_public_research_model,
        model_kind="REAL_NEURAL_PUBLIC_NLLB_RESEARCH_NOT_ORIGINAL_PRIVATE_MODEL",
    )


if __name__ == "__main__":
    sys.exit(main())
