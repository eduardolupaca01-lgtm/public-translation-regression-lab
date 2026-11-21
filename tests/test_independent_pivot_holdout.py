"""Offline contract and adversarial tests for the independent 20-case gate."""
import unittest

from tools.independent_pivot_holdout import (
    DECLARED_LICENSE,
    EN_ES_MODEL_ID,
    INDEPENDENT_CASES,
    JA_EN_MODEL_ID,
    SEMANTIC_POLICY_VERSION,
    _semantic_errors,
)
from tools.neural_acceptance import CASES as DEVELOPMENT_CASES
from tools.unseen_holdout import HOLDOUT_CASES as FIRST_HOLDOUT
from translation_lab.pipeline import validate_translation


REFERENCE_TRANSLATIONS = {
    "meeting_time_contrast":
        "La reunión comenzará a las cuatro de la tarde, no a las dos.",
    "key_ownership":
        "Tanaka tiene la llave, pero Sato no la tiene.",
    "bridge_left_turn":
        "Después de cruzar el puente, gire a la izquierda en el primer semáforo.",
    "envelope_color_counts":
        "Hay dos sobres rojos y cinco sobres azules.",
    "file_do_not_delete":
        "No borre este archivo. Guárdelo en otra carpeta.",
    "email_before_meeting":
        "Envíe primero el correo y después venga a la sala de reuniones.",
    "ordered_books_arrived":
        "No llegaron los tres libros que pedí, sino solo dos.",
    "colder_today_weaker_wind":
        "Hoy hace más frío que ayer, pero el viento es débil.",
    "children_permission_and_prohibition":
        "Los niños pueden entrar en esta habitación, pero no deben correr.",
    "blue_umbrella_owner":
        "El paraguas azul no es mío, sino de mi hermana menor.",
    "shop_yesterday_today":
        "Ayer la tienda estaba abierta, pero hoy está cerrada.",
    "woman_by_window":
        "La mujer que está sentada junto a la ventana es mi nueva profesora.",
    "reservation_tuesday_to_thursday":
        "La reserva se cambió del martes al jueves.",
    "cooked_and_washed_dishes":
        "Él no solo cocinó, sino que también lavó los platos.",
    "check_document_before_signing":
        "Antes de firmar este documento, debe revisar su contenido.",
    "miss_train_take_taxi":
        "Si no alcanzamos el tren a tiempo, iremos en taxi.",
    "luggage_reception_or_room":
        "¿Dejó el equipaje en recepción o lo llevó a la habitación?",
    "called_but_no_reply":
        "Lo llamé, pero todavía no me ha respondido.",
    "price_normal_vs_today":
        "Este producto cuesta normalmente 1000 yenes, pero hoy puede comprarse por 800 yenes.",
    "name_code_two_line_schedule":
        "Mañana, \\N[3] regresará a las 6 de la tarde.\r\n"
        "La recepción abrirá a las 9 de la mañana.",
}


ADVERSARIAL_TRANSLATIONS = {
    "meeting_time_contrast":
        "La reunión comenzará a las dos de la tarde, no a las cuatro.",
    "key_ownership":
        "Tanaka no tiene la llave, pero Sato sí la tiene.",
    "bridge_left_turn":
        "Después de cruzar el puente, gire a la derecha en el primer semáforo.",
    "envelope_color_counts":
        "Hay cinco sobres rojos y dos sobres azules.",
    "file_do_not_delete":
        "Elimine este archivo y guárdelo en otra carpeta.",
    "email_before_meeting":
        "Venga a la sala de reuniones antes de enviar el correo.",
    "ordered_books_arrived":
        "Llegaron tres libros, no dos.",
    "colder_today_weaker_wind":
        "Hoy hace más calor que ayer, pero el viento es débil.",
    "children_permission_and_prohibition":
        "Los niños no pueden entrar en esta habitación, pero sí pueden correr.",
    "blue_umbrella_owner":
        "El paraguas azul es mío, no de mi hermana menor.",
    "shop_yesterday_today":
        "Ayer la tienda estaba cerrada, pero hoy está abierta.",
    "woman_by_window":
        "La mujer junto a la ventana es mi nueva profesora.",
    "reservation_tuesday_to_thursday":
        "La reserva se cambió del jueves al martes.",
    "cooked_and_washed_dishes":
        "Él cocinó, pero no lavó los platos.",
    "check_document_before_signing":
        "Después de firmar este documento, debe revisar su contenido.",
    "miss_train_take_taxi":
        "Si alcanzamos el tren, iremos en taxi.",
    "luggage_reception_or_room":
        "¿Dejó el equipaje en recepción o lo dejó allí?",
    "called_but_no_reply":
        "Lo llamé y ya me ha respondido.",
    "price_normal_vs_today":
        "Este producto cuesta normalmente 800 yenes, pero hoy cuesta 1000 yenes.",
    "name_code_two_line_schedule":
        "Mañana, \\N[3] regresará a las 9 de la mañana.\r\n"
        "La recepción abrirá a las 6 de la tarde.",
}


