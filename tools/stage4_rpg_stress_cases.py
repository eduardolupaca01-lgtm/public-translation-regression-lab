"""Frozen, source-only RPG stress-test plan; no translated answers or model run.

These synthetic Japanese lines are disjoint from the previous 20 + 10 test
sources. They include branching, controls, dialogue roles, negation, date and
price changes, and multiline layout. The future neural runner must be gated
on bilingual sign-off of the earlier stage.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import hashlib
import json
from pathlib import Path

from tools.independent_pivot_holdout import INDEPENDENT_CASES
from tools.unseen_holdout import HOLDOUT_CASES


@dataclass(frozen=True)
class StressCase:
    id: str
    japanese: str
    risk: str


STRESS_CASES: tuple[StressCase, ...] = (
    StressCase(
        "speaker_item_owner",
        r"\N[3]「この剣は私のものではありません。\N[5]に返してください。」",
        "Two protected speaker codes; owner and recipient must differ",
    ),
    StressCase(
        "rain_branching",
        "雨がやんだら橋を渡ってください。まだ降っていたら、ここで待っていてください。",
        "Two opposite weather conditions with distinct instructions",
    ),
    StressCase(
        "discount_deadline",
        "昨日は1200円でしたが、今日は900円です。割引が終わる前に買ってください。",
        "Currency values, day qualifiers, deadline",
    ),
    StressCase(
        "multiline_variable",
        "まず扉を閉めてください。\r\nそのあと\\V[2]を確認してください。",
        "Original CRLF and protected RPG variable in the second line",
    ),
    StressCase(
        "family_three_participants",
        "妹は鍵をなくしましたが、兄が見つけました。私はまだ何も知りません。",
        "Younger sibling lost item, older sibling found, speaker unaware",
    ),
    StressCase(
        "appointment_rebooked",
        "火曜日の予約は取り消され、木曜日の午後6時に変更されました。",
        "Cancellation versus rescheduling; weekday and time",
    ),
    StressCase(
        "box_ownership_question",
        "この箱はあなたのものですか。それとも先生のものですか。",
        "Question alternatives, possession and referents",
    ),
    StressCase(
        "speaker_prohibition_direction",
        r"\N[7]「ここでは走らないで。出口は左ではなく右だよ。」",
        "Prohibition, directional contrast, protected speaker",
    ),
    StressCase(
        "quest_item_quantities",
        "赤い薬を三つ集めてから、青い薬を一つだけ渡してください。",
        "Item quantities, colors and action order",
    ),
    StressCase(
        "reported_speech_no_arrival",
        "彼は来ると言いました。しかし、まだ誰も彼を見ていません。",
        "Reported speech, incomplete arrival and negation",
    ),
    StressCase(
        "signing_help_sequence",
        "書類に署名する前に、内容を確認してください。分からなければ受付に聞いてください。",
        "Sequence, understanding condition, reception desk",
    ),
    StressCase(
        "miss_train_no_taxi",
        "もし列車に間に合わなかったら、次の便を待ってください。タクシーには乗らないでください。",
        "Negative train condition and explicit taxi prohibition",
    ),
)


def manifest() -> dict:
    sources = [{"id": c.id, "source": c.japanese, "risk": c.risk}
               for c in STRESS_CASES]
    canonical = json.dumps(sources, ensure_ascii=False, sort_keys=True)
    return {
        "schema": "ja-es-stage4-rpg-stress-source-manifest-v1",
        "count": len(sources),
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "source_only": True,
        "model_inference_executed": False,
        "require_bilingual_review_before_promotion": True,
        "cases": sources,
        "note": "Public synthetic challenge set, not a blind external benchmark",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = manifest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "STAGE4_RPG_SOURCE_MANIFEST "
        + json.dumps({
            "count": result["count"], "sha256": result["sha256"],
            "model_inference_executed": False,
        }, sort_keys=True),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
