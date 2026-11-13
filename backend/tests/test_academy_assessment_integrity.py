import hashlib
import json
import unittest

from routes.academy_v3 import _assessment_receipt_valid, _public_assessment


class AcademyAssessmentIntegrityTests(unittest.TestCase):
    def test_public_assessment_never_exposes_answer_material(self):
        public = _public_assessment({
            "id": "exam-1",
            "questions": [{
                "id": "q1",
                "text": "Choose",
                "options": ["A", "B"],
                "correct": "A",
                "correct_answer": "A",
                "explanation": "Because",
            }],
        })
        self.assertEqual(public["question_count"], 1)
        self.assertEqual(public["questions"][0], {"id": "q1", "text": "Choose", "options": ["A", "B"]})

    def test_receipt_verification_rejects_tampered_score(self):
        material = {
            "attempt_id": "academy-attempt-1",
            "assessment_id": "exam-1",
            "answer_digest": "a" * 64,
            "score": 100.0,
            "passed": True,
            "completed_at": "2026-11-09T00:00:00+00:00",
        }
        receipt = hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertTrue(_assessment_receipt_valid({**material, "receipt_sha256": receipt}))
        self.assertFalse(_assessment_receipt_valid({**material, "score": 50.0, "receipt_sha256": receipt}))


if __name__ == "__main__":
    unittest.main()
