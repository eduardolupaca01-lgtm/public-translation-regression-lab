# TENSHIXGAME — RPG Maker VX Ace / RGSS3

This is an isolated adapter family for the VX Ace runtime. It does not reuse MV/MZ JavaScript hooks.

## Engine fingerprint

The supplied game-folder screenshot showed `Game.exe`, `Game.ini`, and `Game.rgss3a`, the deployed VX Ace / RGSS3 layout. VX Ace stores project data as Ruby Marshal 4.8 (`.rvdata2`) and can package it in `.rgss3a`.

## Available helper commands

Build the helper from this directory:

```sh
cargo build --release
```

Inspect a game folder without modifying it:

```sh
tenshixgame-rgss3-probe inspect <game-root>
```

Install the native runtime into a CLOSED TEST COPY:

```sh
tenshixgame-rgss3-probe install <game-root> <IATraductora_RGSS3.rb>
```

Restore the exact original archive from the verified backup:

```sh
tenshixgame-rgss3-probe restore <game-root>
```

The installer updates only the `Data/Scripts.rvdata2` entry inside `Game.rgss3a`. It verifies the rebuilt archive and each non-script entry, creates a SHA-256-addressed backup and a receipt, and refuses restoration if the installed archive has been changed by another program. Synthetic fixtures exercise install and byte-identical restore.

## Runtime and V95 bridge

The Ruby runtime uses VX Ace native event commands for dialogue (`101`), choices (`102`) and scroll text (`105`). It starts the existing local V95 worker, reads the sidecar bridge, sends authenticated batches to `/translate_batch`, and restores RGSS control codes before displaying text. F10 is a diagnostic panel only; it does not replace the game's input map.

The worker recognizes packed RGSS3A and loose VX Ace data, writes its bridge under `IA Traductora/.local/Rpg/`, and reuses the existing translation service and cache.

## Test coverage

GitHub Actions tests:
- RGSS3A header, path traversal and archive round-trip.
- Ruby Marshal script export/rebuild, runtime insertion before Main, and archive preservation.
- Backup, receipt, install and byte-identical restore on synthetic VX Ace fixtures.
- Worker detection, bridge publication, authenticated HTTP batch, cache/order behavior and rejection paths.
- Ruby runtime event hooks, control-code preservation and F10 edge-trigger behavior against minimal engine stubs.
- Windows x64 compilation and Ruby syntax, plus Linux/Windows Rust and Python checks.

These tests use synthetic game fixtures and stubs. They do **not** replace a smoke test against an authorized, real VX Ace game running under its bundled RGSS3 runtime.

## Integration boundary

The Rust helper and runtime are implemented and tested independently. The existing Go installer/UI and the release package builder still need an RGSS3 dispatch/package path before a user can select a VX Ace `Game.exe` in the graphical installer. The current Go detection path is MV/MZ-oriented. Do not advertise one-click installation or production compatibility until that packaging/UI integration and a real-game smoke test pass.

## Dependencies and licensing

Pinned build-time libraries:
- `rpgmad-lib 7.0.0` for RGSS3A archive reading and writing.
- `rvpacker-txt-rs-lib 19.0.1` for VX Ace Marshal script export and rebuild.

Both upstream libraries are WTFPL. They are build-time dependencies, not runtime downloads. V95 remains the translation engine.

## Safety boundaries

- Inspect never executes `Game.exe` and extracts only `Data/` to a temporary directory.
- Install is intended only for a closed test copy; it changes the archive's Scripts entry and nothing else.
- Loose and packed layouts mixed together, invalid archive signatures, unsafe paths, duplicate entries, oversized expansions and malformed Marshal data are rejected.
- Saves, maps, audio, graphics, system data and other non-script archive entries are preserved byte-for-byte in the synthetic verification tests.
