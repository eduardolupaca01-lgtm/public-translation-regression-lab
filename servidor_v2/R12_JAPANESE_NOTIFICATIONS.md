# R12 — cobertura de japonés y notificaciones

R11 remained the baseline. Changes are confined to the translator and neutral regression fixtures. No game data or user cache is distributed.

- Keep numeric validation strict. Recover equal Spanish number words only for explicit, unambiguous Japanese counters; never fill in a missing/wrong number. Retry only rejected Japanese segments with ASCII digit input and complete independent sentence decoding, and validate the entire result before persistence.
- Prioritize each visible message line along with the complete block. Do not rerun a native message or overwrite event controls.
- MZ LL_InfoPopupWIndow/showMessage: inventory only the explicit messageText field; wait within existing first-view limits before invoking the native interpreter command once, with a temporary copy of arguments. Never alter timing, position, background, or hide commands. Direct script calls remain cache-first and fail-open.
- Render literal authored speaker roles or evidence-backed kana readings in the native name box. Preserve original speaker and player-entered identity; unknown kanji readings are not guessed.

Tests are synthetic; full OPUS Windows package requires successful CI, and actual-game acceptance remains a separate user verification.
