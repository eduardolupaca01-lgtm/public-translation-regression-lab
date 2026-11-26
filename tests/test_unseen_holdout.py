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
                "Cuando haya terminado, iremos al parque."
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

    def test_rainy_meeting_rejects_plural_waiting_agent(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "rainy_meeting")
        errors = _semantic_errors(
            case,
            "Nos vemos mañana por la tarde frente a la estación. "
            "Cuando llueva, estaremos esperando en la entrada de la biblioteca.",
        )
        self.assertIn("WAITING_AGENT_CHANGED", errors)
        self.assertIn("WAITING_AGENT_OR_FUTURE_TENSE_CHANGED", errors)

    def test_rain_condition_accepts_valid_present_tense_paraphrase(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "rainy_meeting")
        self.assertEqual(
            _semantic_errors(
                case,
                "Te veré mañana por la tarde frente a la estación. "
                "Cuando llueve, te esperaré en la entrada de la biblioteca.",
            ),
            [],
        )

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


    def test_rejects_teacher_statement_that_children_are_quiet(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "teacher_and_children")
        errors = _semantic_errors(
            case,
            'El maestro dijo: "Siguen callados", pero los niños se reían.',
        )
        self.assertIn("TEACHER_SILENCE_QUOTE_IS_NOT_A_REQUEST", errors)

    def test_speaker_control_code_accepts_pm_clock_notation(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "speaker_control_code")
        for suffix in ("p. m.", "p.m.", "pm", "P. M."):
            with self.subTest(suffix=suffix):
                translated = rf"\N[7] llegará mañana a las 3:00 {suffix}"
                self.assertEqual(_semantic_errors(case, translated), [])

    def test_speaker_control_code_rejects_am_clock_notation(self) -> None:
        case = next(x for x in HOLDOUT_CASES if x.id == "speaker_control_code")
        translated = r"\N[7] llegará mañana a las 3:00 a. m."
        errors = _semantic_errors(case, translated)
        self.assertTrue(any("MISSING_CONCEPTS" in error for error in errors), errors)
        self.assertTrue(any("AFTERNOON_PERIOD_LOST" in error for error in errors), errors)

    def test_shop_hours_accepts_spelled_ten_without_changing_line_breaks(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "shop_hours_line_break")
        translated = (
            "La tienda está cerrada hoy.\r\n"
            "Mañana abrirá a las diez de la mañana."
        )
        self.assertEqual(_semantic_errors(case, translated), [])
        validate_translation(case.japanese, translated, source="ja")

    def test_rejects_arrival_time_detached_from_the_arrival_action(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "speaker_control_code")
        errors = _semantic_errors(
            case,
            r"\N[7]Es mañana por la tarde. 3De vez en cuando viene.",
        )
        self.assertIn("ARRIVAL_TIME_CONTEXT_LOST", errors)
        self.assertIn("ARRIVAL_ACTION_LOST", errors)


    def test_rejects_wrong_sister_condition_and_self_companion(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "sister_homework")
        errors = _semantic_errors(
            case,
            "Mi hermana aún no ha terminado sus tareas. "
            "Cuando terminemos, iré al parque conmigo.",
        )
        self.assertIn("AFTER_COMPLETION_CONDITION_LOST", errors)
        self.assertIn("TOGETHER_OR_COMPANION_RELATION_LOST", errors)

    def test_accepts_train_late_paraphrase_without_requiring_retrasado(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "delayed_train")
        self.assertEqual(
            _semantic_errors(
                case,
                "El tren llega tarde, así que la reunión comenzará en media hora.",
            ),
            [],
        )

    def test_rejects_singular_unaddressed_teacher_request(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "teacher_and_children")
        errors = _semantic_errors(
            case,
            "La maestra dijo que se callara, pero los niños siguieron riéndose.",
        )
        self.assertIn("TEACHER_REQUEST_FOR_SILENCE_LOST", errors)

    def test_structure_rejects_missing_control_code(self):
        case = next(x for x in HOLDOUT_CASES if x.id == "speaker_control_code")
        with self.assertRaises(TranslationRejected):
            validate_translation(
                case.japanese, "Vendrá mañana a las 3 de la tarde.", source="ja"
            )


if __name__ == "__main__":
    unittest.main()
