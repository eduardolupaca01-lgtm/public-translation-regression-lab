"""Evidence is not a professional human approval and a badge is not truth."""
from __future__ import annotations
import hashlib
import unittest
from tools.stage9_bilingual_review import EXPECTED, build_packet, screen_case, review_flags
from tools.stage10_release_gate import assess, FROZEN_RUNS, REVIEW_DIMENSIONS

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

    def test_historical_rubric_rejects_are_flagged_for_review(self):
        self.assertIn("HISTORICAL_RUBRIC_REJECTION",
                      review_flags(8, "taro_hana_mika_witness", "", "rejected"))
        self.assertIn("VOLITIVE_AS_IMPERATIVE_REVIEW",
                      review_flags(8, "two_speakers_aria_sara", "", "rejected"))
        self.assertNotIn("HISTORICAL_RUBRIC_REJECTION",
                         review_flags(6, "sibling_map_chain", "Fiel", "rubric_accepted"))

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

    def test_final_gate_detects_packet_target_and_sha_tampering(self):
        reports, proofs, hashes = self._mock_receipts()
        packet = build_packet(reports, proofs, hashes)
        packet["source_run_ids_by_stage"] = {
            "6": "44931094612", "7": "44942504944", "8": "44961618206"
        }
        packet["items"][0]["candidate_es_419"] = "Texto manipulado"
        packet["items"][1]["source_sha256"] = "0" * 64
        packet["items"][2]["historical_rubric"] = "rubric_rejected"
        gate = assess(reports, proofs, packet, hashes)
        self.assertEqual(gate["status"], "HOLD")
        self.assertTrue(any("STAGE9_ORIGINAL_CASE_EVIDENCE_CHANGED" in b
                            for b in gate["blockers"]))

    def test_final_gate_detects_duplicate_case_and_missing_run_provenance(self):
        reports, proofs, hashes = self._mock_receipts()
        packet = build_packet(reports, proofs, hashes)
        packet["items"][0] = dict(packet["items"][1])
        gate = assess(reports, proofs, packet, hashes)
        self.assertIn("STAGE9_PACKET_DUPLICATE_CASE_ID", gate["blockers"])
        self.assertIn("STAGE9_FROZEN_RUN_PROVENANCE_MISMATCH", gate["blockers"])

    def test_forged_boolean_signoff_cannot_bypass_human_and_github_verification(self):
        reports, proofs, hashes = self._mock_receipts()
        packet = build_packet(reports, proofs, hashes)
        packet["source_run_ids_by_stage"] = FROZEN_RUNS
        packet["human_review_completed"] = True
        packet["human_review_approved"] = True
        packet["reviewer_attestation"] = "Fake reviewer text"
        for row in packet["items"]:
            row["human_decision"] = "approved"
        gate = assess(reports, proofs, packet, hashes)
        self.assertEqual(gate["status"], "HOLD")
        self.assertIn("STAGE9_REVIEWER_ATTESTATION_MISSING", gate["blockers"])
        self.assertIn("STAGE9_REVIEW_DIMENSIONS_NOT_ALL_APPROVED", gate["blockers"])
        self.assertIn("STAGE10_CURRENT_HEAD_INDEPENDENT_GITHUB_APPROVAL_NOT_VERIFIED",
                      gate["blockers"])

    def test_independent_approval_requires_current_head_not_older_approval(self):
        reports, proofs, hashes = self._mock_receipts()
        packet = build_packet(reports, proofs, hashes)
        packet["source_run_ids_by_stage"] = FROZEN_RUNS
        packet["human_review_completed"] = True
        packet["human_review_approved"] = True
        packet["reviewer_attestation"] = {
            "reviewer_github_login": "independent-translator",
            "evidence_report_sha256_by_stage": {str(n): hashes[n] for n in EXPECTED},
            "source_run_ids_by_stage": FROZEN_RUNS,
            "independent_bilingual_review_confirmed": True,
            "reviewed_at_utc": "2026-11-21T23:00:00Z",
        }
        for row in packet["items"]:
            row["reviewer"] = "independent-translator"
            for dimension in REVIEW_DIMENSIONS:
                row[dimension] = "approved"
            row["human_decision"] = "approved"
            row["notes"] = "Revisión manual registrada."
        old_sha = "a" * 40
        latest_sha = "b" * 40
        approval = [{
            "user_login": "independent-translator", "commit_id": old_sha,
            "state": "APPROVED", "submitted_at": "2026-11-21T23:00:00Z",
        }]
        gate = assess(reports, proofs, packet, hashes, approval, latest_sha)
        self.assertIn("STAGE10_CURRENT_HEAD_INDEPENDENT_GITHUB_APPROVAL_NOT_VERIFIED",
                      gate["blockers"])

    def test_valid_structural_review_never_auto_merges(self):
        reports, proofs, hashes = self._mock_receipts()
        packet = build_packet(reports, proofs, hashes)
        packet["source_run_ids_by_stage"] = FROZEN_RUNS
        packet["human_review_completed"] = True
        packet["human_review_approved"] = True
        packet["reviewer_attestation"] = {
            "reviewer_github_login": "independent-translator",
            "evidence_report_sha256_by_stage": {str(n): hashes[n] for n in EXPECTED},
            "source_run_ids_by_stage": FROZEN_RUNS,
            "independent_bilingual_review_confirmed": True,
            "reviewed_at_utc": "2026-11-21T23:00:00Z",
        }
        for row in packet["items"]:
            row["reviewer"] = "independent-translator"
            row["human_decision"] = "approved"
            for dimension in REVIEW_DIMENSIONS:
                row[dimension] = "approved"
            row["notes"] = "Fidelidad y códigos revisados."
        sha = "b" * 40
        approval = [{
            "user_login": "independent-translator", "state": "APPROVED",
            "commit_id": sha, "submitted_at": "2026-11-21T23:00:00Z",
        }]
        gate = assess(reports, proofs, packet, hashes, approval, sha)
        self.assertTrue(gate["status"] in {"HOLD", "READY_FOR_MANUAL_PR_REVIEW"})
        self.assertFalse(gate["automatic_merge_or_publication_permitted"])
        self.assertFalse(gate["merge_performed"])
        self.assertTrue(gate["manual_pr_and_main_review_required"])

    @staticmethod
    def _mock_receipts():
        reports, proofs, hashes = {}, {}, {}
        for stage, count in EXPECTED.items():
            reports[stage] = {
                "required": count, "rubric_accepted": count,
                "cases": [{
                    "case": f"mock_{i}", "source": f"原文{i}",
                    "translated": "Texto de prueba", "status": "rubric_accepted"
                } for i in range(count)],
            }
            proofs[stage] = {"persistence_status": "PASS"}
            hashes[stage] = hashlib.sha256(str(stage).encode()).hexdigest()
        return reports, proofs, hashes

if __name__ == "__main__":
    unittest.main()
