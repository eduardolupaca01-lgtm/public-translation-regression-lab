"""Offline safety tests for the PUBLIC experimental RPG desktop build."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools.public_rpg_trial import (
    PUBLIC_RUNTIME, RPG_FILES, export_rpg, locate_rpg_data,
    translate_event_tree, translate_text,
)
from translation_lab.cache import DurableTranslationCache
from translation_lab.pipeline import JAPANESE, TranslationRejected


class TestPublicRPGTrial(unittest.TestCase):
    def test_scope_is_public_model_not_private_application(self):
        self.assertIn("argos-translate", PUBLIC_RUNTIME)
        self.assertTrue(RPG_FILES.fullmatch("Map001.json"))
        self.assertTrue(RPG_FILES.fullmatch("Map1000.json"))
        self.assertIsNone(RPG_FILES.fullmatch("Actors.json"))
        self.assertIsNone(RPG_FILES.fullmatch("Map001.json.exe"))

    def test_exact_rpg_codes_and_logic_remain_intact(self):
        event = {
            "events": [{
                "pages": [{
                    "list": [
                        {"code": 401, "indent": 0, "parameters": [r"\V[2]は好きです。"]},
                        {"code": 405, "indent": 0, "parameters": ["ありがとう。"]},
                        {"code": 102, "indent": 0, "parameters": [
                            ["はい。", "いいえ。"], 0, 0, 2, 0]},
                        {"code": 402, "indent": 0, "parameters": [0, "はい。"]},
                        {"code": 111, "indent": 0, "parameters": [1, 2, 0, 17, 0]},
                        {"code": 355, "indent": 0, "parameters": ["$gameVariables.value(2);"]},
                    ]
                }]
            }]
        }
        frozen = copy.deepcopy(event)
        def fake(text):
            from translation_lab.pipeline import translate_checked
            return translate_checked(text, lambda _: "Sí.")
        number = translate_event_tree(event, fake)
        self.assertEqual(number, 5)
        commands = event["events"][0]["pages"][0]["list"]
        self.assertIn(r"\V[2]", commands[0]["parameters"][0])
        self.assertFalse(JAPANESE.search(commands[0]["parameters"][0]))
        self.assertEqual(commands[4:], frozen["events"][0]["pages"][0]["list"][4:])
        self.assertEqual(commands[2]["parameters"][0][0], commands[3]["parameters"][1])
        self.assertEqual(commands[2]["parameters"][1:], frozen["events"][0]["pages"][0]["list"][2]["parameters"][1:])
        self.assertEqual(frozen["events"][0]["pages"][0]["list"][1]["parameters"][0], "ありがとう。")

    def test_export_to_new_directory_does_not_touch_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "game" / "www" / "data"
            data.mkdir(parents=True)
            origin = data / "Map001.json"
            events = {"events": [None, {"pages": [{"list": [
                {"code": 401, "indent": 0, "parameters": ["ありがとう。"]},
                {"code": 111, "indent": 0, "parameters": [1, 2, 0, 17, 0]},
            ]}]}]}
            origin.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
            original_bytes = origin.read_bytes()
            report = export_rpg(
                root / "game", root / "new-out",
                lambda text: "Gracias.",
            )
            self.assertEqual(report["event_segments_translated"], 1)
            self.assertFalse(report["original_game_modified"])
            self.assertEqual(origin.read_bytes(), original_bytes)
            translated = json.loads((root / "new-out" / "Map001.json").read_text(encoding="utf-8"))
            self.assertEqual(
                translated["events"][1]["pages"][0]["list"][0]["parameters"][0],
                "Gracias.",
            )
            self.assertEqual(
                translated["events"][1]["pages"][0]["list"][1],
                events["events"][1]["pages"][0]["list"][1],
            )
            self.assertEqual(locate_rpg_data(root / "game"), data)

    def test_refuse_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game" / "data"
            game.mkdir(parents=True)
            (game / "Map001.json").write_text(
                json.dumps({"events": []}), encoding="utf-8"
            )
            out = root / "out"
            out.mkdir()
            (out / "sentinel.txt").write_text("do-not-touch", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                export_rpg(game.parent, out, lambda text: "Hola.")
            self.assertEqual((out / "sentinel.txt").read_text(), "do-not-touch")
            with self.assertRaises(ValueError):
                export_rpg(game.parent, game.parent / "out", lambda text: "Hola.")

    def test_translation_failure_rolls_back_without_creating_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            game = root / "game" / "data"
            game.mkdir(parents=True)
            (game / "Map001.json").write_text(
                json.dumps({"events": [{"pages": [{"list": [
                    {"code": 401, "parameters": ["ありがとうございます。"]},
                    {"code": 401, "parameters": ["学校はどこですか？"]},
                ]}]}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            out = root / "out"
            def reject(second):
                if "学校" in second:
                    raise TranslationRejected("INTENTIONAL_TEST_MODEL_REJECTION")
                return "Gracias."
            with self.assertRaises(TranslationRejected):
                export_rpg(game.parent, out, reject)
            self.assertFalse(out.exists())

    def test_sqlite_reuses_valid_neural_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            seen = []
            def translator(text):
                seen.append(text)
                return "Gracias."
            with DurableTranslationCache(Path(tmp) / "cache") as cache:
                source = "ありがとうございます。"
                self.assertEqual(translate_text(source, translator, cache), "Gracias.")
                self.assertEqual(translate_text(source, translator, cache), "Gracias.")
                self.assertEqual(translate_text("No Japanese here", translator, cache),
                                 "No Japanese here")
                self.assertEqual(len(seen), 1)
            with DurableTranslationCache(Path(tmp) / "cache") as cache:
                self.assertEqual(cache.get("ja", "es", source), "Gracias.")
            self.assertEqual(len(seen), 1)

    def test_does_not_translate_code_only_or_non_rpg_fields(self):
        node = {"events": [
            {"pages": [{"list": [
                {"code": 401, "parameters": [r"\V[2]"]},
                {"code": 355, "parameters": ["学校はどこですか？"]},
                {"code": 102, "parameters": [["Yes", "No"], 0, 0, 2, 0]},
            ]}]}
        ]}
        calls = []
        self.assertEqual(translate_event_tree(node, lambda x: calls.append(x)), 0)
        self.assertEqual(calls, [])
        self.assertEqual(node["events"][0]["pages"][0]["list"][1]["parameters"][0],
                         "学校はどこですか？")


if __name__ == "__main__":
    unittest.main()
