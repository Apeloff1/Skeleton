"""Sparse, capability-complete, locally governed supervised curriculum.

Do not conflate the immutable 720-row *reference bank* with the active
training set. This selector chooses 36-72 actual training records from the
504-row permitted train pool; 216 validation/test examples are NEVER an
input. Every selected record has a distinct task-mode capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .offline_foundations import (
    DATASET_ID, FAMILIES, ORACLES, SyntheticCurriculumError,
    _json_equal, _read_bytes, _split_rows, _strict_json, validate_curriculum,
    evaluate_predictions,
)

SCHEMA = "skeleton.offline_sparse_capability.v1"
DEFAULT_BUDGET = 36
MAX_BUDGET = 72
MIN_BUDGET = 36
HARDWARE_BUDGETS = {"low-memory": 36, "consumer": 48, "workstation": 72}

CAPABILITIES: dict[str, tuple[str, str, str]] = {
    "integer_arithmetic": ("arithmetic_addition", "score_accumulation", "arithmetic_multiplication"),
    "grid_navigation": ("grid_right_up", "grid_left_down", "grid_east_south"),
    "aabb_collision": ("positive_rectangle_overlap", "edge_contact_not_overlap", "separated_rectangles"),
    "discrete_motion": ("motion_two_ticks", "motion_three_ticks", "motion_four_ticks"),
    "finite_state": ("transition_variant_a", "transition_variant_b", "transition_variant_c"),
    "inventory": ("inventory_addition", "inventory_removal", "inventory_insufficient_stock"),
    "source_grounding": ("source_supported_citation", "unsupported_question_abstention", "injection_tainted_source"),
    "json_extraction": ("json_health_update", "json_position_extract", "json_selected_fields"),
    "game_mechanics": ("hitpoint_damage", "collectible_score", "cooldown_arithmetic"),
    "offline_authority": ("authorized_local_read", "network_request_denial", "executable_launch_denial"),
    "event_chronology": ("event_ordering", "event_duration", "latest_event"),
    "text_normalization": ("punctuation_normalization", "whitespace_collapsing", "token_order_preservation"),
}
assert set(CAPABILITIES) == set(FAMILIES)
assert all(len(names) == 3 and len(set(names)) == 3 for names in CAPABILITIES.values())

# Spaced representatives, not consecutive near-identical arithmetic parameters.
# Two samples/mode at most. All indices are within the designated train pool.
_FIRST_GROUPS = (0, 5, 10)
_SECOND_GROUPS = (13, 8, 3)
_FORMAT = "<user>\n{instruction}\n<assistant>\n{response}\n<end>\n"


@dataclass(frozen=True, slots=True)
class SparseCapabilityExample:
    capability_id: str
    family: str
    sample_id: str
    group_id: str
    source_split: str
    instruction: str
    response: str
    oracle: str

    def as_record(self) -> dict[str, str]:
        return {
            "capability_id": self.capability_id,
            "family": self.family,
            "sample_id": self.sample_id,
            "group_id": self.group_id,
            "source_split": self.source_split,
            "oracle": self.oracle,
            "instruction": self.instruction,
            "response": self.response,
        }


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _budget(requested: int) -> int:
    if type(requested) is not int or not MIN_BUDGET <= requested <= MAX_BUDGET:
        raise SyntheticCurriculumError("sparse training budget must be 36-72 records")
    return requested


def _candidate_ids() -> tuple[tuple[str, str, int], ...]:
    return tuple(
        (family, CAPABILITIES[family][variant], variant)
        for family in FAMILIES for variant in range(3)
    )


def build_sparse_capability_plan(
    directory: str | Path,
    *,
    budget: int = DEFAULT_BUDGET,
    focus_modes: Sequence[str] = (),
) -> dict[str, Any]:
    """Return an ordered, immutable-in-practice training plan, never train."""
    budget = _budget(budget)
    baseline = validate_curriculum(directory)
    root = Path(directory).expanduser()
    manifest = _strict_json(_read_bytes(root / "manifest.json").decode("utf-8"))
    train = _split_rows(root, manifest, "train")
    by_id = {item["id"]: item for item in train}
    if len(by_id) != 504:
        raise SyntheticCurriculumError("training pool identity is not unique")
    choices: list[SparseCapabilityExample] = []
    seen_groups: set[str] = set()
    members = _candidate_ids()
    if isinstance(focus_modes, (str, bytes)) or not isinstance(focus_modes, (list, tuple)):
        raise SyntheticCurriculumError("focus modes must be a sequence of known capability IDs")
    focus = tuple(focus_modes)
    known = {family + ":" + title for family, title, _ in members}
    if (
        len(focus) > len(members) or len(set(focus)) != len(focus)
        or any(type(x) is not str or x not in known for x in focus)
    ):
        raise SyntheticCurriculumError("invalid or duplicate adaptive focus capability")
    rank = {item: i for i, item in enumerate(focus)}
    secondary = sorted(
        members,
        key=lambda member: (
            0 if member[0] + ":" + member[1] in rank else 1,
            rank.get(member[0] + ":" + member[1], 0),
        ),
    )
    # Round-robin: one for each capability BEFORE selecting a second for
    # any capability. Higher hardware tiers don't unlock different features.
    for phase in (0, 1):
        group_choices = _FIRST_GROUPS if phase == 0 else _SECOND_GROUPS
        for family, title, variant in (members if phase == 0 else secondary):
            if len(choices) >= budget:
                break
            group_number = group_choices[variant]
            key = f"ofv1-{family}-{group_number:02}-{variant}"
            item = by_id.get(key)
            if item is None or item["split"] != "train" or item["oracle"] != ORACLES[family]:
                raise SyntheticCurriculumError("sparse capability source selection failed closed")
            group = item["group_id"]
            if group in seen_groups:
                raise SyntheticCurriculumError("active training scenarios are not disjoint")
            seen_groups.add(group)
            choices.append(
                SparseCapabilityExample(
                    capability_id=family + ":" + title,
                    family=family,
                    sample_id=key,
                    group_id=group,
                    source_split="train",
                    instruction=item["instruction"],
                    response=item["response"],
                    oracle=item["oracle"],
                )
            )
        if len(choices) >= budget:
            break
    capability_ids = [x.capability_id for x in choices]
    covered = set(capability_ids)
    if len(choices) != budget or len(covered) != len(members):
        raise SyntheticCurriculumError("sparse training omitted required capability modes")
    if any(capability_ids.count(x) > 2 for x in covered):
        raise SyntheticCurriculumError("sparse training exceeded per-capability data cap")
    corpus = "".join(
        _FORMAT.format(instruction=item.instruction, response=item.response)
        for item in choices
    ).encode("utf-8")
    rows = tuple(item.as_record() for item in choices)
    canonical = (
        "".join(json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                + "\n" for x in rows)
    ).encode("utf-8")
    return {
        "schema_version": SCHEMA,
        "source_dataset_id": DATASET_ID,
        "source_manifest_sha256": baseline["manifest_sha256"],
        "source_train_corpus_sha256": baseline["train_only_export_sha256"],
        "sample_budget": budget,
        "focus_modes": list(focus),
        "adaptive_focus_requested": bool(focus),
        "capability_modes_available": len(members),
        "capability_modes_covered": len(covered),
        "source_training_pool": 504,
        "heldout_source_rows": 216,
        "active_training_rows": len(rows),
        "per_mode_upper_bound": 2,
        "selected_sample_ids": [x.sample_id for x in choices],
        "selected_scenario_groups": [x.group_id for x in choices],
        "capability_ids": sorted(covered),
        "active_rows": rows,
        "training_text": corpus,
        "training_text_sha256": _digest(corpus),
        "active_jsonl": canonical,
        "active_jsonl_sha256": _digest(canonical),
        "heldout_rows_selected": 0,
        "trained_weights_promoted": False,
        "capability_proficiency_verified": False,
        "hardware_acceleration_verified": False,
    }


def sparse_plan_receipt(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Safe audit receipt: no supervised answers or heldout labels embedded."""
    excluded = {"active_rows", "active_jsonl", "training_text"}
    return {key: value for key, value in plan.items() if key not in excluded}


