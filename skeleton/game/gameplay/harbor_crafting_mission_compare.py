"""Replay-derived gameplay consequence preview for authored mission revisions.

Both original and revised mission boards are scored against the exact same
verified gameplay save. No points, achievements or quest outcomes are trusted
from the supplied comparison object.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .harbor_crafting import HarborError, MAX_BUNDLE_BYTES, _keys, canonical, digest, verify_bundle
from .harbor_crafting_mission_authoring import verify_mission_revision
from .harbor_crafting_missions import mission_report, verify_mission_report

SCHEMA = "skeleton.game.harbor.mission-comparison.v1"
MAX_COMPARISON_BYTES = MAX_BUNDLE_BYTES * 6


def compare_mission_revision(revision: Any, bundle: Any) -> dict[str, Any]:
    """Compare the old and edited mission rules using real replayed actions."""
    updated_board = verify_mission_revision(revision)
    verify_bundle(bundle)
    if bundle["source_digest"] != revision["source_digest"]:
        raise HarborError("mission comparison source mismatch")
    before = mission_report(bundle, revision["parent"])
    after = mission_report(bundle, updated_board)
    verified_before = verify_mission_report(before)
    verified_after = verify_mission_report(after)
    prior = set(verified_before["completed"])
    current = set(verified_after["completed"])
    result = {
        "schema": SCHEMA,
        "revision": deepcopy(revision),
        "bundle_digest": bundle["bundle_digest"],
        "before": before,
        "after": after,
        "delta_points": verified_after["points"] - verified_before["points"],
        "gained": sorted(current - prior),
        "lost": sorted(prior - current),
    }
    result["comparison_digest"] = digest(result)
    if len(canonical(result)) > MAX_COMPARISON_BYTES:
        raise HarborError("mission comparison exceeds byte limit")
    return result


def verify_mission_comparison(comparison: Any) -> dict[str, Any]:
    """Recompute both full mission journals and the edited-board delta."""
    _keys(comparison, {
        "schema", "revision", "bundle_digest", "before", "after",
        "delta_points", "gained", "lost", "comparison_digest",
    }, "mission comparison")
    if comparison["schema"] != SCHEMA or len(canonical(comparison)) > MAX_COMPARISON_BYTES:
        raise HarborError("unsupported or oversized mission comparison")
    if comparison["comparison_digest"] != digest({
        key: value for key, value in comparison.items() if key != "comparison_digest"
    }):
        raise HarborError("mission comparison digest mismatch")
    before = comparison["before"]
    if not isinstance(before, dict) or not isinstance(before.get("bundle"), dict):
        raise HarborError("mission comparison missing verified bundle")
    bundle = before["bundle"]
    if comparison["bundle_digest"] != bundle.get("bundle_digest"):
        raise HarborError("mission comparison bundle mismatch")
    reconstructed = compare_mission_revision(comparison["revision"], bundle)
    if reconstructed != comparison:
        raise HarborError("mission comparison replay mismatch")
    return {
        "delta_points": reconstructed["delta_points"],
        "gained": deepcopy(reconstructed["gained"]),
        "lost": deepcopy(reconstructed["lost"]),
        "before_points": reconstructed["before"]["points"],
        "after_points": reconstructed["after"]["points"],
    }
