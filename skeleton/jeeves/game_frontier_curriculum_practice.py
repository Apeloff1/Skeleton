"""Factual, independently checked Jeeves book-to-Forge practical exercise receipts.

Two algorithmically separate checks validate the real Forge transaction:
source/operation authority and byte-level receipt integrity. This is not
two human reviews, native gameplay testing, or model weight training.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from typing import Any

from skeleton.forge.game_frontier_studio import StudioError
from skeleton.forge.game_frontier_studio_authoring import _digest
from .game_frontier_book_curriculum import exemplar, reference

SCHEMA = "skeleton.jeeves.forge_source_practice_verified.v1"
SHA = frozenset("0123456789abcdef")


def _sha(value: object) -> bool:
    return (type(value) is str and len(value) == 64
            and all(token in SHA for token in value))


def verify_source_practice(
    project_id: str, generation: str, index: int, receipt: Mapping[str, Any],
    *, current_source_sha256: str, expected_candidate_sha256: str,
) -> dict[str, Any]:
    """Fail closed on altered, fictional, reordered or unowned source evidence.

    Source reviewer: book ID is resolved to a real registered action, current
    revision is pinned, actual source changed and every intermediate digest
    chains exactly. Independent structural reviewer: recompute the complete
    canonical Forge receipt hash and check schema/step boundaries.
    """
    book = reference(generation, index)
    operation = exemplar(generation, index)
    if (type(project_id) is not str or not 1 <= len(project_id) <= 128
            or not _sha(current_source_sha256)
            or not _sha(expected_candidate_sha256)
            or current_source_sha256 == expected_candidate_sha256
            or not isinstance(receipt, Mapping)):
        raise StudioError("Source book practice must have a real changed owned project")
    if (receipt.get("schema") != "skeleton.forge.frontier_authoring_batch.v1"
            or receipt.get("project_id") != project_id
            or receipt.get("source_sha256") != current_source_sha256
            or receipt.get("candidate_sha256") != expected_candidate_sha256
            or receipt.get("persisted") is not False
            or receipt.get("actually_changed") is not True
            or type(receipt.get("action_count")) is not int
            or receipt["action_count"] != 1):
        raise StudioError("Book practice proof does not match the actual Forge edit")
    steps = receipt.get("changes")
    if type(steps) is not list or len(steps) != 1:
        raise StudioError("Book practice requires one exact registered exercise action")
    step = steps[0]
    if (type(step) is not dict or set(step) != {
            "index", "operation", "before_sha256", "after_sha256", "changed"
        } or step["index"] != 0 or step["operation"] != operation
            or step["before_sha256"] != current_source_sha256
            or step["after_sha256"] != expected_candidate_sha256
            or step["changed"] is not True):
        raise StudioError("No independently traceable book-to-action source mutation")
    signature = receipt.get("receipt_sha256")
    if not _sha(signature):
        raise StudioError("Source receipt is not a valid SHA256")
    unsigned = dict(receipt)
    unsigned.pop("receipt_sha256")
    if _digest(unsigned) != signature:
        raise StudioError("Serialized source batch receipt differs from its byte checksum")
    # A second independent content digest ties the learning claim to the
    # exact verified source transaction; it is not a new runtime authority.
    witness = {
        "schema": SCHEMA,
        "project_id": project_id, "book": book["ref"],
        "source_operation": operation,
        "source_sha256": current_source_sha256,
        "candidate_sha256": expected_candidate_sha256,
        "forge_receipt_sha256": signature,
        "observed_checks": {
            "book_action_resolved": True,
            "single_step_exact_operation": True,
            "nonempty_immutable_diff": True,
            "continuous_source_digest_chain": True,
            "canonical_batch_checksum": True,
            "project_owner_correspondence": True,
        },
        "source_practice_verified": True,
        "project_saved": False,
        "native_engine_executed": False,
        "physical_event_sensors_qualified": False,
        "independent_human_reviewed": False,
        "model_weights_trained": False,
        "rights_cleared": False,
        "promotion": "not_requested",
    }
    raw = json.dumps(witness, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode("utf8")
    return {**witness, "evidence_sha256": sha256(raw).hexdigest()}
