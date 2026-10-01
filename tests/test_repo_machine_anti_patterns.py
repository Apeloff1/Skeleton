from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "repo_machine_anti_patterns",
    ROOT / "skeleton" / "repo_machine" / "anti_patterns.py",
)
assert SPEC and SPEC.loader
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)

class RepositoryAntiPatternTests(unittest.TestCase):
    def _exception(self, **changes):
        values = dict(
            exception_id="APX-0001",
            pattern_id="AP-HEURISTIC-FALLBACK",
            owner_id="repo-machine",
            rationale="temporary parser migration",
            created_at_utc="2026-10-01T00:00:00Z",
            expires_at_utc="2026-10-05T00:00:00Z",
            evidence_refs=("issue://123",),
        )
        values.update(changes)
        return M.AntiPatternException(**values)

    def test_owned_bounded_exception_is_valid(self):
        M.validate_exception(
            self._exception(),
            policy={"AP-HEURISTIC-FALLBACK": (True, 7)},
            as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
        )

    def test_non_waivable_pattern_rejects_exception(self):
        with self.assertRaises(M.AntiPatternPolicyError):
            M.validate_exception(
                self._exception(),
                policy={"AP-HEURISTIC-FALLBACK": (False, None)},
                as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
            )

    def test_future_dated_exception_is_not_yet_active(self):
        with self.assertRaisesRegex(M.AntiPatternPolicyError, "not yet active"):
            M.validate_exception(
                self._exception(),
                policy={"AP-HEURISTIC-FALLBACK": (True, 7)},
                as_of=datetime(2026, 9, 30, tzinfo=timezone.utc),
            )

    def test_naive_evaluation_time_is_rejected(self):
        with self.assertRaisesRegex(M.AntiPatternPolicyError, "timezone-aware"):
            M.validate_exception(
                self._exception(),
                policy={"AP-HEURISTIC-FALLBACK": (True, 7)},
                as_of=datetime(2026, 10, 2),
            )

    def test_expired_exception_fails_closed(self):
        with self.assertRaisesRegex(M.AntiPatternPolicyError, "expired"):
            M.validate_exception(
                self._exception(),
                policy={"AP-HEURISTIC-FALLBACK": (True, 7)},
                as_of=datetime(2026, 10, 6, tzinfo=timezone.utc),
            )

    def test_ttl_overflow_fails_closed(self):
        with self.assertRaisesRegex(M.AntiPatternPolicyError, "max TTL"):
            M.validate_exception(
                self._exception(expires_at_utc="2026-10-20T00:00:00Z"),
                policy={"AP-HEURISTIC-FALLBACK": (True, 7)},
                as_of=datetime(2026, 10, 2, tzinfo=timezone.utc),
            )


if __name__ == "__main__":
    unittest.main()