def assess_heldout_capabilities(
    directory: str | Path,
    prediction_file: str | Path,
    *,
    split: str = "validation",
) -> dict[str, Any]:
    """Evidence-based 36-mode scorecard. Does not train or leak test answers.

    Held-out predictions are checked by the existing strict scorer before
    deriving the per-mode breakdown. Missing/duplicate/unknown answers fail.
    Scoring never changes which training samples are selected.
    """
    if split not in ("validation", "test"):
        raise SyntheticCurriculumError("capability proficiency requires held-out split")
    result = evaluate_predictions(directory, prediction_file, split=split)
    manifest = _strict_json(
        _read_bytes(Path(directory) / "manifest.json").decode("utf-8")
    )
    rows = _split_rows(Path(directory), manifest, split)
    raw = _read_bytes(Path(prediction_file))
    try:
        lines = raw.decode("utf-8", "strict").splitlines()
    except UnicodeError as exc:
        raise SyntheticCurriculumError("capability predictions must be UTF-8") from exc
    predictions: dict[str, str] = {}
    for line in lines:
        candidate = _strict_json(line)
        if (
            not isinstance(candidate, dict)
            or set(candidate) != {"id", "prediction"}
            or not isinstance(candidate["id"], str)
            or not isinstance(candidate["prediction"], str)
            or candidate["id"] in predictions
        ):
            raise SyntheticCurriculumError("invalid held-out capability prediction")
        predictions[candidate["id"]] = candidate["prediction"].strip()
    by_mode: dict[str, dict[str, int]] = {
        family + ":" + label: {"correct": 0, "total": 0}
        for family, modes in CAPABILITIES.items() for label in modes
    }
    for row in rows:
        variant = int(row["id"].rsplit("-", 1)[1])
        key = row["family"] + ":" + CAPABILITIES[row["family"]][variant]
        prediction = predictions[row["id"]]
        if row["oracle"] in ("exact_json", "inventory_oracle", "json_exact"):
            try:
                accurate = _json_equal(prediction, _strict_json(row["response"]))
            except (ValueError, SyntheticCurriculumError):
                accurate = False
        else:
            accurate = prediction == row["response"]
        by_mode[key]["correct"] += int(accurate)
        by_mode[key]["total"] += 1
    if (
        len(by_mode) != 36 or any(value["total"] != 3 for value in by_mode.values())
        or sum(value["correct"] for value in by_mode.values()) != result["correct"]
    ):
        raise SyntheticCurriculumError("held-out capability scoring contract drift")
    weakest = sorted(
        key for key, value in by_mode.items()
        if value["correct"] != value["total"]
    )
    return {
        "schema_version": "skeleton.offline_sparse_capability.evaluation.v1",
        "source_split": split,
        "prediction_sha256": result["predictions_sha256"],
        "available_modes": 36,
        "evaluated_modes": 36,
        "modes_perfect_on_heldout": 36 - len(weakest),
        "modes_with_observed_errors": weakest,
        "heldout_correct": result["correct"],
        "heldout_total": result["total"],
        "per_mode": by_mode,
        "training_data_modified": False,
        "promotion_authorized": False,
        "real_world_generalization_proven": False,
    }


