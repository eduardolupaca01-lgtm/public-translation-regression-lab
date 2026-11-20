"""Offline contracts for the independent unseen-dialogue holdout."""
from __future__ import annotations

import unittest

from tools.neural_acceptance import CASES as DEVELOPMENT_CASES
from tools.unseen_holdout import HOLDOUT_CASES, _semantic_errors
from translation_lab.pipeline import validate_translation, TranslationRejected


class TestUnseenHoldoutContracts(unittest.TestCase):
    def test_holdout_is_distinct_from_all_development_sources(self):
        self.assertEqual(len(HOLDOUT_CASES), 10)
        self.assertEqual(len({case.id for case in HOLDOUT_CASES}), 10)
        self.assertEqual(len({case.japanese for case in HOLDOUT_CASES}), 10)
        development_ids = {case.id for case in DEVELOPMENT_CASES}
        development_sources = {case.japanese for case in DEVELOPMENT_CASES}
        self.assertFalse(development_ids.intersection(
            case.id for case in HOLDOUT_CASES
        ))
        self.assertFalse(development_sources.intersection(
            case.japanese for case in HOLDOUT_CASES
        ))
        self.assertTrue(all(case.japanese for case in HOLDOUT_CASES))
        self.assertTrue(any(r"\N[7]" in case.japanese for case in HOLDOUT_CASES))
        self.assertTrue(any("\r\n" in case.japanese for case in HOLDOUT_CASES))

    def test_reviewed_paraphrases_satisfy_each_holdout_rule(self):
        good = {
            "rainy_meeting": (
                "Mañana por la tarde nos reuniremos frente a la estación. "
                "Si llueve, te esperaré en la entrada de la biblioteca."
            ),
            "closed_shop": (
                "Ayer fui a comprar medicinas, pero la tienda ya estaba cerrada."
            ),
            "sister_homework": (
                "Mi hermana menor todavía no ha terminado los deberes. "
                "Cuando termine, iremos juntas al parque."
            ),
            "red_and_blue_apples": (
                "En esta caja hay tres manzanas rojas. No hay ninguna manzana azul."
            ),
            "teacher_and_children": (
                "El profesor pidió a los niños que guardaran silencio, "
                "pero ellos siguieron riéndose."
            ),
            "delayed_train": (
                "Como el tren está retrasado, la reunión comenzará dentro de treinta minutos."
            ),
            "brother_city_roles": (
                "Mi hermano mayor vive en Tokio, pero yo vivo en Osaka."
            ),
            "second_corner": (
                "Siga recto por esta calle y gire a la derecha en la segunda esquina."
            ),
            "speaker_control_code": (
                r"\N[7]Vendrá mañana a las 3 de la tarde."
            ),
            "shop_hours_line_break": (
                "La tienda está cerrada hoy.\r\nMañana abrirá a las 10 de la mañana."
            ),
        }
        by_id = {case.id: case for case in HOLDOUT_CASES}
        self.assertEqual(set(good), set(by_id))
        for case_id, value in good.items():
            with self.subTest(case=case_id):
                self.assertEqual(_semantic_errors(by_id[case_id], value), [])

    def test_rejects_negation_loss_and_blue_apple_inversion(self):
        cases = {case.id: case for case in HOLDOUT_CASES}
        self.assertIn(
            "HOMEWORK_NEGATION_LOST",
            _semantic_errors(
                cases["sister_homework"],
                "Mi hermana terminó los deberes. Cuando termine, iremos juntas al parque.",
            ),
        )
        self.assertIn(
            "BLUE_APPLE_ABSENCE_INVERTED",
            _semantic_errors(
                cases["red_and_blue_apples"],
                "En esta caja hay tres manzanas rojas y también hay manzanas azules.",
            ),
        )

    def test_rejects_reversed_person_city_roles(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "brother_city_roles")
        errors = _semantic_errors(
            case, "Mi hermano vive en Osaka, pero yo vivo en Tokio."
        )
        self.assertIn("BROTHER_TOKYO_ROLE_MISMATCH", errors)
        self.assertIn("SPEAKER_OSAKA_ROLE_MISMATCH", errors)

    def test_rejects_wrong_turn_and_missing_causal_link(self):
        cases = {case.id: case for case in HOLDOUT_CASES}
        self.assertIn(
            "RIGHT_TURN_INVERTED",
            _semantic_errors(
                cases["second_corner"],
                "Siga recto y gire a la izquierda en la segunda esquina.",
            ),
        )
        self.assertIn(
            "TRAIN_DELAY_CAUSAL_LINK_LOST",
            _semantic_errors(
                cases["delayed_train"],
                "El tren está retrasado. La reunión comenzará dentro de treinta minutos.",
            ),
        )

    def test_structural_pipeline_preserves_unseen_control_code_and_time(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "speaker_control_code")
        translated = r"\N[7]Vendrá mañana a las 3 de la tarde."
        validate_translation(case.japanese, translated, source="ja")
        self.assertEqual(_semantic_errors(case, translated), [])

    def test_structural_pipeline_preserves_crlf_and_numeric_time(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "shop_hours_line_break")
        translated = (
            "La tienda está cerrada hoy.\r\n"
            "Mañana abrirá a las 10 de la mañana."
        )
        validate_translation(case.japanese, translated, source="ja")
        self.assertEqual(_semantic_errors(case, translated), [])

    def test_structure_rejects_missing_control_code(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "speaker_control_code")
        with self.assertRaises(TranslationRejected):
            validate_translation(
                case.japanese, "Vendrá mañana a las 3 de la tarde.", source="ja"
            )


if __name__ == "__main__":
    unittest.main()
