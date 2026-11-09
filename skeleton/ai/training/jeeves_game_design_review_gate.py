"""Independent, blinded human game-design review of Jeeves training candidates.

The model-training report is intentionally not authoritative about game quality.
This module only prepares anonymized A/B text pairs and adjudicates COMPLETE
human-authored reviews. It never fabricates scores or promotes serving weights.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import secrets
from typing import Any

from .jeeves_production_game_train import ProductionCheckpointError, _strict_json
from .jeeves_production_readiness import _canonical, _save_new_private

SCHEMA = "skeleton.jeeves.game_review_blind_packet.v1"
KEY_SCHEMA = "skeleton.jeeves.game_review_key.v1"
ASSESSMENT_SCHEMA = "skeleton.jeeves.game_review_assessment.v1"
DECISION_SCHEMA = "skeleton.jeeves.game_review_adjudication.v1"
CRITERIA = (
    "playable_loop",
    "player_agency",
    "canon_and_npc_consistency",
    "technical_feasibility",
    "accessibility",
    "originality",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_bounded(path: Path, *, max_bytes: int = 8 * 1024 * 1024) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise ProductionCheckpointError("review input must be a bounded regular JSON file")
    return _strict_json(path.read_bytes())


def prepare(
    *,
    source_report: Path,
    public_packet: Path,
    private_key: Path,
) -> dict[str, Any]:
    """Create a reviewer packet and a separate private label map.

    Never hand private_key to reviewers; it would reveal which output is new.
    """
    if public_packet.resolve() == private_key.resolve():
        raise ProductionCheckpointError("public packet and adjudicator key cannot share a path")
    report = _read_bounded(source_report)
    if report.get("schema_version") != "skeleton.jeeves.game_design_answer_benchmark.v1":
        raise ProductionCheckpointError("a complete independent game benchmark is required")
    if report.get("status") != "needs_independent_game_design_review":
        raise ProductionCheckpointError("game benchmark is not ready for review")
    observations = report.get("results")
    if not isinstance(observations, list) or len(observations) != 24:
        raise ProductionCheckpointError("expected 24 game-design generations")
    for path in (public_packet, private_key):
        if path.exists() or path.is_symlink() or not path.parent.is_dir():
            raise ProductionCheckpointError("review outputs must be new paths")

    entries: list[dict[str, Any]] = []
    assignments: dict[str, str] = {}
    for index, case in enumerate(observations):
        if not isinstance(case, dict):
            raise ProductionCheckpointError("malformed generation evidence")
        required = ("family", "prompt", "parent_output", "candidate_output")
        if any(not isinstance(case.get(k), str) for k in required):
            raise ProductionCheckpointError("missing benchmark generation text")
        if not case["prompt"].strip():
            raise ProductionCheckpointError("empty game-design review prompt")
        identity = f"p{index:02d}"
        candidate_is_a = bool(secrets.randbits(1))
        a = case["candidate_output"] if candidate_is_a else case["parent_output"]
        b = case["parent_output"] if candidate_is_a else case["candidate_output"]
        assignments[identity] = "A" if candidate_is_a else "B"
        entries.append({
            "item_id": identity,
            "family": case["family"],
            "prompt": case["prompt"],
            "answer_a": a,
            "answer_b": b,
            "rubric": list(CRITERIA),
            "scores_allowed": [0, 1, 2, 3, 4],
            "critical_issue_choices": [True, False],
            "review_note_required": True,
        })
    packet = {
        "schema_version": SCHEMA,
        "benchmark_report_sha256": _sha(source_report.read_bytes()),
        "parent_checkpoint_sha256": report["parent_checkpoint_sha256"],
        "candidate_checkpoint_sha256": report["candidate_checkpoint_sha256"],
        "independent_reviewer_count_required": 2,
        "generation_count": len(entries),
        "criterion_names": list(CRITERIA),
        "candidate_identity_redacted": True,
        "candidate_promoted": False,
        "entries": entries,
    }
    packet_bytes = _canonical(packet) + b"\n"
    key = {
        "schema_version": KEY_SCHEMA,
        "packet_sha256": _sha(packet_bytes),
        "benchmark_report_sha256": packet["benchmark_report_sha256"],
        "parent_checkpoint_sha256": report["parent_checkpoint_sha256"],
        "candidate_checkpoint_sha256": report["candidate_checkpoint_sha256"],
        "candidate_label_by_item": assignments,
    }
    # Key first. If packet publication fails, reviewers never receive a partial
    # packet; the orphan private key can be safely discarded by the operator.
    _save_new_private(private_key, _canonical(key) + b"\n")
    _save_new_private(public_packet, packet_bytes)
    return {
        "status": "blind_packet_prepared",
        "packet_path": str(public_packet.resolve()),
        "packet_sha256": _sha(packet_bytes),
        "private_adjudicator_key_path": str(private_key.resolve()),
        "generation_count": len(entries),
        "human_scores_entered": False,
        "candidate_promoted": False,
    }


def _ratings(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != set(CRITERIA):
        raise ProductionCheckpointError("reviewer " + label + " lacks required rubric dimensions")
    if any(type(score) is not int or score < 0 or score > 4 for score in value.values()):
        raise ProductionCheckpointError("reviewer scores must be integers from zero through four")
    return value


def adjudicate(
    *,
    packet_path: Path,
    private_key_path: Path,
    assessment_paths: tuple[Path, Path],
    min_mean_improvement: float = 0.40,
) -> dict[str, Any]:
    """Require two distinct complete reviews, deblind, and gate regressions."""
    if not 0 < min_mean_improvement <= 2:
        raise ProductionCheckpointError("invalid minimum meaningful design improvement")
    if len({p.resolve() for p in (packet_path, private_key_path) + assessment_paths}) != 4:
        raise ProductionCheckpointError("review packet, key and assessments must be distinct")
    packet = _read_bounded(packet_path)
    key = _read_bounded(private_key_path)
    packet_sha = _sha(packet_path.read_bytes())
    if packet.get("schema_version") != SCHEMA or key.get("schema_version") != KEY_SCHEMA:
        raise ProductionCheckpointError("review packet/key schema mismatch")
    if key.get("packet_sha256") != packet_sha:
        raise ProductionCheckpointError("review packet differs from private identity key")
    if any(packet.get(k) != key.get(k) for k in (
        "benchmark_report_sha256", "parent_checkpoint_sha256", "candidate_checkpoint_sha256"
    )):
        raise ProductionCheckpointError("review checkpoint lineage mismatch")
    records = packet.get("entries")
    labels = key.get("candidate_label_by_item")
    if not isinstance(records, list) or len(records) != 24 or not isinstance(labels, dict):
        raise ProductionCheckpointError("complete 24-prompt review packet required")
    expected_ids = {f"p{i:02d}" for i in range(24)}
    if set(labels) != expected_ids or set(labels.values()) - {"A", "B"}:
        raise ProductionCheckpointError("private reviewer label map incomplete")
    if {record.get("item_id") for record in records} != expected_ids:
        raise ProductionCheckpointError("review packet item identity mismatch")

    assessments = [_read_bounded(p) for p in assessment_paths]
    reviewers: set[str] = set()
    family_gains: dict[str, list[float]] = defaultdict(list)
    case_gains: dict[str, list[float]] = defaultdict(list)
    candidate_critical: list[dict[str, str]] = []
    for assessment in assessments:
        if assessment.get("schema_version") != ASSESSMENT_SCHEMA or assessment.get("packet_sha256") != packet_sha:
            raise ProductionCheckpointError("review assessment not bound to this packet")
        reviewer = assessment.get("reviewer_id")
        if not isinstance(reviewer, str) or not 3 <= len(reviewer) <= 80 or reviewer in reviewers:
            raise ProductionCheckpointError("two distinct identified reviewers required")
        reviewers.add(reviewer)
        scores = assessment.get("ratings")
        if not isinstance(scores, list) or len(scores) != 24:
            raise ProductionCheckpointError("reviewer must score all 24 prompts")
        scored_ids = set()
        entry_by_id = {rec["item_id"]: rec for rec in records}
        for row in scores:
            if not isinstance(row, dict):
                raise ProductionCheckpointError("malformed reviewer score")
            identity = row.get("item_id")
            if identity not in expected_ids or identity in scored_ids:
                raise ProductionCheckpointError("missing or duplicate game-design case")
            scored_ids.add(identity)
            a = _ratings(row.get("scores_a"), "A")
            b = _ratings(row.get("scores_b"), "B")
            if type(row.get("critical_a")) is not bool or type(row.get("critical_b")) is not bool:
                raise ProductionCheckpointError("reviewer must resolve both critical issue flags")
            note = row.get("evidence_note")
            if not isinstance(note, str) or len(note.strip()) < 20:
                raise ProductionCheckpointError("reviewer must include concrete evidence notes")
            cand_is_a = labels[identity] == "A"
            cand = a if cand_is_a else b
            parent = b if cand_is_a else a
            critical = row["critical_a"] if cand_is_a else row["critical_b"]
            if critical:
                candidate_critical.append({"reviewer": reviewer, "item_id": identity})
            delta = sum(cand[field] - parent[field] for field in CRITERIA) / len(CRITERIA)
            family = entry_by_id[identity]["family"]
            family_gains[family].append(delta)
            case_gains[identity].append(delta)
        if scored_ids != expected_ids:
            raise ProductionCheckpointError("reviewer skipped some prompts")

    all_deltas = [value for values in case_gains.values() for value in values]
    mean_delta = sum(all_deltas) / len(all_deltas)
    by_family = {name: sum(values) / len(values) for name, values in sorted(family_gains.items())}
    non_regressive_count = sum(1 for values in case_gains.values() if min(values) >= 0)
    sufficient = (
        len(by_family) == 8
        and mean_delta >= min_mean_improvement
        and not candidate_critical
        and all(value >= -0.1 for value in by_family.values())
        and non_regressive_count >= 20
    )
    return {
        "schema_version": DECISION_SCHEMA,
        "status": "eligible_for_separate_promotion_review" if sufficient else "quality_gate_failed",
        "packet_sha256": packet_sha,
        "parent_checkpoint_sha256": packet["parent_checkpoint_sha256"],
        "candidate_checkpoint_sha256": packet["candidate_checkpoint_sha256"],
        "reviewers": sorted(reviewers),
        "fully_reviewed_pairs": 24,
        "dimensions_per_pair": len(CRITERIA),
        "mean_candidate_minus_parent_rating": round(mean_delta, 4),
        "min_required_mean_improvement": min_mean_improvement,
        "mean_gain_by_domain": {k: round(v, 4) for k, v in by_family.items()},
        "nonregressive_cases_agreed_by_reviewers": non_regressive_count,
        "candidate_critical_defects": candidate_critical,
        "human_review_complete": True,
        "game_design_quality_gate_passed": sufficient,
        "production_weights_modified": False,
        "candidate_promoted": False,
        "separate_governed_promotion_required": True,
    }


def publish_adjudication(report: dict[str, Any], output: Path) -> dict[str, Any]:
    _save_new_private(output, _canonical(report) + b"\n")
    return {**report, "adjudication_path": str(output.resolve())}


__all__ = [
    "SCHEMA", "ASSESSMENT_SCHEMA", "CRITERIA",
    "adjudicate", "prepare", "publish_adjudication",
]
