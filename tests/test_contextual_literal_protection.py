"""Tests for preserving literal tokens without fragmenting translation context."""
import re
import unittest

from translation_lab.pipeline import (
    TranslationRejected,
    translate_checked,
)


MARKER = re.compile(r"ZXQPH(?:CODE|NUM|TERM)\d+QXZ")


class TestContextualLiteralProtection(unittest.TestCase):
    def test_control_code_and_number_stay_in_the_same_model_context(self):
        observed = []

        def fake_translate(fragment):
            observed.append(fragment)
            markers = MARKER.findall(fragment)
            self.assertEqual(len(markers), 2)
            return (
                "Mañana, " + markers[0]
                + " regresará a las " + markers[1] + " de la tarde."
            )

        source = "明日、\\N[3]は午後6時に戻ります。"
        translated = translate_checked(
            source,
            fake_translate,
            source="ja",
            protect_numbers=True,
            contextualize_name_codes=False,
            protect_literals_in_context=True,
            split_model_sentences="document",
        )
        self.assertEqual(
            translated,
            "Mañana, \\N[3] regresará a las 6 de la tarde.",
        )
        self.assertEqual(len(observed), 1)
        self.assertIn("明日", observed[0])
        self.assertIn("午後", observed[0])
        self.assertNotIn(r"\N[3]", observed[0])
        self.assertNotIn("6", observed[0])
        self.assertEqual(len(MARKER.findall(observed[0])), 2)

    def test_document_line_breaks_and_two_numeric_literals_are_restored(self):
        observed = []

        def fake_translate(fragment):
            observed.append(fragment)
            markers = MARKER.findall(fragment)
            self.assertEqual(len(markers), 3)
            return (
                "Mañana, " + markers[0] + " regresará a las "
                + markers[1] + " de la tarde.\r\n"
                "La recepción abrirá a las " + markers[2] + " de la mañana."
            )

        source = (
            "明日、\\N[3]は午後6時に戻ります。\r\n"
            "受付は午前9時に開きます。"
        )
        translated = translate_checked(
            source,
            fake_translate,
            source="ja",
            protect_numbers=True,
            contextualize_name_codes=False,
            protect_literals_in_context=True,
            split_model_sentences="document",
        )
        self.assertIn("\r\n", translated)
        self.assertEqual(
            translated,
            (
                "Mañana, \\N[3] regresará a las 6 de la tarde.\r\n"
                "La recepción abrirá a las 9 de la mañana."
            ),
        )
        self.assertEqual(len(observed), 1)

    def test_missing_marker_is_rejected(self):
        source = "明日、\\N[3]は戻ります。"
        with self.assertRaises(TranslationRejected):
            translate_checked(
                source,
                lambda _fragment: "Mañana regresará.",
                source="ja",
                protect_literals_in_context=True,
                contextualize_name_codes=False,
                split_model_sentences="document",
            )

    def test_duplicated_marker_is_rejected(self):
        source = "明日、\\N[3]は戻ります。"

        def duplicate(fragment):
            marker = MARKER.findall(fragment)[0]
            return "Mañana " + marker + " y " + marker + " regresará."

        with self.assertRaises(TranslationRejected):
            translate_checked(
                source,
                duplicate,
                source="ja",
                protect_literals_in_context=True,
                contextualize_name_codes=False,
                split_model_sentences="document",
            )

    def test_reordered_markers_follow_spanish_grammar_and_are_restored(self):
        # Japanese places the time before the named subject; natural Spanish
        # places the subject before the time. Both immutable markers must survive.
        source = "午後6時に\\N[3]は来ます。"
        observed = []

        def reorder(fragment):
            markers = MARKER.findall(fragment)
            observed.extend(markers)
            self.assertEqual(len(markers), 2)
            # Source order: numeric time, then name code.
            # Spanish order: name code, then numeric time.
            return markers[1] + " llegará a las " + markers[0] + "."

        translated = translate_checked(
            source,
            reorder,
            source="ja",
            protect_numbers=True,
            contextualize_name_codes=False,
            protect_literals_in_context=True,
            split_model_sentences="document",
        )
        self.assertEqual(translated, "\\N[3] llegará a las 6.")
        self.assertEqual(len(observed), 2)
        self.assertEqual(len(set(observed)), 2)


if __name__ == "__main__":
    unittest.main()
