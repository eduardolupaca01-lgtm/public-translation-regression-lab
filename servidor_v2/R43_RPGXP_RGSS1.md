# Servidor R43 — RPG Maker XP / RGSS1 (development, no release)

Base: approved R42 commit `4165c5d3d69bb26a128ba03e830d061735a84041`. Separate branch; R42 is unchanged.

## Evidence and scope

RPG Maker XP uses RGSS1 (Ruby 1.8-era runtime), unlike VX Ace (RGSS3). Typical deployed markers are a 32-bit RGSS1 DLL, Game.ini pointing to Data/Scripts.rxdata, and loose .rxdata data files. The initial detector verifies native markers without executing code or parsing arbitrary Ruby Marshal objects. It refuses installation and reports a specific diagnostic until an XP adapter is validated. Packed RGSSAD is recognized separately but not modified. Test data is entirely synthetic; no user game assets, DLLs, saves or scripts are included.

Sources: https://store.rpgmakerofficial.com/products/rpg-maker-xp ; https://www.rpg-maker.fr/dl/monos/aide/xp/source/rgss/rgss.html ; https://github.com/Ancurio/mkxp/blob/master/README.md

## Compatibility work required before release

- Create a separate RGSS1 script that uses Ruby 1.8-compatible APIs. XP must not receive the existing RGSS3 Fiber/Encoding implementation.
- Verify the actual game's native Window_Message and Interpreter methods, choices, menu and battle rendering, control codes, and 32-bit Win32API interoperability. Do not assume the VX Ace scene lifecycle or convert arbitrary script text.
- Reuse the existing verified local OPUS worker and authenticated game-local cache where compatible; preserve names, game state, data and save files. Treat non-UTF8 strings explicitly; no global encoding conversion.
- Add a separate, bounded, validated Scripts.rxdata reader/injector, preserving all original Marshal bytes/sections wherever possible, exact backup/recovery, and no deserialization of executable hooks. Do not modify other data or the original game runtime. Scope initial installation to a closed, loose copy; leave encrypted archives unsupported until independently validated.
- Require synthetic tests of the actual XP contracts and native RGSS1 runtime acceptance with OPUS real, alongside every R42 regression. A real-game trial remains necessary before declaring compatibility.

The current change is read-only detection and test infrastructure, not a functioning XP translation installer or downloadable R43.
