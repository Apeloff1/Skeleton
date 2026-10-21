"""Exact Jeeves mastery path through all seven indexed Forge manuscript eras.

A single selected book resolves to a contiguous prerequisite chain without
bulk-manifesting 9.999999 billion virtual books. Progress means measurable
study/practice receipts, never an unearned claim of model-weight training.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from skeleton.forge.game_frontier_studio import StudioError
from .game_frontier_book_curriculum import (
    GENERATIONS, COMPETENCIES, PREREQUISITES,
    curriculum_catalog, reference, lesson, exemplar,
)

SCHEMA = "skeleton.jeeves.forge_learning_path.v1"
PRACTICE_CHECKS = (
    "authentic_source_revision", "exact_registered_operation",
    "source_diff_and_receipt", "new_only_canon_preservation",
    "independent_environmental_observations",
    "project_reopen_replay", "native_gameplay_separate",
    "rights_and_adversarial_review",
)


def _digest(body: dict[str, Any]) -> str:
    return sha256(json.dumps(body, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf8")).hexdigest()


def learning_path(generation: str, index: int) -> dict[str, Any]:
    """Generate all prerequisites ending at one registered book, O(7) memory.

    Every step is a concrete source-addressed lesson with an executable
    author's *candidate* edit, inherited exact book identity and parent hash.
    No source mutations, remote provider calls or persistent training occur.
    """
    names = [name for name, _, _ in GENERATIONS]
    if type(generation) is not str or generation not in names:
        raise StudioError("Learning path requires an indexed Forge generation")
    # Validates the terminal volume before computing any ancestors.
    selected = reference(generation, index)
    cursor = index
    steps = []
    previous_ref = None
    previous_receipt = None
    for level, family in reversed(list(enumerate(names[:names.index(generation)+1]))):
        # Determine exact parent IDs from end to beginning, not from a
        # prefix or a user-provided source string.
        ancestor_index = index // (10 ** (names.index(generation)-level))
        if previous_ref is None:  # first step in reverse is the terminal
            pass
        ancestor = reference(family, ancestor_index)
        steps.append((family, ancestor_index, ancestor))
    steps.reverse()
    modules = []
    for ordinal, (family, ancestor_index, book) in enumerate(steps, 1):
        task = lesson(family, ancestor_index)
        if previous_ref is not None and task["parent_reference"] != previous_ref:
            raise StudioError("Forge curriculum prerequisite chain has changed")
        row = {
            "level": ordinal,
            "generation": family,
            "book": book["ref"],
            "index": ancestor_index,
            "parent_book": previous_ref,
            "operation": task["source_exercise_action"],
            "learning_objectives": [
                "Identify exact registered source blueprint and world axes",
                "Explain the inherited world and authored narrative purpose",
                "Perform a host-scoped immutable source edit preview",
                "Verify provenance, original canon and observable event cues",
                "Review failures, rollback and downstream native qualification",
            ],
            "theory_question_count": len(task["questions"]),
            "practical_checkpoints": list(PRACTICE_CHECKS),
            "ready_for_operator_preview": True,
            "theory_assessed": False,
            "practical_evidence_verified": False,
            "weight_trained": False,
            "prerequisite_sha256": previous_receipt,
        }
        row["lesson_sha256"] = _digest(row)
        previous_ref, previous_receipt = book["ref"], row["lesson_sha256"]
        modules.append(row)
    body = {
        "schema": SCHEMA,
        "target": selected["ref"],
        "scope": "single_exact_book_with_all_ancestor_generations",
        "course_levels": len(modules),
        "modules": modules,
        "practical_checkpoints": list(PRACTICE_CHECKS),
        "provider_training_performed": False,
        "weights_promoted": False,
        "native_playthrough_claimed": False,
        "requires_independent_practical_receipts": True,
        "manifest_policy": "one_source_book_on_demand_or_four_book_bounded_ZIP",
    }
    return {**body, "curriculum_sha256": _digest(body)}


def batch_program(generation: str, index: int, *, sessions: int = 8,
                  stride: int = 1) -> dict[str, Any]:
    """Bounded curriculum of distinct indexed volumes, no eager manuscripts.

    This is a reproducible worklist for the host's existing job plane.
    It does not start a scheduler, reserve GPU memory or assert completion.
    """
    names = {name: count for name, _, count in GENERATIONS}
    if (type(generation) is not str or generation not in names
            or type(index) is not int or index < 0
            or type(sessions) is not int or not 1 <= sessions <= 16
            or type(stride) is not int or not 1 <= stride <= 1_000_000
            or index + (sessions-1) * stride >= names[generation]):
        raise StudioError("A worklist must fit within the real indexed curriculum")
    tasks = []
    for i in range(sessions):
        chosen_index = index + i * stride
        item = reference(generation, chosen_index)
        tasks.append({
            "session": i+1, "book": item["ref"], "generation": generation,
            "index": chosen_index, "exact_operation": exemplar(generation, chosen_index),
            "study": "manifest the source book, read, take exact-axis assessment",
            "practice": "preview the registered edit against the owned game project",
            "review": "record source/replay/rights evidence before human promotion",
            "status": "not_started",
        })
    body = {
        "schema": "skeleton.jeeves.forge_study_worklist.v1",
        "mode": "source-grounded_host_issued_work_only",
        "selected_generation": generation, "start_index": index,
        "sessions": sessions, "stride": stride,
        "estimated_book_count": sessions,
        "tasks": tasks,
        "issued_jobs": 0, "completed_lessons": 0,
        "model_weights_updated": False,
    }
    return {**body, "worklist_sha256": _digest(body)}
