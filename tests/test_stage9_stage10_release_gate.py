"""Evidence is not a professional human approval and a badge is not truth."""
from __future__ import annotations
import hashlib
import unittest
from tools.stage9_bilingual_review import EXPECTED, build_packet, screen_case
from tools.stage10_release_gate import assess

class TestStage9Stage10(unittest.TestCase):
    def test_packet_always_requires_forty_manual_decisions(self):
        reports, proofs, hashes = {}, {}, {}
        for n, count in EXPECTED.items():
            reports[n] = {
                "required": count, "rubric_accepted": count,
                "cases": [{
                    "case": f"mock_{i}", "source": f"原文{i}",
                    "translated": "Texto de prueba", "status": "rubric_accepted"
                } for i in range(count)],
            }
            proofs[n] = {"persistence_status": "PASS"}
            hashes[n] = hashlib.sha256(str(n).encode()).hexdigest()
        packet = build_packet(reports, proofs, hashes)
        self.assertEqual(packet["total_items"], 40)
        self.assertFalse(packet["human_review_approved"])
        self.assertTrue(all(x["human_decision"] == "pending" for x in packet["items"]))
        gate = assess(reports, proofs, packet, hashes)
        self.assertEqual(gate["status"], "HOLD")
        self.assertFalse(gate["automatic_merge_or_publication_permitted"])
        self.assertIn("STAGE9_INDEPENDENT_HUMAN_REVIEW_PENDING", gate["blockers"])

    def test_medication_inversion_and_name_change_are_detected(self):
        wrong = r"\V[2] es mayor que 1 solo si se usa una medicina. De lo contrario, no se debe usar."
        self.assertIn("MEDICINE_PREMISE_AND_CONSEQUENCE_REVERSED",
                      screen_case(7, "medicine_variable_strict_gt", wrong))
        self.assertIn("HANA_MISSING", screen_case(
            8, "taro_hana_mika_witness",
            "Taro vio a Hanako salir de la estación, pero Mika no la vio."
        ))
        self.assertEqual([], screen_case(
            8, "shop_hours_sunday",
            "La tienda abre a las 10 de la mañana y cierra a las 6 de la tarde. No abre los domingos."
        ))

if __name__ == "__main__":
    unittest.main()
