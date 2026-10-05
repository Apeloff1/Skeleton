"""
backend.models — shared vocabulary for the backend.

``enums`` is the canonical home of every platform-wide (str, Enum) type
(Phase-10, Feb 2026). Consumers should import from here::

    from models.enums import LanguageType, ExecutionStatus

For convenience the enum names are re-exported at package level::

    from models import LanguageType

Pydantic model shapes (code_runtime, compiler_pipeline) live alongside and
import their enums from this package — never from server.py — which keeps
boot order deterministic.
"""
from models.enums import (
    AIAssistantMode,
    CodeComplexity,
    DockStatus,
    ExecutionStatus,
    ExpansionCategory,
    ExpansionStatus,
    FeatureFlag,
    HotfixPriority,
    LLMProvider,
    LanguageType,
    OptimizerType,
    SanitizerType,
    SecurityLevel,
    TooltipCategory,
    TutorialStep,
)

__all__ = [
    "AIAssistantMode",
    "CodeComplexity",
    "DockStatus",
    "ExecutionStatus",
    "ExpansionCategory",
    "ExpansionStatus",
    "FeatureFlag",
    "HotfixPriority",
    "LLMProvider",
    "LanguageType",
    "OptimizerType",
    "SanitizerType",
    "SecurityLevel",
    "TooltipCategory",
    "TutorialStep",
]
