"""Read-only deterministic source dry-run, never a model-quality claim."""
from __future__ import annotations
from .catalog import iter_examples
from .contamination import scan
from .dedup import require_unique
from .splits import partition
from .split_proof import verify
from .workload import build
from .strict import digest


def preview() -> dict:
    items = tuple(iter_examples())
    duplicate = require_unique(items)
    parts = partition(items)
    proof = verify(parts)
    run = build(parts)
    contaminated = scan(items)
    return {
        "schema": "skeleton.native-candidate.dry-run.v1",
        "source_count": len(items),
        "train_lines": len(run.lines),
        "validation_items": len(parts.validation),
        "holdout_items": len(parts.holdout),
        "group_isolation": proof["group_disjoint"],
        "unique_text": duplicate["unique_prompts"] == len(items),
        "exact_contamination_clear": contaminated.exact_clear,
        "near_duplicate_review_required": True,
        "source_digest": digest([e.source_digest for e in items]),
        "real_training_executed": False,
        "model_qualified": False,
        "release_certified": False,
    }
