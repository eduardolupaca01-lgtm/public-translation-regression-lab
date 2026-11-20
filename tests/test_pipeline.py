import unittest
from translation_lab.pipeline import (
    TranslationRejected, code_parts, protect_literals, restore_literals,
    split_sentences, restore_layout, validate_translation, translate_checked
)


class TestSourceIntegrity(unittest.TestCase):
    def test_sentence_split_does_not_lose_characters(self):
        cases = [
            "今日は天気がいい。明日は雨？",
            "（私はサッカー部です。友人は水泳部です。）",
            "「おはよう！今日は寝坊しなかったね。」",
            "一行目。\r\n二行目！\n三行目。",
            "",
        ]
        for source in cases:
            self.assertEqual("".join(split_sentences(source)), source)

    def test_native_codes_remain_identical(self):
        source = (r"変数\V[12] と \N[花子] は %1 %s %d ${player7} "
                  r"<span id='44'> と 2026-11-19。")
        protected, mapping = protect_literals(
            source, glossary={"変数": "variable", "花子": "Hanako"}
        )
        original_codes = [s for is_code, s in code_parts(source) if is_code]
        candidate_codes = [
            s for is_code, s in code_parts(protected) if is_code and s not in mapping
        ]
        self.assertEqual(original_codes, candidate_codes)
        self.assertIn(r"\N[花子]", protected)
        self.assertIn(r"\V[12]", protected)
        self.assertIn("${player7}", protected)
        self.assertEqual(restore_literals(protected, mapping).count(r"\N[花子]"), 1)

    def test_numeric_literals_roundtrip(self):
        source = "2026-11-19 a las 12:51, 30 x 40."
        protected, mapping = protect_literals(source, source="en")
        self.assertEqual(restore_literals(protected, mapping), source)
        self.assertNotEqual(protected, source)
        self.assertGreaterEqual(len(mapping), 7)

    def test_semantic_anchors_roundtrip(self):
        source = "午前中、夕方頃。"
        glossary = {
            "午前中": "por la mañana",
            "夕方頃": "alrededor del atardecer",
        }
        protected, mapping = protect_literals(source, glossary=glossary)
        restored = restore_literals(protected, mapping)
        self.assertIn("por la mañana", restored)
        self.assertIn("alrededor del atardecer", restored)
        self.assertNotIn("ZXQTX", restored)

    def test_missing_marker_is_rejected(self):
        protected, mapping = protect_literals("午前中は12時", glossary={"午前中": "mañana"})
        self.assertTrue(mapping)
        token = next(iter(mapping))
        with self.assertRaises(TranslationRejected):
            restore_literals(protected.replace(token, "", 1), mapping)

    def test_duplicate_marker_is_rejected(self):
        protected, mapping = protect_literals("午前中は12時", glossary={"午前中": "mañana"})
        token = next(iter(mapping))
        with self.assertRaises(TranslationRejected):
            restore_literals(protected + token, mapping)

    def test_unchanged_game_variables_are_not_protected_twice(self):
        source = r"\V[12] + 7 = %1"
        protected, mapping = protect_literals(source, source="en")
        self.assertEqual(protected.count(r"\V[12]"), 1)
        self.assertEqual(restore_literals(protected, mapping), source)
        self.assertEqual(list(mapping.values()), ["7"])

    def test_overlapping_terms_prefer_longest(self):
        protected, mapping = protect_literals(
            "新しい顧問が来た。",
            glossary={"顧問": "asesor", "新しい顧問": "nuevo asesor"}
        )
        self.assertEqual(len(mapping), 1)
        self.assertIn("nuevo asesor", restore_literals(protected, mapping))

    def test_unsafe_glossary_is_rejected(self):
        with self.assertRaises(ValueError):
            protect_literals("私", glossary={"私": r"\V[12]"})
        with self.assertRaises(ValueError):
            protect_literals("私", glossary={"私": ""})

    def test_marker_collision_is_avoided(self):
        source = r"\V[987650] es la variable; nuevo 2026"
        protected, mapping = protect_literals(source, source="en")
        self.assertIn(r"\V[987650]", protected)
        self.assertNotIn(r"\V[987650]", mapping)
        self.assertEqual(restore_literals(protected, mapping), source)


