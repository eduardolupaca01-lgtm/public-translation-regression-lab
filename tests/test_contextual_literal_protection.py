"""Tests for native RPG placeholders that remain in translation context."""
import re
import unittest

from translation_lab.pipeline import (
    TranslationRejected,
    translate_checked,
)


NUMERIC_MARKER = re.compile(r"\\V\[9\d{5}\]")


class TestContextualLiteralProtection(unittest.TestCase):
    def test_control_code_and_number_stay_in_the_same_model_context(self):
        observed = []

        def fake_translate(fragment):
            observed.append(fragment)
            markers = NUMERIC_MARKER.findall(fragment)
            self.assertEqual(len(markers), 1)
            self.assertIn(r"\N[3]", fragment)
            return (
                "Mañana, \\N[3] regresará a las "
                + markers[0] + " de la tarde."
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
        self.assertIn(r"\N[3]", observed[0])
        self.assertNotIn("6", observed[0])
        self.assertEqual(len(NUMERIC_MARKER.findall(observed[0])), 1)

    def test_document_line_breaks_and_two_numeric_literals_are_restored(self):
        observed = []

        def fake_translate(fragment):
            observed.append(fragment)
            markers = NUMERIC_MARKER.findall(fragment)
            self.assertEqual(len(markers), 2)
            self.assertIn(r"\N[3]", fragment)
            return (
                "Mañana, \\N[3] regresará a las " + markers[0]
                + " de la tarde.\r\n"
                "La recepción abrirá a las " + markers[1] + " de la mañana."
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

    def test_missing_numeric_marker_is_rejected(self):
        source = "明日、\\N[3]は午後6時に戻ります。"
        with self.assertRaises(TranslationRejected):
            translate_checked(
                source,
                lambda _fragment: "Mañana, \\N[3] regresará por la tarde.",
                source="ja",
                protect_numbers=True,
                protect_literals_in_context=True,
                contextualize_name_codes=False,
                split_model_sentences="document",
            )

    def test_duplicated_numeric_marker_is_rejected(self):
        source = "明日、\\N[3]は午後6時に戻ります。"

        def duplicate(fragment):
            marker = NUMERIC_MARKER.findall(fragment)[0]
            return (
                "Mañana, \\N[3] regresará a las " + marker
                + " y luego volverá a las " + marker + "."
            )

        with self.assertRaises(TranslationRejected):
            translate_checked(
                source,
                duplicate,
                source="ja",
                protect_numbers=True,
                protect_literals_in_context=True,
                contextualize_name_codes=False,
                split_model_sentences="document",
            )

    def test_unknown_numeric_marker_is_rejected(self):
        source = "明日、\\N[3]は午後6時に戻ります。"

        def substitute_unknown(fragment):
            marker = NUMERIC_MARKER.findall(fragment)[0]
            return "Mañana, \\N[3] regresará a las " + marker.replace(
                "987650", "999999"
            ) + "."

        with self.assertRaises(TranslationRejected):
            translate_checked(
                source,
                substitute_unknown,
                source="ja",
                protect_numbers=True,
                protect_literals_in_context=True,
                contextualize_name_codes=False,
                split_model_sentences="document",
            )

    def test_name_code_and_numeric_marker_follow_spanish_word_order(self):
        # Japanese places the time before the named subject; natural Spanish
        # places the named subject before the time. Both source literals survive.
        source = "午後6時に\\N[3]は来ます。"
        observed = []

        def reorder_for_spanish(fragment):
            markers = NUMERIC_MARKER.findall(fragment)
            observed.append(fragment)
            self.assertEqual(len(markers), 1)
            self.assertIn(r"\N[3]", fragment)
            return "\\N[3] llegará a las " + markers[0] + "."

        translated = translate_checked(
            source,
            reorder_for_spanish,
            source="ja",
            protect_numbers=True,
            contextualize_name_codes=False,
            protect_literals_in_context=True,
            split_model_sentences="document",
        )
        self.assertEqual(translated, "\\N[3] llegará a las 6.")
        self.assertEqual(len(observed), 1)


if __name__ == "__main__":
    unittest.main()
