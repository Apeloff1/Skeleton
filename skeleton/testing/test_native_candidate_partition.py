"""Original group-disjoint training, validation and holdout source custody."""
from __future__ import annotations
from dataclasses import replace
import unittest
from skeleton.ai.runtime.operational_ai.native_candidate.catalog import iter_examples
from skeleton.ai.runtime.operational_ai.native_candidate.splits import partition
from skeleton.ai.runtime.operational_ai.native_candidate.split_proof import verify
from skeleton.ai.runtime.operational_ai.native_candidate.workload import build
from skeleton.ai.runtime.operational_ai.native_candidate.errors import CandidateRejected


class TestNativePartitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items=tuple(iter_examples())
        cls.splits=partition(cls.items)

    def test_balanced_domain_quota(self):
        self.assertEqual((len(self.splits.train),len(self.splits.validation),
                          len(self.splits.holdout)),(432,72,72))

    def test_gradient_inputs_exclude_holdouts(self):
        workload=build(self.splits)
        self.assertEqual(len(workload.lines),432)
        selected=set(workload.source_ids)
        self.assertFalse(selected & {x.item_id for x in self.splits.validation})
        self.assertFalse(selected & {x.item_id for x in self.splits.holdout})

    def test_source_isolation(self):
        proof=verify(self.splits)
        self.assertTrue(proof["group_disjoint"])
        self.assertTrue(proof["normalized_prompt_disjoint"])

    def test_identical_reconstruction(self):
        self.assertEqual(partition(self.items).digest,self.splits.digest)

    def test_duplicate_group_refused(self):
        changed=list(self.items)
        changed[1]=replace(changed[1],group_id=changed[0].group_id)
        with self.assertRaises(CandidateRejected):
            partition(tuple(changed))

    def test_missing_source_refused(self):
        with self.assertRaises(CandidateRejected):
            partition(self.items[:-1])


if __name__ == "__main__":
    unittest.main()
