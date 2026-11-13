"""skeleton/tutolage/school_100x_v2.py
Further 100x extreme Tutolage school policies.
SAM CLOM KREM. Do not fork a second school.
Fail-closed.
"""
from __future__ import annotations

class SchoolError(Exception):
    pass

class TutolageSchool100xV2:
    POLICIES = {"SAM", "CLOM", "KREM"}

    def apply(self, policy: str) -> bool:
        if policy not in self.POLICIES:
            raise SchoolError("invalid or second school")
        return True
