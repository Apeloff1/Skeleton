"""
Tutolage school policies SAM CLOM KREM. Review PR 69. Do not fork a second school.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

POLICIES = ["SAM", "CLOM", "KREM"]


def process(data: dict) -> dict:
    refused = admit("tutolage_school", data)
    if refused:
        return refused
    policy = data.get("policy")
    if policy is None:
        return stamp("tutolage_school", data, {"policies": POLICIES})
    if policy not in POLICIES:
        return {
            "ok": False,
            "error": "unknown policy",
            "card": "tutolage_school",
            "policies": list(POLICIES),
        }
    return stamp("tutolage_school", data, {"policies": POLICIES, "policy": policy})
