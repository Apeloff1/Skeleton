"""Seal over unread provider and PR Automation cards.

A forged green flag is stripped. The seal never returns green. It does not
query a provider and it does not query GitHub.
"""

from __future__ import annotations

from typing import Any


class SpineSurfaceSealError(RuntimeError):
    """Surface seal rejected its inputs. Not a maturity signal."""


class SpineSurfaceSeal:
    """Compose two unread cards and refuse a green claim."""

    def seal(self, provider: dict[str, Any], pr: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(provider, dict) or not isinstance(pr, dict):
            raise SpineSurfaceSealError("provider and pr must be cards")
        stripped: list[str] = []
        if provider.get("green") is True or provider.get("provider_surface_green") is True:
            stripped.append("provider-green-stripped")
        if pr.get("green") is True or pr.get("pr_automation_green") is True:
            stripped.append("pr-green-stripped")
        if provider.get("kind") not in {None, "spine_provider_probe", "spine_surface"}:
            stripped.append("provider-kind")
        if pr.get("kind") not in {None, "spine_pr_probe", "spine_surface"}:
            stripped.append("pr-kind")
        return {
            "kind": "spine_surface_seal",
            "hit": False,
            "law": "green-claim-stripped",
            "citation": "VOL-134",
            "provider_surface_green": False,
            "pr_automation_green": False,
            "ci_green": False,
            "live_motor": False,
            "stripped": stripped,
            "provider_seen": int(provider.get("seen", 0) or 0),
            "pr_seen": int(pr.get("seen", 0) or 0),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
