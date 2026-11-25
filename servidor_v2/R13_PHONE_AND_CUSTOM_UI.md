# R13 — phone and custom UI compatibility

Build on R12. No supplied game or cache contents are included.

- PKD PhoneMenu: recognize event lists containing documented phone commands. Preload explicit display text, choices and literal setAnswerForChoice response text. At synchronous interpreter dispatch, prepare a temporary command list containing available validated translations, with a bounded first-view gate. Preserve original data, metadata, choice indices, wait commands and contact/asset identifiers.
- Hendrix Pictures UI Creator: apply the existing bounded MZ notification gate to ShowText's explicit text field. Do not change layout, vocabulary references, dynamic variable-only text, timing, or erase commands.
- Translate known short UI labels and interjections only on confirmed display surfaces. Phone header/typing label fallback is limited to the identified drawing stack and known names.
- A synthetic phone interpreter deliberately bypasses Game_Message. Tests verify first dispatch, custom response, choice branch, source preservation and picture fields.
- Third-party source scripts were not supplied: actual game acceptance is still required; undocumented interpreters that bypass inherited setup/executeCommand or render through another API may need another adapter.
