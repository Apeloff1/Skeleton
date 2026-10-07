#!/usr/bin/env python3
"""Shared fail-closed validation for P3-T2 implementation candidates."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[1]
FRONTIER = "machine/ai_masterplan_continuation_frontier.json"
MASTER = "machine/ai_master_plan.json"
TREE = "machine/ai_file_tree.json"
EVIDENCE_CONTRACT = "skeleton/ai/runtime/p3t2/evidence.py"
EVIDENCE_TEST = "skeleton/testing/test_p3t2_evidence.py"


class P3T2CandidateError(RuntimeError):
    """Candidate declaration, implementation or evidence drift."""


@dataclass(frozen=True)
class CandidateSpec:
    task_id: str
    lane_id: str
    candidate_path: str
    volumes: tuple[str, ...]
    dependencies: tuple[str, ...]
    modules: tuple[str, ...]
    tests: tuple[str, ...]
    evidence_policy_keys: tuple[str, ...]
    mirror_pairs: tuple[tuple[str, str], ...] = ()
    ai_tree_mapping_id: str | None = None

    def __post_init__(self) -> None:
        if len(self.volumes) != len(self.modules) or len(self.volumes) != len(self.tests):
            raise ValueError(f"{self.task_id} spec must map one module and test per volume")


TRAINING = CandidateSpec(
    task_id="P3T2-TRAINING-01",
    lane_id="P3T2-L2",
    candidate_path="machine/ai_p3t2_training_candidate.json",
    volumes=tuple(f"VOL-{value:03d}" for value in range(143, 150)),
    dependencies=("P3T2-DATA-01",),
    modules=(
        "skeleton/training/control_plane.py",
        "skeleton/training/distributed.py",
        "skeleton/training/checkpointing.py",
        "skeleton/training/elastic_recovery.py",
        "skeleton/training/observability.py",
        "skeleton/training/eval_gates.py",
        "skeleton/training/post_training.py",
    ),
    tests=(
        "skeleton/testing/test_training_control_plane.py",
        "skeleton/testing/test_distributed_training.py",
        "skeleton/testing/test_training_checkpointing.py",
        "skeleton/testing/test_elastic_training_recovery.py",
        "skeleton/testing/test_training_observability.py",
        "skeleton/testing/test_training_eval_gates.py",
        "skeleton/testing/test_post_training_lab.py",
    ),
    mirror_pairs=(
        ("skeleton/training/control_plane.py", "skeleton/ai/training/control_plane.py"),
        ("skeleton/training/distributed.py", "skeleton/ai/training/distributed.py"),
        ("skeleton/training/checkpointing.py", "skeleton/ai/training/checkpointing.py"),
        ("skeleton/training/elastic_recovery.py", "skeleton/ai/training/elastic_recovery.py"),
        ("skeleton/training/observability.py", "skeleton/ai/training/observability.py"),
        ("skeleton/training/eval_gates.py", "skeleton/ai/training/eval_gates.py"),
        ("skeleton/training/post_training.py", "skeleton/ai/training/post_training.py"),
    ),
    ai_tree_mapping_id="AIFT-TRAINING",
    evidence_policy_keys=(
        "exact_head_ci_required",
        "independent_closure_required",
        "current_main_reconciliation_required",
        "data_dependency_candidate_required",
        "single_revision_proof_required",
        "single_execution_subject_required",
        "independent_verifier_required",
    ),
)

LEARNING = CandidateSpec(
    task_id="P3T2-LEARNING-01",
    lane_id="P3T2-L3",
    candidate_path="machine/ai_p3t2_learning_candidate.json",
    volumes=("VOL-150", "VOL-151", "VOL-152"),
    dependencies=("P3T2-TRAINING-01",),
    modules=(
        "skeleton/training/rl_environment.py",
        "skeleton/training/curriculum.py",
        "skeleton/training/verifier_models.py",
    ),
    tests=(
        "skeleton/testing/test_rl_environments.py",
        "skeleton/testing/test_curriculum_engine.py",
        "skeleton/testing/test_verifier_model_program.py",
    ),
    mirror_pairs=(
        ("skeleton/training/rl_environment.py", "skeleton/ai/training/rl_environment.py"),
        ("skeleton/training/curriculum.py", "skeleton/ai/training/curriculum.py"),
        ("skeleton/training/verifier_models.py", "skeleton/ai/training/verifier_models.py"),
    ),
    ai_tree_mapping_id="AIFT-TRAINING",
    evidence_policy_keys=(
        "exact_head_ci_required",
        "independent_closure_required",
        "current_main_reconciliation_required",
        "training_dependency_candidate_required",
        "single_revision_proof_required",
        "single_execution_subject_required",
        "independent_verifier_required",
    ),
)

MULTIMODAL = CandidateSpec(
    task_id="P3T2-MULTIMODAL-01",
    lane_id="P3T2-L4",
    candidate_path="machine/ai_p3t2_multimodal_candidate.json",
    volumes=tuple(f"VOL-{value:03d}" for value in range(153, 160)),
    dependencies=("P3T2-DATA-01", "P3T2-TRAINING-01", "P3T2-LEARNING-01"),
    modules=(
        "skeleton/artifacts/multimodal_ingestion.py",
        "skeleton/vision/pipeline.py",
        "skeleton/document_vision/fusion.py",
        "skeleton/audio/pipeline.py",
        "skeleton/speech/runtime.py",
        "skeleton/video/pipeline.py",
        "skeleton/ai/runtime/extensions/multimodal.py",
    ),
    tests=(
        "skeleton/testing/test_multimodal_ingestion.py",
        "skeleton/testing/test_vision_pipeline.py",
        "skeleton/testing/test_document_vision.py",
        "skeleton/testing/test_audio_pipeline.py",
        "skeleton/testing/test_live_speech_runtime.py",
        "skeleton/testing/test_video_pipeline.py",
        "skeleton/testing/test_p3_deferred_multimodal_tools.py",
    ),
    evidence_policy_keys=(
        "exact_head_ci_required",
        "independent_closure_required",
        "current_main_reconciliation_required",
        "data_dependency_candidate_required",
        "training_dependency_candidate_required",
        "learning_dependency_candidate_required",
        "single_revision_proof_required",
        "single_execution_subject_required",
        "independent_verifier_required",
    ),
)


SPECS = {
    TRAINING.task_id: TRAINING,
    LEARNING.task_id: LEARNING,
    MULTIMODAL.task_id: MULTIMODAL,
}

DEPENDENCY_CANDIDATES = {
    "P3T2-DATA-01": "machine/ai_p3t2_data_candidate.json",
    "P3T2-TRAINING-01": TRAINING.candidate_path,
    "P3T2-LEARNING-01": LEARNING.candidate_path,
}


def load_json(root: Path, relative: str) -> dict[str, Any]:
    try:
        value = json.loads((root / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise P3T2CandidateError(f"cannot read {relative}") from exc
    if not isinstance(value, dict):
        raise P3T2CandidateError(f"{relative} must contain an object")
    return value


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise P3T2CandidateError(
            "git identity unavailable: " + result.stderr.strip()
        )
    return result.stdout.strip()


def _require_exact_head(root: Path, reported_head: str | None) -> str:
    actual = git(root, "rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", actual) is None:
        raise P3T2CandidateError("checkout HEAD is not a full lowercase Git SHA")
    if reported_head is not None:
        if re.fullmatch(r"[0-9a-f]{40}", reported_head) is None:
            raise P3T2CandidateError("reported exact head is malformed")
        if reported_head != actual:
            raise P3T2CandidateError("reported exact head does not match checkout")
    return actual


def _owner(frontier: Mapping[str, Any], task_id: str) -> Mapping[str, Any]:
    tranche = frontier.get("next_tranche")
    if not isinstance(tranche, dict) or tranche.get("status") != "planned":
        raise P3T2CandidateError("P3-T2 frontier must remain planned")
    owners = tranche.get("planned_task_owners")
    if not isinstance(owners, list):
        raise P3T2CandidateError("P3-T2 planned owner registry missing")
    matches = [
        value
        for value in owners
        if isinstance(value, dict) and value.get("task_id") == task_id
    ]
    if len(matches) != 1:
        raise P3T2CandidateError(f"{task_id} must have exactly one planned owner")
    return matches[0]


def _validate_dependency_candidates(
    root: Path,
    candidate: Mapping[str, Any],
    spec: CandidateSpec,
) -> None:
    if tuple(candidate.get("depends_on_task_ids", ())) != spec.dependencies:
        raise P3T2CandidateError(f"{spec.task_id} dependency identity drift")
    declared = tuple(candidate.get("dependency_candidate_paths", ()))
    expected_paths = tuple(DEPENDENCY_CANDIDATES[task] for task in spec.dependencies)
    if declared != expected_paths:
        raise P3T2CandidateError(f"{spec.task_id} dependency candidate path drift")
    for task_id, path in zip(spec.dependencies, expected_paths, strict=True):
        dependency = load_json(root, path)
        if (
            dependency.get("task_id") != task_id
            or dependency.get("status") != "implementation_candidate"
        ):
            raise P3T2CandidateError(
                f"{spec.task_id} dependency candidate is not valid: {task_id}"
            )
        promotion = dependency.get("promotion_state")
        if not isinstance(promotion, dict) or promotion.get("may_self_close") is not False:
            raise P3T2CandidateError(
                f"{spec.task_id} dependency candidate has unsafe promotion authority"
            )


def _validate_ai_tree(
    root: Path,
    tree: Mapping[str, Any],
    spec: CandidateSpec,
) -> str | None:
    if spec.ai_tree_mapping_id is None:
        return None
    mappings = tree.get("mappings")
    if not isinstance(mappings, list):
        raise P3T2CandidateError("AI file-tree mappings missing")
    mapping = next(
        (
            value
            for value in mappings
            if isinstance(value, dict)
            and value.get("id") == spec.ai_tree_mapping_id
        ),
        None,
    )
    if mapping is None:
        raise P3T2CandidateError(
            f"AI file-tree mapping missing: {spec.ai_tree_mapping_id}"
        )
    if (
        mapping.get("source") != "skeleton/training"
        or mapping.get("destination") != "skeleton/ai/training"
    ):
        raise P3T2CandidateError("AIFT-TRAINING root identity drift")
    if not set(spec.volumes).issubset(set(mapping.get("volume_refs", ()))):
        raise P3T2CandidateError(
            f"{spec.task_id} volumes escaped AIFT-TRAINING ownership"
        )
    tree_sha = git(root, "rev-parse", "HEAD:skeleton/training")
    mapped_sha = mapping.get("source_git_object_sha")
    if mapped_sha != tree_sha:
        raise P3T2CandidateError(
            "AIFT-TRAINING source tree identity does not match exact checkout"
        )
    return tree_sha


def validate_candidate(
    spec: CandidateSpec,
    root: Path = ROOT,
    *,
    head: str | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    frontier = load_json(root, FRONTIER)
    master = load_json(root, MASTER)
    tree = load_json(root, TREE)
    candidate = load_json(root, spec.candidate_path)

    actual_head = _require_exact_head(root, head)

    if (
        candidate.get("task_id") != spec.task_id
        or candidate.get("lane_id") != spec.lane_id
        or candidate.get("status") != "implementation_candidate"
    ):
        raise P3T2CandidateError(f"{spec.task_id} candidate identity drift")
    if tuple(candidate.get("volume_refs", ())) != spec.volumes:
        raise P3T2CandidateError(f"{spec.task_id} candidate volume identity drift")

    owner = _owner(frontier, spec.task_id)
    if (
        owner.get("lane_id") != spec.lane_id
        or owner.get("planning_status") != "planned"
        or tuple(owner.get("depends_on", ())) != spec.dependencies
        or tuple(owner.get("primary_volume_refs", ())) != spec.volumes
    ):
        raise P3T2CandidateError(f"{spec.task_id} planned owner drift")
    for key in ("completion_checkbox", "implementation_signed", "verification_signed"):
        if owner.get(key) is not False:
            raise P3T2CandidateError(f"{spec.task_id} owner illegally promoted {key}")

    promotion = candidate.get("promotion_state")
    if not isinstance(promotion, dict):
        raise P3T2CandidateError(f"{spec.task_id} promotion state missing")
    for key in (
        "completion_checkbox",
        "implementation_signed",
        "verification_signed",
        "may_self_close",
    ):
        if promotion.get(key) is not False:
            raise P3T2CandidateError(f"{spec.task_id} illegally promoted {key}")

    policy = candidate.get("evidence_policy")
    if not isinstance(policy, dict):
        raise P3T2CandidateError(f"{spec.task_id} evidence policy missing")
    for key in spec.evidence_policy_keys:
        if policy.get(key) is not True:
            raise P3T2CandidateError(f"{spec.task_id} missing evidence policy: {key}")

    if candidate.get("evidence_contract") != EVIDENCE_CONTRACT:
        raise P3T2CandidateError(f"{spec.task_id} evidence contract drift")
    for required in (EVIDENCE_CONTRACT, EVIDENCE_TEST):
        if not (root / required).is_file():
            raise P3T2CandidateError(f"shared P3-T2 evidence file missing: {required}")

    _validate_dependency_candidates(root, candidate, spec)

    if tuple(candidate.get("implementation_modules", ())) != spec.modules:
        raise P3T2CandidateError(f"{spec.task_id} module registry drift")
    if tuple(candidate.get("executable_tests", ())) != spec.tests:
        raise P3T2CandidateError(f"{spec.task_id} executable test registry drift")

    cross_plane = tuple(candidate.get("cross_plane_regressions", ()))
    if not cross_plane or EVIDENCE_TEST not in cross_plane:
        raise P3T2CandidateError(
            f"{spec.task_id} must carry shared evidence regression coverage"
        )
    if len(cross_plane) != len(set(cross_plane)):
        raise P3T2CandidateError(f"{spec.task_id} cross-plane tests contain duplicates")

    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        raise P3T2CandidateError("masterplan volume registry missing")
    by_key = {
        value.get("key"): value
        for value in volumes
        if isinstance(value, dict) and value.get("key")
    }
    for volume_ref, module, test in zip(
        spec.volumes,
        spec.modules,
        spec.tests,
        strict=True,
    ):
        volume = by_key.get(volume_ref)
        if not isinstance(volume, dict):
            raise P3T2CandidateError(f"masterplan volume missing: {volume_ref}")
        if volume.get("completion_checkbox") is not False:
            raise P3T2CandidateError(f"{volume_ref} completion checkbox self-promoted")
        if volume.get("implementation_status") != "implemented":
            raise P3T2CandidateError(
                f"{volume_ref} must remain implemented-but-unverified for this candidate"
            )
        if module not in volume.get("implementation_paths", ()):
            raise P3T2CandidateError(
                f"{volume_ref} missing canonical implementation path: {module}"
            )
        tests = volume.get("tests", ())
        if test not in tests or f"planned:{test}" in tests:
            raise P3T2CandidateError(
                f"{volume_ref} missing executable regression: {test}"
            )
        if not (root / module).is_file() or not (root / test).is_file():
            raise P3T2CandidateError(
                f"{volume_ref} declared implementation evidence is missing"
            )

    for test in cross_plane:
        if not (root / test).is_file():
            raise P3T2CandidateError(f"cross-plane regression missing: {test}")

    declared_pairs = tuple(
        tuple(value)
        for value in candidate.get("mirror_pairs", ())
        if isinstance(value, list)
    )
    if declared_pairs != spec.mirror_pairs:
        raise P3T2CandidateError(f"{spec.task_id} mirror pair registry drift")
    for source, destination in spec.mirror_pairs:
        if not (root / source).is_file() or not (root / destination).is_file():
            raise P3T2CandidateError(
                f"{spec.task_id} training mirror file missing: {source} -> {destination}"
            )
        if (root / source).read_bytes() != (root / destination).read_bytes():
            raise P3T2CandidateError(
                f"{spec.task_id} training mirror parity drift: {source}"
            )

    source_tree_sha = _validate_ai_tree(root, tree, spec)

    return {
        "status": "valid",
        "task_id": spec.task_id,
        "lane_id": spec.lane_id,
        "volume_refs": list(spec.volumes),
        "volume_count": len(spec.volumes),
        "implementation_module_count": len(spec.modules),
        "executable_test_count": len(spec.tests),
        "cross_plane_test_count": len(cross_plane),
        "mirror_pair_count": len(spec.mirror_pairs),
        "dependency_task_ids": list(spec.dependencies),
        "reported_head": head,
        "actual_head": actual_head,
        "source_tree_sha": source_tree_sha,
        "completion_checkbox": False,
        "implementation_signed": False,
        "verification_signed": False,
        "promotion_authority": False,
    }