def register_sparse_capability_plan(
    directory: str | Path, plan: Mapping[str, Any], registry: Any,
) -> str:
    """Rebuild and verify the sparse plan BEFORE registry mutation.

    A caller-crafted plan cannot substitute alternate answer text, rights or
    held-out rows by simply recomputing its own SHA-256 digest.
    """
    if not isinstance(plan, Mapping):
        raise SyntheticCurriculumError("invalid sparse plan mapping")
    expected = build_sparse_capability_plan(
        directory,
        budget=plan.get("sample_budget"),
        focus_modes=plan.get("focus_modes", ()),
    )
    if dict(plan) != expected:
        raise SyntheticCurriculumError("sparse plan differs from verified source training pool")
    from skeleton.ai.runtime.training.data import (
        DataQualityReport, DataQualityRule, DatasetManifest,
        DatasetSplit, IngestEnvelope, SyntheticDataReceipt,
    )
    from skeleton.ai.runtime.training.trainer import corpus_digest

    budget = _budget(plan["sample_budget"])
    if plan["active_training_rows"] != budget or plan["heldout_rows_selected"] != 0:
        raise SyntheticCurriculumError("cannot register invalid sparse training plan")
    text = plan["training_text"]
    if not isinstance(text, bytes) or _digest(text) != plan["training_text_sha256"]:
        raise SyntheticCurriculumError("sparse training corpus identity changed")
    identities = plan["selected_sample_ids"]
    if (
        len(identities) != budget
        or len(set(identities)) != budget
        or any(not str(x).startswith("ofv1-") for x in identities)
        or plan["capability_modes_covered"] != 36
    ):
        raise SyntheticCurriculumError("sparse plan identity/coverage mismatch")
    source_id = f"original-synthetic:skeleton-offline-sparse:b{budget:03}"
    rights = IngestEnvelope.from_bytes(
        source_id=source_id,
        payload=text,
        parser_version=SCHEMA,
        classification="public",
        rights=("training",),
        trusted=True,
        acquired_at=datetime(2026, 10, 9, tzinfo=timezone.utc),
    )
    registry.register_ingest(rights)
    identity = f"{DATASET_ID}-sparse"
    gen_config = json.dumps(
        {"version": SCHEMA, "budget": budget,
         "source_manifest_sha256": plan["source_manifest_sha256"],
         "corpus_sha256": plan["training_text_sha256"]},
        sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    manifest = DatasetManifest(
        dataset_id=identity,
        version=f"1.0.0-b{budget:03}",
        splits=(DatasetSplit(
            name="train", digest=corpus_digest((text.decode("utf-8"),)),
            record_count=budget,
        ),),
        source_ingest_digests=(rights.content_digest,),
        classification="public",
        permitted_uses=("training",),
        retention_class="sparse-synthetic-operator-controlled-v1",
        parser_versions=(SCHEMA,),
        synthetic_receipt=SyntheticDataReceipt(
            generator_id=SCHEMA,
            generator_config_digest=_digest(gen_config),
            source_dataset_digests=(),
            seed=1729,
            generated_record_count=budget,
        ),
        pii_present=False, contamination_labels=(),
    )
    digest = registry.register_dataset(manifest)
    rules = (
        DataQualityRule("sparse-exact-budget", "samples", "==", budget),
        DataQualityRule("capability-breadth", "covered_modes", "==", 36),
        DataQualityRule("zero-heldout-answers", "heldout_rows", "==", 0),
        DataQualityRule("strict-two-per-mode", "largest_mode_count", "<=", 2),
    )
    counts = {
        item: sum(row["capability_id"] == item for row in plan["active_rows"])
        for item in plan["capability_ids"]
    }
    metrics = {
        "samples": float(budget),
        "covered_modes": float(len(counts)),
        "heldout_rows": 0.0,
        "largest_mode_count": float(max(counts.values())),
    }
    registry.record_quality(DataQualityReport.evaluate(digest, rules, metrics))
    registry.require_training_ready(digest)
    return digest


__all__ = [
    "SCHEMA", "DEFAULT_BUDGET", "MAX_BUDGET", "HARDWARE_BUDGETS",
    "CAPABILITIES", "SparseCapabilityExample", "SyntheticCurriculumError",
    "build_sparse_capability_plan", "sparse_plan_receipt",
    "assess_heldout_capabilities", "register_sparse_capability_plan",
]
