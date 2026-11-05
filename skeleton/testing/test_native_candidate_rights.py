"""Use existing FLGB rights scopes to fence native training data."""
from __future__ import annotations
import unittest
from skeleton.ai.runtime.operational_ai.native_candidate.catalog import iter_examples
from skeleton.ai.runtime.operational_ai.native_candidate.rights import verify_rights
from skeleton.ai.runtime.operational_ai.native_candidate.records import TrainingExample
from skeleton.ai.runtime.operational_ai.native_candidate.strict import encode
from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected


class TestTrainingRights(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items=tuple(iter_examples())

    def test_original_scoped_data(self):
        proof=verify_rights(self.items)
        self.assertEqual(proof.records,576)
        self.assertEqual(proof.allowed_scope,"offline_native_candidate_training")
        self.assertEqual(proof.license_id,"skeleton_original")

    def test_restricted_rights_refused(self):
        row=self.items[0].record()
        row["rights_status"]="restricted"
        with self.assertRaises(CandidateRejected):
            TrainingExample.parse(encode(row))

    def test_unknown_training_scope_refused(self):
        row=self.items[0].record()
        row["training_scope"]="other_scope"
        with self.assertRaises(CandidateRejected):
            TrainingExample.parse(encode(row))

    def test_repeated_rights_source_refused(self):
        with self.assertRaises(CandidateRejected):
            verify_rights((self.items[0],self.items[0]))

    def test_missing_rights_data_refused(self):
        with self.assertRaises(CandidateRejected):
            verify_rights(())


if __name__ == "__main__":
    unittest.main()
