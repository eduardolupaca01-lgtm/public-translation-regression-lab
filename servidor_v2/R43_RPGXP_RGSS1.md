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

## Stage 2: raw script archive and native presentation lab

The new Go reader accepts only the Ruby 1.8 raw Scripts.rxdata array of triples, with bounded sizes and zlib validation. It preserves original serialized rows byte-for-byte and inserts a separately owned script immediately before the sole Main section. A laboratory stage writes the original backup, the candidate and a SHA-256 receipt outside the game, never activating the candidate. Unknown tags, links, encoding wrappers, duplicate Main, invalid compression and already-installed plugin are rejected. The Ruby 1.8-style presentation prototype handles stock-style Window_Message first display and choice text using a replaceable transport, preserving control codes, numbers, original event strings and callbacks. Unknown controls, invalid UTF-8, numeric input, missing transport and timeouts fail open; no overlay is created. The desktop Ruby fixture is not RGSS1. The actual game, 32-bit launcher, authenticated OPUS transport, installer activation/recovery, F10 and menu/battle coverage still require integration. The production XP installation gate stays closed; no release is built. References: https://ruby-doc.org/core-2.5.8/doc/marshal_rdoc.html ; https://www.rpg-maker.fr/dl/monos/aide/xp/source/rgss/rgss.html .

## Stage 2b — Windows CRLF and actual worker transport laboratory

The first Stage 2 CI passed Ubuntu; Windows rejected the owned Ruby script because checkout used CRLF while the marker gate only accepted LF. The fix accepts exactly either newline, preserves the script bytes, and rejects marker suffixes. The Ruby prototype no longer relies on an enumerator returned by each_with_index and normalizes full-width digits for validation. A separate XP profile in the existing authenticated file bridge and an explicit, non-CLI XP laboratory mode connect the Ruby client to the same worker Service and SQLite memory. The cross-language fixture starts a fresh Ruby process twice, validates native first paint and choice state, and requires zero repeated inference on the second run. Only the inference backend is mocked. The new path remains intentionally unavailable through the production installer or automatic launcher; no commercial game or authentic RGSS1 DLL is executed, no new OPUS package is published. Next release gate: verified launcher/receipt, real OPUS, exact activation and restoration on a closed loose XP copy, and native RGSS1 runtime validation.
