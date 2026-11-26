# Third-party dependency notices

The VX Ace adapter consumes the following pinned libraries. Their source code is not copied into this repository; each remains governed by its own license.

| Crate | Pinned version | Declared license | Upstream |
|---|---:|---|---|
| rpgmad-lib | 7.0.0 | WTFPL | https://github.com/RPG-Maker-Translation-Tools/rpgm-archive-decrypter-lib |
| rvpacker-txt-rs-lib | 19.0.1 | WTFPL | https://github.com/RPG-Maker-Translation-Tools/rvpacker-txt-rs-lib |
| marshal-rs | 4.0.1 | WTFPL | https://github.com/savannstm/marshal-rs |
| tempfile | 3.23.0 | MIT OR Apache-2.0 | https://github.com/Stebalien/tempfile |

marshal-rs is a direct development dependency for synthetic test fixtures and is also used by rvpacker-txt-rs-lib. tempfile is a direct runtime dependency used only to stage complete output trees before publishing them. The optional gxhash feature in rvpacker-txt-rs-lib is not enabled by this crate.

The exact dependency versions are pinned in Cargo.toml. Before producing a distributable package, include the upstream license texts and a complete transitive dependency/license inventory generated from the resolved Cargo graph.
