# TENSHIXGAME — RPG Maker VX Ace / RGSS3

This folder starts the VX Ace adapter as an isolated engine family. It is not an MV/MZ plugin and does not reuse JavaScript window hooks.

## Fingerprint from the supplied game folder

The folder contains:

- `Game.exe`
- `Game.ini`
- `Game.rgss3a`

That is the deployed RPG Maker VX Ace layout (RGSS3). VX Ace stores project resources as Ruby Marshal 4.8 data (`.rvdata2`) and may package them in a `.rgss3a` archive. MV/MZ use a different JavaScript/JSON runtime and are not interchangeable.

## First batch: read-only inventory

`tenshixgame-rgss3-probe inspect <game-root>`:

1. Validates the executable/config/archive markers without executing the game.
2. Reads RGSS3A entries using the pinned `rpgmad-lib` implementation.
3. Rejects unsafe paths, duplicate normalized paths, oversized entries and ambiguous packed/loose layouts.
4. Extracts only into a temporary directory, never into the supplied game folder.
5. Uses `rvpacker-txt-rs-lib` to inventory translatable data from VX Ace Marshal files.
6. Emits a JSON report with the archive hash, entry counts, data-file counts, text inventory and parser status.

The probe does not rewrite `Game.rgss3a`, `Scripts.rvdata2`, saves, maps, or any game file. No translation is claimed by this first batch.

## Dependencies and licensing

- `rpgmad-lib 7.0.0`: RGSS archive read/write implementation, WTFPL.
- `rvpacker-txt-rs-lib 19.0.1`: VX Ace Marshal/text extraction and write library, WTFPL.

They are build-time libraries for this adapter. They are not downloaded or installed by the player, and no external translation service is introduced. V95 remains the translation engine.

## Deliberate safety boundary

A packed archive and a loose `Data/` directory at the same time are treated as ambiguous. Encrypted/unsupported layouts, malformed Marshal data, non-standard script containers and paths that cannot be validated are reported as unsupported; the original game is left untouched.

The next integration stage must add a reversible installer, a verified backup/receipt, the RGSS3 runtime bridge to the existing V95 worker, and native message/choice hooks. Those must be tested before the engine is advertised as production-compatible.
