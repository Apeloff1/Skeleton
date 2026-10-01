"""Card for the P2 spine masterplan. Not a sign-off."""

from __future__ import annotations

from typing import Any


class SpineMasterplan:
    """Read the plan percentages. hit stays false."""

    def card(self) -> dict[str, Any]:
        return {
            "kind": "spine_masterplan",
            "hit": False,
            "law": "plan-is-not-signoff",
            "citation": "VOL-134",
            "doc": "docs/plan/P2_SPINE_MASTERPLAN.md",
            "read_project_percent": 95,
            "apply_percent": 55,
            "motor_bootstrap_percent": 15,
            "provider_surface_percent": 0,
            "pr_automation_percent": 0,
            "ci_green_percent": 0,
            "merge_percent": 0,
            "bind_card_percent": 75,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
