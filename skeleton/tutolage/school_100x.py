"""skeleton/tutolage/school_100x.py
100x extreme complete Tutolage school policies.
SAM CLOM KREM. No second school. Review alignment.
Fail-closed.
"""
from __future__ import annotations

class SchoolError(Exception):
    pass

class TutolageSchool100x:
    POLICIES = {"SAM", "CLOM", "KREM"}

    def apply(self, policy: str) -> bool:
        if policy not in self.POLICIES:
            raise SchoolError("invalid policy")
        return True
