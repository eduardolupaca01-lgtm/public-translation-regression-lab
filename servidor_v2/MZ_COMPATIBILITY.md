# Servidor v2 — MV/MZ R1 (2026-11-24)

Baseline: MV R4P9, commit dc6ff693c136ec8d09fc555723d24d3ef0fc6e43, validated by the owner. New isolated branch. No merge into the MV reference branch.

- Shared local neural worker, original OPUS models, authenticated loopback, durable per-game cache, inventory, continuous scheduler, and verified recovery.
- MZ adapter for Rectangle, Window_NameBox, ColorManager, textSizeEx, native choice labels and help refresh. Game choice arrays and speaker identities stay unchanged in MZ.
- Detect both native layouts (root or www); reject ambiguous markers and incomplete MZ core. Never interpret arbitrary plugin command 357 arguments as translatable text.
- All tests use synthetic game data. Unknown third-party MZ plugins still need specific verification. Do not publish a final Windows package until real-model gates and in-game tests have been checked.

References: https://developer.rpgmakerweb.com/rpg-maker-mz/Window.html ; https://rpgmakerofficial.com/product/MZ_help-en/01_10_01.html ; https://github.com/tonbijp/RPGMakerMZ/blob/master/Reference/Window_Message.md ; https://github.com/tonbijp/RPGMakerMZ/blob/master/Reference/Window_Base.md .
