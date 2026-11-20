"""Regression tests for failures that passed the initial 35-case suite."""
import tempfile
import unittest

from translation_lab.pipeline import (
    TranslationRejected, protect_literals, restore_literals, translate_checked,
    validate_translation,
)
from translation_lab.cache import DurableTranslationCache


class NumericAndDialogueRegressionTests(unittest.TestCase):
    def test_numeric_identifiers_preserve_adjacent_letters(self):
        for source in ("HP99", "nivel12", "v2.3", "XP10/20", "ID-0007", "12:51"):
            with self.subTest(source=source):
                protected, mapping = protect_literals(source, source="en")
                self.assertEqual(restore_literals(protected, mapping), source)

    def test_numeric_invariant_rejects_altered_times_dates(self):
        for before, after in (
            ("Hoy a las 12:51.", "Hoy a las 12:50."),
            ("La fecha es 2026-11-19.", "La fecha es 2025-11-19."),
            ("HP99 puntos.", "HP100 puntos."),
            ("2026年の学校。", "La escuela en 2025."),
        ):
            with self.subTest(original=before):
                with self.assertRaises(TranslationRejected):
                    validate_translation(before, after)

    def test_numeric_invariant_rejects_removed_duplicate(self):
        with self.assertRaises(TranslationRejected):
            validate_translation("El precio es 12 y 12.", "El precio es 12.", source="en")

    def test_native_code_numbers_do_not_count_as_prose_numbers(self):
        validate_translation(r"\V[12] 2026年", r"\V[12] Año 2026")

    def test_corrupted_cached_time_is_not_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            original = "La clase empieza a las 12:51."
            with DurableTranslationCache(folder) as cache:
                cache.put("en", "es", original, "La clase empieza a las 12:51.")
                with cache.connection:
                    cache.connection.execute(
                        "UPDATE translations SET translated=? WHERE original=?",
                        ("La clase empieza a las 12:50.", original),
                    )
                self.assertIsNone(cache.get("en", "es", original))

    def test_sentence_aware_translation_routes_each_sentence(self):
        calls = []
        def translate_piece(sentence):
            calls.append(sentence)
            data = {"学校へ行く。": "Voy a la escuela.",
                    "明日も行く。": "Mañana también iré."}
            if sentence not in data:
                raise AssertionError("Unsplit Japanese narrative sent to model: " + sentence)
            return data[sentence]
        result = translate_checked("学校へ行く。明日も行く。", translate_piece)
        self.assertEqual(calls, ["学校へ行く。", "明日も行く。"])
        self.assertEqual(result, "Voy a la escuela. Mañana también iré.")

    def test_multiline_sentence_translation_keeps_crlf(self):
        source = "学校へ行く。\r\n明日も行く。"
        def translator(fragment):
            return {"学校へ行く。": "Voy a la escuela.",
                    "明日も行く。": "Mañana también iré."}[fragment]
        self.assertEqual(
            translate_checked(source, translator),
            "Voy a la escuela.\r\nMañana también iré.",
        )

    def test_temporary_marker_never_reaches_model_after_sentence_split(self):
        calls = []
        def translator(fragment):
            calls.append(fragment)
            self.assertNotIn(r"\V[987", fragment)
            return (fragment.replace("今日は", "Hoy ")
                    .replace("明日も", "Mañana también ")
                    .replace("。", "."))
        source = "今日は学校。明日も学校。"
        result = translate_checked(
            source, translator, glossary={"学校": "escuela"},
            required_terms=("escuela",),
        )
        self.assertEqual(result.count("escuela"), 2)
        self.assertTrue(calls)


if __name__ == "__main__":
    unittest.main()
