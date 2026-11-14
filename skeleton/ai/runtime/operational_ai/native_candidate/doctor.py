"""Source-only doctor verifies all original examples and split bounds."""
from __future__ import annotations
from .catalog import DOMAINS, TOTAL_EXAMPLES, iter_examples, verify_exact
from .contamination import scan
from .dedup import require_unique
from .rights import verify_rights
from .source_manifest import generate
from .split_proof import verify
from .splits import partition


def check_source() -> dict:
    examples = tuple(iter_examples())
    rights = verify_rights(examples)
    duplicates = require_unique(examples)
    split = partition(examples)
    split_proof = verify(split)
    contamination = scan(examples)
    manifest = generate()
    return {
        "schema": "skeleton.native-candidate.doctor.v1",
        "examples": len(examples), "domains": len(DOMAINS),
        "complete": verify_exact(examples),
        "rights_scoped": rights.allowed_scope == "offline_native_candidate_training",
        "unique": duplicates["unique_sources"] == TOTAL_EXAMPLES,
        "split_proof": split_proof,
        "contamination": contamination.record(),
        "manifest": manifest.record(),
        "real_training_executed": False,
        "model_quality_verified": False,
        "release_certified": False,
    }
