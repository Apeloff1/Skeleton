from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from skeleton.learning.mirror_room import (
    MirrorCandidate,
    MirrorRoomObservatory,
    mirror_room_file_tree,
)


ROOT = Path(__file__).resolve().parents[2]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _candidate(candidate_id: str, skill: float, *, parent: str | None = None):
    return MirrorCandidate(
        candidate_id=candidate_id,
        version=f"v-{candidate_id}",
        producer_id="learner",
        change_ref=f"change:{candidate_id}",
        change_digest=_sha(candidate_id),
        parameters={"skill": skill},
        parent_candidate_id=parent,
    )


def _metric(metric_id: str, baseline: float, candidate: float):
    return SimpleNamespace(
        metric_id=metric_id,
        baseline_mean=baseline,
        candidate_mean=candidate,
    )


def _attempt(
    attempt: int,
    baseline: MirrorCandidate,
    candidate: MirrorCandidate,
    *,
    accepted: bool,
):
    report = SimpleNamespace(
        weighted_utility_delta=0.08 if accepted else -0.02,
        metric_comparisons=(
            _metric("content.correctness", 0.80, 0.90),
            _metric("content.specificity", 0.70, 0.88),
            _metric("content.information_density", 0.75, 0.91),
        ),
    )
    return SimpleNamespace(
        attempt=attempt,
        accepted=accepted,
        baseline_before=baseline,
        candidate=candidate,
        baseline_after=candidate if accepted else baseline,
        validation_report=report,
        required_weighted_gain=0.03,
        required_strict_metric_gain=0.01,
        retention_scenario_digests=("a" * 64, "b" * 64),
        rejection_reasons=() if accepted else ("validation-gate",),
    )


def test_observatory_projects_baseline_challenger_and_detail_lift() -> None:
    baseline = _candidate("base", 0.2)
    candidate = _candidate("upgrade", 0.4, parent=baseline.candidate_id)
    observatory = MirrorRoomObservatory()
    observatory.begin(run_id="run-observe", baseline=baseline)
    observatory.record_attempt(
        _attempt(1, baseline, candidate, accepted=True)
    )

    snapshot = observatory.snapshot()
    attempt = snapshot["attempts"][0]

    assert snapshot["attempts_completed"] == 1
    assert snapshot["accepted_upgrades"] == 1
    assert snapshot["current_baseline_id"] == "upgrade"
    assert snapshot["quality_lift"] > 0.0
    assert snapshot["detail_lift"] > snapshot["quality_lift"]
    assert attempt["baseline_quality_score"] < attempt["candidate_quality_score"]
    assert attempt["baseline_detail_score"] < attempt["candidate_detail_score"]
    assert attempt["dimensions"]
    assert snapshot["production_authority"] is False


def test_observatory_rejected_attempt_cannot_move_visible_baseline() -> None:
    baseline = _candidate("base", 0.2)
    candidate = _candidate("weak", 0.1, parent=baseline.candidate_id)
    observatory = MirrorRoomObservatory()
    observatory.begin(run_id="run-reject", baseline=baseline)
    observatory.record_attempt(
        _attempt(1, baseline, candidate, accepted=False)
    )

    snapshot = observatory.snapshot()
    attempt = snapshot["attempts"][0]

    assert snapshot["current_baseline_id"] == "base"
    assert attempt["accepted"] is False
    assert attempt["effective_quality_score"] == attempt["baseline_quality_score"]
    assert attempt["rejection_reasons"] == ["validation-gate"]


def test_observatory_file_tree_exposes_landed_extension_surface() -> None:
    encoded = repr(mirror_room_file_tree())

    assert "skeleton/learning/mirror_room" in encoded
    assert "skeleton/ai/learning/mirror_room" in encoded
    assert "test_mirror_room_observability.py" in encoded
    assert "mirror-room-extensions.yml" in encoded


def test_observatory_file_tree_binds_landed_product_routes() -> None:
    encoded = repr(mirror_room_file_tree())

    assert "backend/routes/mirror_room.py" in encoded
    assert "frontend/features/MirrorRoom" in encoded
    assert "frontend/app/mirror-room.tsx" in encoded

    screen = (
        ROOT / "frontend/features/MirrorRoom/MirrorRoomObservatory.tsx"
    ).read_text(encoding="utf-8")
    route = (ROOT / "frontend/app/mirror-room.tsx").read_text(encoding="utf-8")
    types = (ROOT / "frontend/features/MirrorRoom/types.ts").read_text(
        encoding="utf-8"
    )
    api_route = (ROOT / "backend/routes/mirror_room.py").read_text(
        encoding="utf-8"
    )

    assert "/api/mirror-room/observatory" in screen
    assert "features/MirrorRoom/MirrorRoomObservatory" in route
    assert "interface MirrorRoomObservatoryPayload" in types
    assert "production_authority: false" in types
    assert "get_default_observatory().snapshot()" in api_route
    route_registry = (ROOT / "frontend/utils/routeRegistry.ts").read_text(
        encoding="utf-8"
    )
    dashboard = (ROOT / "frontend/app/dashboard.tsx").read_text(
        encoding="utf-8"
    )
    assert "path: '/mirror-room'" in route_registry
    assert "Mirror Room Observatory" in dashboard
    assert "router.push('/mirror-room'" in dashboard



def test_machine_product_tree_manifest_is_fail_closed() -> None:
    manifest = json.loads(
        (ROOT / "machine/mirror_room_file_tree.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["schema_version"] == 1
    assert manifest["authority"] == "evidence-only-observability"
    assert manifest["production_authority"] is False

    surfaces = manifest["root"]["surfaces"]
    paths = {item["path"] for item in surfaces}
    required = {
        "skeleton/learning/mirror_room",
        "skeleton/ai/learning/mirror_room",
        "backend/routes/mirror_room.py",
        "backend/core/routes_registry.py",
        "backend/core/route_policy_catalog.py",
        "frontend/features/MirrorRoom",
        "frontend/app/mirror-room.tsx",
        "frontend/utils/routeRegistry.ts",
        "frontend/app/dashboard.tsx",
        "skeleton/testing/test_mirror_room_observability.py",
        ".github/workflows/mirror-room-extensions.yml",
        "docs/plan/MIRROR_ROOM_LEARNING.md",
    }
    assert required.issubset(paths)
    for surface in surfaces:
        assert (ROOT / surface["path"]).exists(), surface["path"]
