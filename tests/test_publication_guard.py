import unittest
from tools.publication_guard import inspect_tree


class TestPublicationGuard(unittest.TestCase):
    def test_repository_contains_no_model_files_or_creds(self):
        self.assertEqual(inspect_tree(), [])

    def test_modules_have_no_external_runtime_requirements(self):
        import translation_lab.cache
        import translation_lab.pipeline
        self.assertTrue(callable(translation_lab.pipeline.translate_checked))
