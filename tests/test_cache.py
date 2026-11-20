import tempfile
import unittest
import subprocess
import sys
from translation_lab import DurableTranslationCache, TranslationRejected


class TestDurableCache(unittest.TestCase):
    def test_persistence_after_restarting_the_process(self):
        with tempfile.TemporaryDirectory() as folder:
            original = "学校"
            with DurableTranslationCache(folder) as first:
                result = first.translate_or_get("ja", "es", original, lambda _: "escuela")
                self.assertEqual(result, "escuela")
                self.assertEqual(first.count(), 1)
            def must_not_translate(_):
                raise AssertionError("Repeated translation called the model again")
            with DurableTranslationCache(folder) as second:
                cached = second.translate_or_get("ja", "es", original, must_not_translate)
                self.assertEqual(cached, "escuela")
                self.assertEqual(second.count(), 1)

    def test_cross_process_cache_persists_without_retranslation(self):
        with tempfile.TemporaryDirectory() as folder:
            original = "学校に行きます。"
            with DurableTranslationCache(folder) as cache:
                cache.put("ja", "es", original, "Voy a la escuela.")
            program = (
                "from translation_lab.cache import DurableTranslationCache\n"
                "import sys\n"
                "with DurableTranslationCache(sys.argv[1]) as c:\n"
                "    assert c.get('ja','es', '学校に行きます。') == 'Voy a la escuela.'\n"
                "    print('CROSS_PROCESS_CACHE_HIT')\n"
            )
            result = subprocess.run(
                [sys.executable, "-c", program, folder],
                capture_output=True, text=True, check=True,
            )
            self.assertIn("CROSS_PROCESS_CACHE_HIT", result.stdout)

    def test_semantic_gate_prevents_caching_incomplete_translation(self):
        with tempfile.TemporaryDirectory() as folder:
            with DurableTranslationCache(folder) as cache:
                original = "学校のクラブ。"
                with self.assertRaises(TranslationRejected):
                    cache.translate_or_get(
                        "ja", "es", original, lambda _s: "La escuela.",
                        required_terms=("club",),
                    )
                self.assertEqual(cache.count(), 0)
                value = cache.translate_or_get(
                    "ja", "es", original, lambda _s: "El club de la escuela.",
                    required_terms=("club",),
                )
                self.assertEqual(value, "El club de la escuela.")
                self.assertEqual(cache.count(), 1)

    def test_semantic_gate_does_not_reuse_old_incomplete_row(self):
        with tempfile.TemporaryDirectory() as folder:
            with DurableTranslationCache(folder) as cache:
                original = "学校のクラブ。"
                cache.put("ja", "es", original, "La escuela.")
                self.assertIsNone(cache.get("ja", "es", original, required_terms=("club",)))
                result = cache.translate_or_get(
                    "ja", "es", original,
                    lambda _s: "El club de la escuela.",
                    required_terms=("club",),
                )
                self.assertEqual(result, "El club de la escuela.")
                self.assertEqual(cache.count(), 1)

    def test_empty_translation_never_enters_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            with DurableTranslationCache(folder) as cache:
                with self.assertRaises(TranslationRejected):
                    cache.put("ja", "es", "学校", "")
                self.assertEqual(cache.count(), 0)

    def test_failed_neural_attempt_not_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            with DurableTranslationCache(folder) as cache:
                with self.assertRaises(TranslationRejected):
                    cache.translate_or_get("ja", "es", "学校", lambda x: x)
                self.assertEqual(cache.count(), 0)

    def test_model_failure_is_not_cached(self):
        with tempfile.TemporaryDirectory() as folder:
            with DurableTranslationCache(folder) as cache:
                def failed(_):
                    raise RuntimeError("MODEL_UNAVAILABLE")
                with self.assertRaises(RuntimeError):
                    cache.translate_or_get("ja", "es", "学校", failed)
                self.assertEqual(cache.count(), 0)

    def test_cache_key_includes_original_source_and_target(self):
        with tempfile.TemporaryDirectory() as folder:
            with DurableTranslationCache(folder) as cache:
                cache.put("ja", "es", "学校", "escuela")
                self.assertIsNone(cache.get("en", "es", "学校"))
                self.assertIsNone(cache.get("ja", "en", "学校"))
                self.assertIsNone(cache.get("ja", "es", "校門"))

    def test_corrected_translation_replaces_existing_row(self):
        with tempfile.TemporaryDirectory() as folder:
            with DurableTranslationCache(folder) as cache:
                cache.put("ja", "es", "学校", "escuela")
                cache.put("ja", "es", "学校", "colegio")
                self.assertEqual(cache.count(), 1)
                self.assertEqual(cache.get("ja", "es", "学校"), "colegio")

    def test_unicode_and_punctuation_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            original = "「学校はどこですか？」"
            expected = "«¿Dónde está la escuela?»"
            with DurableTranslationCache(folder) as cache:
                cache.put("ja", "es", original, expected)
            with DurableTranslationCache(folder) as cache:
                self.assertEqual(cache.get("ja", "es", original), expected)

    def test_damaged_cached_translation_is_not_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            with DurableTranslationCache(folder) as cache:
                cache.put("ja", "es", "学校", "escuela")
                with cache.connection:
                    cache.connection.execute(
                        "UPDATE translations SET translated=? WHERE original=?",
                        ("残った日本語", "学校")
                    )
                self.assertIsNone(cache.get("ja", "es", "学校"))


    def test_quality_validator_rejects_stale_row_and_replaces_it(self):
        """A quality-rule change must invalidate an old structural-only cache hit."""
        with tempfile.TemporaryDirectory() as folder:
            original = "友人は水泳部です。"
            bad = "Mi amigo es un club de natación."
            good = "Mi amigo pertenece al club de natación."
            with DurableTranslationCache(folder) as cache:
                cache.put("ja", "es", original, bad)

            def validate_role(value):
                if "es un club" in value:
                    raise TranslationRejected("PERSON_NOT_A_CLUB")

            calls = []
            def model(_source):
                calls.append(_source)
                return good

            with DurableTranslationCache(folder) as cache:
                self.assertIsNone(
                    cache.get("ja", "es", original, quality_validator=validate_role)
                )
                self.assertEqual(cache.translate_or_get(
                    "ja", "es", original, model,
                    quality_validator=validate_role
                ), good)
                self.assertEqual(len(calls), 1)
                self.assertEqual(cache.count(), 1)

            with DurableTranslationCache(folder) as cache:
                self.assertEqual(cache.translate_or_get(
                    "ja", "es", original,
                    lambda _: (_ for _ in ()).throw(
                        AssertionError("VALID_CACHE_SHOULD_NOT_RETRANSLATE")
                    ),
                    quality_validator=validate_role
                ), good)

    def test_semantically_rejected_translation_never_enters_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            with DurableTranslationCache(folder) as cache:
                def forbidden(_text):
                    raise TranslationRejected("UNFAITHFUL_CHARACTER_RELATION")
                with self.assertRaisesRegex(
                    TranslationRejected, "UNFAITHFUL_CHARACTER_RELATION"
                ):
                    cache.translate_or_get(
                        "ja", "es", "友人は水泳部です。",
                        lambda _: "Mi amigo es un club de natación.",
                        quality_validator=forbidden
                    )
                self.assertEqual(cache.count(), 0)


    def test_stale_rejected_row_is_removed_if_retranslation_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            with DurableTranslationCache(folder) as cache:
                original = "学校のクラブ。"
                cache.put("ja", "es", original, "La escuela.")

                def reject_old_value(_candidate):
                    raise TranslationRejected("QUALITY_POLICY_CHANGED")

                def unavailable_model(_source):
                    raise RuntimeError("MODEL_UNAVAILABLE")

                with self.assertRaisesRegex(RuntimeError, "MODEL_UNAVAILABLE"):
                    cache.translate_or_get(
                        "ja", "es", original, unavailable_model,
                        quality_validator=reject_old_value,
                    )
                self.assertEqual(cache.count(), 0)
                self.assertIsNone(cache.get("ja", "es", original))
