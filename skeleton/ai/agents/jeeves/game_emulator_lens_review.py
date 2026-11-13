"""Catalog-wide, evidence-bound Jeeves/Dragon/adversary review of emulator learning.

This is a REVIEW instrument over the existing native emulator trainer, not a
new emulator, model, watcher, provider, or training authority. Each registered
semantic lens gets one source-pinned falsification task. A digest only detects
internal changes: it does not authenticate an operator's report or establish
an independent native replay. No prompt, screen, ROM, or model weights leave
the canonical training report through this projection.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from types import SimpleNamespace
from collections.abc import Mapping
from typing import Any

from .agent.lens_system import LensCatalog
from .agent.semantic_depth_lenses import register_depth_lenses
from .agent.semantic_extreme_lenses import register_rare_lenses
from .agent.semantic_frontier import FrontierSemanticRegistry
from .agent.semantic_plane_lenses import register_plane_lenses
from .agent.semantic_research_lenses import register_research_lenses
from .game_emulator_training_lab import MAX_LAB_RUNS, SCHEMA as TRAINING_SCHEMA
from .game_learning import _digest

SCHEMA = "skeleton.game.emulator_full_lens_review.v1"
_SHA = re.compile(r"^[0-9a-f]{64}$")
MAX_PAGE = 512


class EmulatorLensReviewError(ValueError):
    """A source, catalog, resource, or authority check failed."""


def complete_lens_registry() -> FrontierSemanticRegistry:
    """Reuse the canonical catalogs; register no shadow lenses or duplicate keys."""
    registry = FrontierSemanticRegistry()
    register_rare_lenses(registry)
    register_depth_lenses(registry)
    register_research_lenses(registry)
    register_plane_lenses(registry)
    return registry


def _all_review_specs() -> tuple[Any, ...]:
    """Unify the two existing Jeeves catalogs for review without re-registering.

    Routing lenses use their own LensCatalog and authority model. The adapter
    keeps stable prefixed identifiers rather than pretending that routing
    operators and semantic hypotheses are the same type or evidence source.
    """
    semantic = complete_lens_registry().all()
    routing = tuple(
        SimpleNamespace(
            key="routing/" + item.lens_id,
            family=item.family,
            role=SimpleNamespace(value="routing_" + item.authority.value),
            lineage_year=0,
            minimum_observations=1,
            pairwise=False,
            sequential=False,
            description=item.description,
            asks=item.outputs or (item.description,),
            predicts="Routing operator proposes a research direction, not a measurement",
            failure_mode="Compare the proposed routing choice with a disconfirming native replay",
        )
        for item in LensCatalog().all()
    )
    return tuple(sorted((*semantic, *routing), key=lambda item: item.key))


def _positive(value: Any, name: str, *, minimum: int = 0, maximum: int = 2**31) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise EmulatorLensReviewError(f"{name} is not an integer in its permitted range")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise EmulatorLensReviewError(f"{name} must be an exact SHA-256 digest")
    return value


def validate_training_receipts(report: Mapping[str, Any]) -> dict[str, Any]:
    """Check bounded source-to-report consistency, not native replay authenticity.

    An operator can forge a whole report and its unkeyed digest. Only the
    original runner and an independent replay/audit can verify native custody.
    """
    if not isinstance(report, Mapping) or report.get("schema_version") != TRAINING_SCHEMA:
        raise EmulatorLensReviewError("expected the canonical emulator training report")
    source_digest = _sha(report.get("report_digest"), "training report digest")
    if _digest({key: value for key, value in report.items() if key != "report_digest"}) != source_digest:
        raise EmulatorLensReviewError("training report was modified after sealing")
    lineage = report.get("source_lineage")
    if not isinstance(lineage, Mapping) or lineage.get("rights_acknowledged") is not True:
        raise EmulatorLensReviewError("source has no explicit rights acknowledgement")
    count = _positive(report.get("run_count"), "run_count", minimum=1, maximum=MAX_LAB_RUNS)
    receipts = report.get("audited_run_receipts")
    if not isinstance(receipts, list) or len(receipts) != count:
        raise EmulatorLensReviewError("audited run receipt count does not match report")
    if report.get("actual_neural_parameter_updates") != 0:
        raise EmulatorLensReviewError("neural weight promotion is not part of this report")
    source_steps = 0
    source_updates = 0
    receipt_digests = []
    traces = set()
    for ordinal, item in enumerate(receipts):
        if not isinstance(item, Mapping):
            raise EmulatorLensReviewError("run receipt must be an object")
        digest = _sha(item.get("receipt_digest"), "run receipt digest")
        if _digest({k: v for k, v in item.items() if k != "receipt_digest"}) != digest:
            raise EmulatorLensReviewError(f"run receipt {ordinal} changed")
        controls = item.get("scrutiny_checks")
        if (
            not isinstance(controls, Mapping)
            or len(controls) < 10
            or any(value is not True for value in controls.values())
            or item.get("training_commit") is not True
        ):
            raise EmulatorLensReviewError(f"run receipt {ordinal} did not clear replay scrutiny")
        _sha(item.get("trace_digest"), "source trace digest")
        steps = _positive(item.get("actual_steps"), "native steps", minimum=1, maximum=128)
        replay = _positive(item.get("actual_replay_steps"), "native replay steps", minimum=steps)
        updates = _positive(item.get("actual_tabular_q_updates"), "Q updates", maximum=128)
        if replay < steps:
            raise EmulatorLensReviewError("native reverse replay accounting is inconsistent")
        source_steps += steps
        source_updates += updates
        receipt_digests.append(digest)
        traces.add(item["trace_digest"])
    if (
        report.get("actual_training_steps") != source_steps
        or report.get("actual_q_table_updates") != source_updates
    ):
        raise EmulatorLensReviewError("source-run Q/step accounting does not match")
    if len(traces) != len(receipts):
        raise EmulatorLensReviewError("duplicate trace identity cannot count as separate run")
    return {
        "report_digest": source_digest,
        "run_count": count,
        "replayed_step_count": source_steps,
        "tabular_q_updates": source_updates,
        "receipt_digests": tuple(receipt_digests),
        "independent_native_replay_in_this_review": False,
    }


def _channel_checks(family: str) -> tuple[str, ...]:
    # Prompts focus inspection; these channels do not assert that a mechanic,
    # narrative, audio signal, or visual pattern was actually observed.
    families = {
        "film": ("frame temporal continuity", "camera/cut falsifier"),
        "cinema": ("frame temporal continuity", "camera/cut falsifier"),
        "literature": ("narrative trace provenance", "voice-continuity counterexample"),
        "literary": ("narrative trace provenance", "voice-continuity counterexample"),
        "narrative": ("event ordering", "branch/ending counterexample"),
        "game": ("state-action accessibility", "counterfactual controller probe"),
        "ludic": ("state-action accessibility", "counterfactual controller probe"),
        "semiotic": ("cue-to-effect correspondence", "false-affordance counterexample"),
        "cognitive": ("revisit versus novel perception", "recall/interference alternative"),
        "memory": ("revisit versus novel perception", "recall/interference alternative"),
        "rhetoric": ("dialogue choice consequences", "speaker-meaning counterexample"),
        "pragmatic": ("dialogue choice consequences", "speaker-meaning counterexample"),
        "social": ("agent incentive alternatives", "unobserved actor caveat"),
        "temporal": ("checkpoint timeline", "delayed effect counterexample"),
        "system": ("state invariant", "failure and recovery trace"),
        "causal": ("intervention/control contrast", "confounder alternative"),
        "information": ("observed frame/action entropy", "unmeasured channel caveat"),
        "computational": ("replay determinism", "resource/edge-case falsifier"),
        "metacognitive": ("evidence calibration", "plateau/novelty failure"),
        "probability": ("sample-size uncertainty", "heldout-leakage falsifier"),
        "predictive": ("out-of-run holdout shift", "error/calibration counterexample"),
    }
    return families.get(family, ("source-grounded alternative", "unknown-mechanism falsifier"))


def review_verified_training_report(
    report: Mapping[str, Any], *,
    offset: int = 0,
    limit: int = MAX_PAGE,
) -> dict[str, Any]:
    """Schedule *every* canonical lens in deterministic pages for the triad.

    The Dragon and adversarial lanes are explicit OPEN tasks until independent
    receipts are submitted through their canonical authority. They are never
    silently manufactured by this projection. These are research prompts,
    not training gradients or proven game completion.
    """
    source = validate_training_receipts(report)
    start = _positive(offset, "offset", maximum=1_000_000)
    page_size = _positive(limit, "limit", minimum=1, maximum=MAX_PAGE)
    all_specs = _all_review_specs()
    if len(all_specs) != len({spec.key for spec in all_specs}):
        raise EmulatorLensReviewError("lens keys are not unique")
    total = len(all_specs)
    catalog_digest = _digest([
        [spec.key, spec.family.value, spec.role.value, spec.lineage_year,
         spec.minimum_observations, spec.pairwise, spec.sequential]
        for spec in all_specs
    ])
    entries = []
    for spec in all_specs[start:start + page_size]:
        needed = max(spec.minimum_observations, 2 if spec.pairwise else 1,
                     3 if spec.sequential else 1)
        # Actual episode receipts, rather than invented semantic observations,
        # are a conservative minimum for choosing follow-up inspections.
        eligible = source["run_count"] >= needed
        index = int(hashlib.sha256(
            (source["report_digest"] + "|" + spec.key).encode("ascii")
        ).hexdigest()[:12], 16) % source["run_count"]
        support = tuple(
            source["receipt_digests"][(index + delta) % source["run_count"]]
            for delta in range(min(source["run_count"], needed))
        )
        checks = _channel_checks(spec.family.value)
        entry = {
            "lens_key": spec.key,
            "family": spec.family.value,
            "role": spec.role.value,
            "catalog_lineage_year": spec.lineage_year,
            "source_report_digest": source["report_digest"],
            "source_receipt_digests": support,
            "required_distinct_replayed_runs": needed,
            "available_replayed_runs": source["run_count"],
            "review_material_ready": eligible,
            "jeeves_playback": {
                "source": "replay-audited_emulator_training_report",
                "task": checks[0],
                "status": "receipt_indices_identified_not_independently_replayed",
            },
            "dragon_observation": {
                "task": spec.asks[0] if spec.asks else spec.description,
                "status": "awaiting_independent_consent_scoped_observation",
            },
            "adversarial_review": {
                "task": spec.failure_mode,
                "counterexample_to_test": checks[1],
                "status": "awaiting_independent_counterexample_execution",
            },
            "proposed_prediction_not_a_fact": spec.predicts,
            "semantic_interpretation_asserted": False,
            "evidence_triangulation_complete": False,
            "ai_gradient_updates_by_review": 0,
        }
        entry["review_id"] = _digest([SCHEMA, catalog_digest, source["report_digest"], spec.key])
        entries.append(entry)
    counts = Counter(entry["family"] for entry in entries)
    result = {
        "schema_version": SCHEMA,
        "source_report_digest": source["report_digest"],
        "source_integrity": {
            "sha256_structure_verified": True,
            "native_runtime_reexecuted": False,
            "operator_report_authenticated": False,
            "source_run_count": source["run_count"],
            "source_actual_steps_claimed_by_report": source["replayed_step_count"],
            "source_tabular_q_updates_claimed_by_report": source["tabular_q_updates"],
        },
        "catalog_digest": catalog_digest,
        "catalog_lens_count": total,
        "offset": start,
        "page_size": len(entries),
        "next_offset": start + len(entries) if start + len(entries) < total else None,
        "review_lens_count": len(entries),
        "family_coverage_in_page": dict(sorted(counts.items())),
        "review_material_ready_count": sum(row["review_material_ready"] for row in entries),
        "independent_dragon_observations": 0,
        "independent_adversarial_reviews": 0,
        "actual_neural_parameter_updates_by_review": 0,
        "production_model_promotion_authorized": False,
        "reviews": entries,
    }
    result["review_digest"] = _digest(result)
    return result
