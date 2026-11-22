"""Risk detectors must find actual Stage4 errors without rewriting the outputs."""
import unittest
from tools.stage5_cross_run_semantic_audit import known_risks


class TestStage5KnownSemanticRisks(unittest.TestCase):
    def test_singular_intent_plural_joint_error(self):
        hard, review = known_risks("calibration", "sister_homework",
            "Cuando termine, pienso ir al parque juntos.")
        self.assertEqual([i["code"] for i in hard], ["SINGULAR_INTENT_PLURAL_JUNTOS"])
        self.assertEqual(review, [])

    def test_feminine_sword_masculine_direct_object(self):
        hard, _ = known_risks("rpg", "speaker_item_owner",
            r"\N[3]「Esta espada no es mía. Devuélvelo a \N[5].」")
        self.assertEqual([i["code"] for i in hard], ["SWORD_OBJECT_GENDER_DISAGREEMENT"])

    def test_seer_seen_subject_object_swap(self):
        hard, _ = known_risks("rpg", "reported_speech_no_arrival",
            "Él dijo que vendría. Sin embargo, aún no ha visto a nadie.")
        self.assertEqual([i["code"] for i in hard], ["SEER_SEEN_ROLE_INVERSION"])

    def test_plausible_alternatives_are_not_wrongly_flagged(self):
        samples = (
            ("calibration", "sister_homework", "Cuando termine, iremos juntas al parque."),
            ("rpg", "speaker_item_owner", "Esta espada no es mía. Devuélvela a su dueña."),
            ("rpg", "reported_speech_no_arrival", "Dijo que vendría, pero nadie lo ha visto."),
        )
        for group, case, text in samples:
            self.assertEqual(known_risks(group, case, text)[0], [])

    def test_ambiguity_is_not_pretended_to_be_resolved(self):
        _, review = known_risks("calibration", "red_and_blue_apples",
                                "No hay ninguna manzana azul.")
        self.assertEqual([r["code"] for r in review], ["AOI_APPLE_COLOR_CONTEXT"])


if __name__ == "__main__":
    unittest.main()
