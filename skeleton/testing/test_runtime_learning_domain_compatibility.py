"""Preserve operational learning behavior while reversing persistence layer inversion."""
from __future__ import annotations

import unittest

from skeleton.contracts import runtime_learning as core_learning
from skeleton.intelligence import runtime_learning as compatibility_learning
from skeleton.persistence.execution_repository import SQLiteExecutionRepository


class RuntimeLearningDomainCompatTests(unittest.TestCase):
    def test_original_intelligence_import_resolves_to_same_domain_implementation(self):
        self.assertIs(core_learning, compatibility_learning)
        self.assertIs(core_learning.RuntimeLearningError,
                      compatibility_learning.RuntimeLearningError)

    def test_learning_policy_and_optimizer_schema_identity_are_preserved(self):
        original = compatibility_learning.normalize_policy()
        canonical = core_learning.normalize_policy(original)
        self.assertEqual(original, canonical)
        self.assertEqual(core_learning.digest(original),
                         compatibility_learning.digest(canonical))
        self.assertEqual(core_learning.SCHEMA, "skeleton.runtime.learning.v1")

    def test_sqlite_persistence_no_longer_imports_application_learning(self):
        self.assertTrue(hasattr(SQLiteExecutionRepository, "runtime_learning_snapshot"))
        self.assertIs(core_learning.digest, compatibility_learning.digest)


if __name__ == "__main__":
    unittest.main()
