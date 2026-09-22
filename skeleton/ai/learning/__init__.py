"""Canonical learning contracts for Skeleton.

Jeeves remains the implementation home during consolidation; consumers should
prefer this package when they need assessment/curriculum behavior without the
rest of the tutor/LLM surface.
"""

from skeleton.jeeves.assessment import (
    AdaptiveTest,
    AssessmentEngine,
    AssessmentError,
    BloomLevel,
    InteractionEvidence,
    SkillModel,
)
from skeleton.jeeves.curriculum import Curriculum, CurriculumError, Lesson

from .evidence import (
    Calibration,
    EvidenceProvenance,
    Feature,
    Hypothesis,
    LearningEvidenceError,
    LearningEvidenceStore,
    Observation,
    Outcome,
    Prediction,
    RecordPlane,
    UpdateKind,
    UpdateRecord,
    canonical_fingerprint,
    empty_calibration,
    make_provenance,
)
from .service import LearningService, LearningSnapshot

__all__ = [
    "AdaptiveTest",
    "AssessmentEngine",
    "AssessmentError",
    "BloomLevel",
    "Calibration",
    "Curriculum",
    "CurriculumError",
    "EvidenceProvenance",
    "Feature",
    "Hypothesis",
    "InteractionEvidence",
    "LearningEvidenceError",
    "LearningEvidenceStore",
    "LearningService",
    "LearningSnapshot",
    "Lesson",
    "Observation",
    "Outcome",
    "Prediction",
    "RecordPlane",
    "SkillModel",
    "UpdateKind",
    "UpdateRecord",
    "canonical_fingerprint",
    "empty_calibration",
    "make_provenance",
]