VALID_VARIANT_TRANSLATIONS = {
    "meeting_time_contrast":
        "La reunión no comienza a las dos de la tarde, sino a las cuatro.",
    "email_before_meeting":
        "Por favor, envíe un correo antes de venir a la sala de conferencias.",
    "ordered_books_arrived":
        "Los libros que pedí no fueron tres, sino dos. Llegaron.",
    "colder_today_weaker_wind":
        "Hoy hace más frío que ayer, pero el viento es suave.",
    "cooked_and_washed_dishes":
        "Él no solo preparó la comida, sino que también lavó los platos.",
    "check_document_before_signing":
        "Antes de firmar este documento, hay que verificar su contenido.",
    "miss_train_take_taxi":
        "Si no logro coger el tren, iré en taxi.",
}

INVALID_VARIANT_TRANSLATIONS = {
    "blue_umbrella_owner":
        "El paraguas azul no es mío, es de mi hermana.",
    "email_before_meeting":
        "Por favor, envíenos un correo antes de venir a la sala de conferencias.",
    "ordered_books_arrived":
        "Los libros que pedí no fueron tres, sino dos. No llegaron.",
    "check_document_before_signing":
        "Antes de firmar este documento, debo verificar su contenido.",
    "miss_train_take_taxi":
        "Si no logro coger el tren, no iré en taxi.",
}


class TestIndependentHoldoutContracts(unittest.TestCase):
    def test_twenty_unique_cases_are_disjoint_from_prior_corpora(self):
        self.assertEqual(len(INDEPENDENT_CASES), 20)
        self.assertEqual(len({case.id for case in INDEPENDENT_CASES}), 20)
        self.assertEqual(len({case.japanese for case in INDEPENDENT_CASES}), 20)
        new_sources = {case.japanese for case in INDEPENDENT_CASES}
        prior_sources = {case.japanese for case in FIRST_HOLDOUT}
        development_sources = {case.japanese for case in DEVELOPMENT_CASES}
        self.assertFalse(new_sources & prior_sources)
        self.assertFalse(new_sources & development_sources)

    def test_semantic_policy_is_versioned_and_case_sources_remain_fixed(self):
        self.assertEqual(
            SEMANTIC_POLICY_VERSION,
            "independent_holdout_v2_semantic_calibration",
        )
        self.assertEqual(len(INDEPENDENT_CASES), 20)
        self.assertEqual(len({case.japanese for case in INDEPENDENT_CASES}), 20)

    def test_faithful_spanish_variants_are_not_false_rejected(self):
        by_id = {case.id: case for case in INDEPENDENT_CASES}
        for case_id, translated in VALID_VARIANT_TRANSLATIONS.items():
            with self.subTest(case=case_id):
                self.assertEqual(_semantic_errors(by_id[case_id], translated), [])

    def test_omissions_invented_recipients_and_inverted_events_are_rejected(self):
        by_id = {case.id: case for case in INDEPENDENT_CASES}
        for case_id, translated in INVALID_VARIANT_TRANSLATIONS.items():
            with self.subTest(case=case_id):
                self.assertTrue(_semantic_errors(by_id[case_id], translated))

    def test_public_model_provenance_is_fixed(self):
        self.assertEqual(JA_EN_MODEL_ID, "Helsinki-NLP/opus-mt-ja-en")
        self.assertEqual(EN_ES_MODEL_ID, "Helsinki-NLP/opus-mt-en-es")
        self.assertEqual(DECLARED_LICENSE, "apache-2.0")

    def test_all_twenty_reference_translations_pass_semantic_and_structure_gates(self):
        self.assertEqual(set(REFERENCE_TRANSLATIONS), {
            case.id for case in INDEPENDENT_CASES
        })
        by_id = {case.id: case for case in INDEPENDENT_CASES}
        for case_id, translated in REFERENCE_TRANSLATIONS.items():
            with self.subTest(case=case_id):
                self.assertEqual(_semantic_errors(by_id[case_id], translated), [])
                validate_translation(
                    by_id[case_id].japanese, translated, source="ja"
                )

    def test_all_twenty_adversarial_translations_are_rejected(self):
        self.assertEqual(set(ADVERSARIAL_TRANSLATIONS), {
            case.id for case in INDEPENDENT_CASES
        })
        by_id = {case.id: case for case in INDEPENDENT_CASES}
        for case_id, translated in ADVERSARIAL_TRANSLATIONS.items():
            with self.subTest(case=case_id):
                self.assertTrue(
                    _semantic_errors(by_id[case_id], translated),
                    "The semantic gate accepted an intentionally inverted translation: "
                    + case_id,
                )

    def test_code_and_crlf_schedule_are_preserved_in_reference(self):
        case = next(
            item for item in INDEPENDENT_CASES
            if item.id == "name_code_two_line_schedule"
        )
        translated = REFERENCE_TRANSLATIONS[case.id]
        self.assertIn(r"\N[3]", translated)
        self.assertIn("\r\n", translated)
        validate_translation(case.japanese, translated, source="ja")


if __name__ == "__main__":
    unittest.main()
