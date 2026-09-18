"""Measurement-only evaluation arenas.

These modules consume creator/game/world/quality/release evidence without
mutating those subsystems.
"""

from skeleton.eval.concept_to_release import (
    BENCHMARK_ID,
    BENCHMARK_SCHEMA_VERSION,
    SCORE_DIMENSIONS,
    ConceptToReleaseError,
    make_reproducible_fixture,
    score_concept_to_release,
)

__all__ = [
    "BENCHMARK_ID",
    "BENCHMARK_SCHEMA_VERSION",
    "SCORE_DIMENSIONS",
    "ConceptToReleaseError",
    "make_reproducible_fixture",
    "score_concept_to_release",
]
