"""Context substrate.

Dependency-light context primitives import eagerly. Historical exports whose
implementation belongs to the orchestration layer remain available through a
lazy compatibility facade so importing skeleton.context never pulls
forge/Jeeves/pipeline dependencies into the lower context layer.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from skeleton.context.compaction import (
    COMPACTION_VERSION,
    ContextCompactionError,
    compact_context_segment,
)
from skeleton.context.compiler import (
    COMPILER_VERSION,
    ContextAllocationPolicy,
    ContextCompilationError,
    ContextCompiler,
    ProviderContextProjection,
    project_provider_context,
)
from skeleton.context.policy import (
    ContextAdmissionDecision,
    ContextCompilePolicy,
    ContextPolicyError,
)
from skeleton.context.helix import DNAHelix, BasePair
from skeleton.context.ledger import ContextLedger, LedgerError
from skeleton.context.instruction_policy import (
    INSTRUCTION_POLICY_SCHEMA_VERSION,
    InstructionPolicy,
    InstructionPolicyError,
    InstructionPolicyRegistry,
)
from skeleton.context.skills_files import (
    ContextCard,
    IterationReport,
    SkillBank,
    SkillSpec,
    SkillsContextLoop,
    SkillsFilesError,
    TaskState,
    mastery_to_skill_file,
)
from skeleton.context.snowball import Snowball, STAGES as SNOWBALL_STAGES

def _load_lazy_module(module_name: str) -> Any:
    """Load one explicitly allowlisted lazy context module.

    Keep each import target literal so repository dynamic-import safety can prove
    the compatibility facade cannot import attacker-controlled module names.
    """
    if module_name == "skeleton.context.tensor":
        return import_module("skeleton.context.tensor")
    if module_name == "skeleton.context.dodeca":
        return import_module("skeleton.context.dodeca")
    if module_name == "skeleton.context.oracle":
        return import_module("skeleton.context.oracle")
    if module_name == "skeleton.context.cockpit":
        return import_module("skeleton.context.cockpit")
    if module_name == "skeleton.context.pipeline":
        return import_module("skeleton.context.pipeline")
    if module_name == "skeleton.context.questionnaire":
        return import_module("skeleton.context.questionnaire")
    raise RuntimeError(f"unsupported lazy context module: {module_name!r}")


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "AXES": ("skeleton.context.tensor", "AXES"),
    "ContextTensor": ("skeleton.context.tensor", "ContextTensor"),
    "detect_era": ("skeleton.context.tensor", "detect_era"),
    "Dodecahedron": ("skeleton.context.dodeca", "Dodecahedron"),
    "FACES": ("skeleton.context.dodeca", "FACES"),
    "Magic8Ball": ("skeleton.context.oracle", "Magic8Ball"),
    "OracleReading": ("skeleton.context.oracle", "OracleReading"),
    "Cockpit": ("skeleton.context.cockpit", "Cockpit"),
    "CockpitError": ("skeleton.context.cockpit", "CockpitError"),
    "GameForgeRun": ("skeleton.context.pipeline", "GameForgeRun"),
    "Intake": ("skeleton.context.questionnaire", "Intake"),
    "IntakeResult": ("skeleton.context.questionnaire", "IntakeResult"),
    "Questionnaire": ("skeleton.context.questionnaire", "Questionnaire"),
    "intake": ("skeleton.context.questionnaire", "intake"),
    "BEATS": ("skeleton.context.questionnaire", "BEATS"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(_load_lazy_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


__all__ = [
    "COMPACTION_VERSION",
    "ContextCompactionError",
    "compact_context_segment",
    "COMPILER_VERSION",
    "ContextAdmissionDecision",
    "ContextAllocationPolicy",
    "ContextCompilationError",
    "ContextCompilePolicy",
    "ContextCompiler",
    "ContextPolicyError",
    "ProviderContextProjection",
    "project_provider_context",
    "AXES",
    "ContextTensor",
    "detect_era",
    "Dodecahedron",
    "FACES",
    "Magic8Ball",
    "OracleReading",
    "DNAHelix",
    "BasePair",
    "ContextLedger",
    "LedgerError",
    "INSTRUCTION_POLICY_SCHEMA_VERSION",
    "InstructionPolicy",
    "InstructionPolicyError",
    "InstructionPolicyRegistry",
    "Snowball",
    "SNOWBALL_STAGES",
    "Cockpit",
    "CockpitError",
    "GameForgeRun",
    "Intake",
    "IntakeResult",
    "Questionnaire",
    "intake",
    "BEATS",
    "SkillsFilesError",
    "SkillSpec",
    "TaskState",
    "ContextCard",
    "IterationReport",
    "SkillBank",
    "SkillsContextLoop",
    "mastery_to_skill_file",
]