class TestModelIsolation(unittest.TestCase):
    def test_no_sentinel_reaches_the_model(self):
        calls = []
        source = "午前中、夕方頃。"
        def model(fragment):
            calls.append(fragment)
            self.assertNotIn(r"\V[987", fragment)
            return fragment.replace("、", ", ")
        result = translate_checked(
            source, model,
            glossary={"午前中": "por la mañana", "夕方頃": "alrededor del atardecer"},
            required_terms=("mañana", "atardecer")
        )
        self.assertIn("mañana", result)
        self.assertIn("atardecer", result)
        self.assertTrue(all(r"\V[987" not in x for x in calls))

    def test_native_code_argument_punctuation_remains_untouched(self):
        source = r"\N[花子！]！"
        protected, mapping = protect_literals(
            source, glossary={"花子": "Hanako"}
        )
        restored = restore_literals(protected, mapping)
        self.assertIn(r"\N[花子！]", restored)
        self.assertTrue(restored.endswith("!"))
        validate_translation(source, restored)

    def test_existing_high_number_variable_is_not_an_internal_leak(self):
        validate_translation(r"\V[987650] は学校。", r"\V[987650] es la escuela.")

    def test_model_cannot_drop_unprotected_fragment_when_terms_survive(self):
        with self.assertRaises(TranslationRejected):
            translate_checked(
                "学校で話す。",
                lambda _: "",
                glossary={"学校": "escuela"}
            )

    def test_model_cannot_return_japanese_prose(self):
        source = "学校に行きます。"
        with self.assertRaises(TranslationRejected):
            translate_checked(source, lambda frag: frag)

    def test_model_cannot_insert_newline(self):
        with self.assertRaises(TranslationRejected):
            translate_checked("学校。", lambda frag: "escuela\nerrónea")

    def test_translator_cannot_drop_original_native_codes(self):
        source = r"\V[12] が好きです。"
        result = translate_checked(source, lambda f: " me gusta.")
        self.assertIn(r"\V[12]", result)
        validate_translation(source, result)

    def test_error_on_modified_original_native_code(self):
        with self.assertRaises(TranslationRejected):
            validate_translation(r"\V[12] 色", r"\V[13] color")

    def test_required_semantic_terms_must_be_present(self):
        with self.assertRaises(TranslationRejected):
            validate_translation("今日はいい天気。", "Hace sol.",
                                 required_terms=("escuela",))

    def test_internal_marker_leak_is_rejected(self):
        with self.assertRaises(TranslationRejected):
            validate_translation("学校。", "escuela ZXQTX760TERM001QXZ")
        with self.assertRaises(TranslationRejected):
            validate_translation("学校。", r"escuela \V[987650]")

    def test_unicode_replacement_is_rejected(self):
        with self.assertRaises(TranslationRejected):
            validate_translation("学校。", "escuela \ufffd")

    def test_original_line_margins_and_endings_are_restored(self):
        original = "\t学校。\r\n  明日。"
        target = "escuela\r\nmañana"
        result = restore_layout(original, target)
        self.assertEqual(result, "\tescuela\r\n  mañana")
        validate_translation(original, result)

    def test_line_break_changed_is_rejected(self):
        with self.assertRaises(TranslationRejected):
            restore_layout("学校。\r\n明日。", "escuela\nmañana")
        with self.assertRaises(TranslationRejected):
            validate_translation("学校。\r\n明日。", "escuela\nmañana")

    def test_two_consecutive_approved_spanish_literals_have_word_spacing(self):
        protected, mapping = protect_literals(
            "花子おはよう！今日は早かったね。",
            glossary={
                "花子": "Hanako",
                "おはよう": "¡Buenos días!",
                "今日は早かったね": "Hoy llegaste temprano",
            },
        )
        result = restore_literals(protected, mapping)
        self.assertIn("Hanako ¡Buenos días!", result)
        self.assertIn("¡Buenos días! Hoy", result)
        self.assertNotIn(r"\V[987", result)

    def test_zero_width_and_empty_translation_rejected(self):
        with self.assertRaises(TranslationRejected):
            validate_translation("学校", "")
        with self.assertRaises(TranslationRejected):
            validate_translation("学校", "   ")



class TestInlineGlossaryContext(unittest.TestCase):
    def test_inline_glossary_preserves_full_japanese_clause_for_model(self):
        source = "花子は私の幼なじみです。"
        seen = []
        def model(text):
            seen.append(text)
            return "Hanako es mi amiga de la infancia."
        result = translate_checked(
            source, model, glossary={"花子": "Hanako"},
            inline_glossary=True, required_terms=("Hanako",),
        )
        self.assertEqual(seen, ["Hanakoは私の幼なじみです。"])
        self.assertEqual(result, "Hanako es mi amiga de la infancia.")

    def test_inline_glossary_does_not_modify_original_native_rpg_code(self):
        source = r"\N[花子]と花子は学校。"
        altered, mapping = protect_literals(
            source, glossary={"花子": "Hanako"},
            inline_glossary=True, protect_numbers=False,
        )
        self.assertEqual(altered, r"\N[花子]とHanakoは学校。")
        self.assertEqual(mapping, {})

    def test_inline_glossary_rejects_untranslated_japanese_values(self):
        with self.assertRaises(ValueError):
            protect_literals(
                "花子は学校。", glossary={"花子": "はなこ"},
                inline_glossary=True,
            )

    def test_whole_context_mode_sends_two_sentences_as_one(self):
        source = "学校へ行く。明日も行く。"
        calls = []
        def model(text):
            calls.append(text)
            return "Voy a la escuela. Mañana también iré."
        translated = translate_checked(
            source, model, split_model_sentences=False,
        )
        self.assertEqual(calls, [source])
        self.assertEqual(translated, "Voy a la escuela. Mañana también iré.")

    def test_old_marker_mode_keeps_legacy_behavior_by_default(self):
        altered, mapping = protect_literals(
            "花子は学校。", glossary={"花子": "Hanako"},
        )
        self.assertNotIn("Hanako", altered)
        self.assertEqual(len(mapping), 1)
