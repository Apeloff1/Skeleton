"""Merge gate in front of PR #2333.

A complete unread catalog and a clean seal still do not merge. A forged
CI-green flag is recorded and refused.
"""

from __future__ import annotations

from typing import Any


class SpineMergeGateError(RuntimeError):
    """Merge gate rejected its inputs. Not a maturity signal."""


class SpineMergeGate:
    """Refuse the merge. Record why."""

    def consider(self, ci: dict[str, Any], seal: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(ci, dict) or not isinstance(seal, dict):
            raise SpineMergeGateError("ci and seal must be cards")
        reasons: list[str] = []
        if ci.get("ci_green") is True:
            reasons.append("forged-ci")
        if seal.get("provider_surface_green") is True or seal.get("pr_automation_green") is True:
            reasons.append("forged-surface")
        if ci.get("catalog_complete") is not True:
            reasons.append("catalog-incomplete")
        reasons.append("merge-not-landed")
        return {
            "kind": "spine_merge_gate",
            "hit": False,
            "law": "merge-refused",
            "citation": "VOL-134",
            "merged": False,
            "ci_green": False,
            "reasons": reasons,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
