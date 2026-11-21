# Stage4: bilingual QA + frozen RPG dialogue stress plan

Research-only work on the Eduardo experimental branch. The Stage3 model run
[44893774138](https://github.com/eduardolupaca01-lgtm/public-translation-regression-lab/actions/runs/44893774138)
accepted 10/10 according to the versioned automatic rules and cold restart
integrity; this does **not** establish that all ten outputs are professionally
fluent or semantically exact.

## Actual output review (original model output is never edited)

- `rainy_meeting`: output "nos vemos en la estación" omits "駅の前",
  *in front of the station*. Material location loss.
- `sister_homework`: output "pienso ir al parque juntos" has unnatural
  singular/plural coordination. "La hermana menor" also needs a
  contextual perspective check; Japanese 妹 has no overt possessive.
- `red_and_blue_apples`: "manzana azul" follows the literal color
  but 青いリンゴ often means green apples; a fantasy setting could genuinely
  intend blue apples. Review with visual/narrative context, do not
  automatically rewrite it.

`tools/stage4_bilingual_audit.py` consumes and hashes the **same** original
Stage3 report, frozen manifest and cold restart evidence. It produces a
separate JSON quality receipt that distinguishes material errors from
context-dependent language review. This is post-hoc calibration on a
published research set, not blind external validation or human sign-off.

## Next RPG challenge corpus

`tools/stage4_rpg_stress_cases.py` freezes 12 new Japanese-only text
sources: multiple speakers, protected name/variable codes, CRLF lines,
contrasting instructions, prices, deadlines, item counts, familial roles,
and conditional choices. All 12 are disjoint from the 20 development and
10 Stage3 cases. Its manifest has source hashes and **no Spanish reference
translations**. No new neural evaluation or production integration is
claimed until the bilingual quality gate and separate review are complete.

## Non-negotiable gates

1. Preserve 20/20 development and 10/10 structural research evidence,
   model provenance, and cold SQLite restart receipts.
2. Resolve material omissions and Spanish grammatical defects through a
   new, uniformly configured neural evaluation, not by editing reports,
   hardcoding Spanish target answers, or weakening the existing scorer.
3. Resolve contextual ambiguity with independent bilingual review.
4. Only then run a fresh neural evaluation on the 12 RPG cases with
   literal and control-code integrity, naturalness and persistence checks.
5. Keep the pull request in draft; no merge or distribution.
