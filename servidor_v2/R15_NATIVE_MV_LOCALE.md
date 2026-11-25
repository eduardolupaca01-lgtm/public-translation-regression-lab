# R15 — native MV locale compatibility

R14 remains the base. Only translator code and newly written synthetic fixtures are distributed. No game data, actual catalog text, assets, or user cache is included.

- Detect an exact active native localization contract and bounded, read-only EN/SP catalog pairs under loc/. Preserve REM_* lookup tokens; they are not model inputs.
- Prefer the game's own Spanish text option once at English-language boot, only when the six native Spanish difficulty picture variants are present. The actual native language getter, database lookups, and event branches select their own authored localized assets. No voice settings, game data, saved files, or assets are manually rewritten. Later language choices during the session are not reset.
- Known distinct Spanish catalog text is kept unchanged. Cache/OPUS fallback is restricted to provably missing/unchanged simple complete English prose in the MAP/DESC accessors, with the existing first-view deadline for exact event keys.
- If metadata, locale files or required image variants are absent, do not auto-switch. The normal translator remains available. No OCR, global string replacement or arbitrary script execution.
- The synthetic tests verify native catalog resolution offline, voice preservation, fallback, original identifiers, no double translation, and missing-image protection. Actual graphics and complete game runtime are not included in CI.
