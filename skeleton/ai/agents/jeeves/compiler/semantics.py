"""Explicit machine-semantics contracts for Jeeves semantic IR.

The core IR deliberately models broad effects.  This module supplies the next
assurance layer for transformations where broad effect labels are insufficient:

* alias assumptions and memory regions;
* plain/volatile/atomic memory access and ordering;
* integer overflow and divide-by-zero behavior;
* floating-point mode, rounding, NaN and signed-zero behavior;
* nondeterminism source and reproducibility;
* provenance-keyed semantic facts for pass auditing.

The contracts are opt-in at the IR attribute level but a production safety
profile can require them.  Missing semantics fail closed rather than inheriting
Python/C/LLVM folklore implicitly.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence, Tuple

from .decompiler import DecompilationArtifact, Decompiler
from .ir import Effect, IRModule, Instruction, Severity, SourceProvenance


class SemanticContractError(ValueError):
    """Malformed or internally inconsistent instruction semantic contract."""


class MemoryAccessKind(str, Enum):
    PLAIN = "plain"
    VOLATILE = "volatile"
    ATOMIC = "atomic"


class MemoryOrdering(str, Enum):
    RELAXED = "relaxed"
    ACQUIRE = "acquire"
    RELEASE = "release"
    ACQ_REL = "acq_rel"
    SEQ_CST = "seq_cst"


class AliasRelation(str, Enum):
    NO_ALIAS = "no_alias"
    MAY_ALIAS = "may_alias"
    MUST_ALIAS = "must_alias"
    UNKNOWN = "unknown"


class OverflowSemantics(str, Enum):
    MATHEMATICAL = "mathematical"
    WRAP = "wrap"
    SATURATE = "saturate"
    TRAP = "trap"
    POISON = "poison"
    UNDEFINED = "undefined"


class DivisionByZeroSemantics(str, Enum):
    TRAP = "trap"
    POISON = "poison"
    UNDEFINED = "undefined"


class FloatMode(str, Enum):
    STRICT_IEEE = "strict_ieee"
    CONSTRAINED = "constrained"
    FAST_MATH = "fast_math"


class RoundingMode(str, Enum):
    NEAREST_EVEN = "nearest_even"
    TOWARD_ZERO = "toward_zero"
    TOWARD_POSITIVE = "toward_positive"
    TOWARD_NEGATIVE = "toward_negative"
    DYNAMIC = "dynamic"


class NaNSemantics(str, Enum):
    PRESERVE = "preserve"
    CANONICALIZE = "canonicalize"
    ASSUME_ABSENT = "assume_absent"


class NondeterminismKind(str, Enum):
    NONE = "none"
    SEEDED = "seeded"
    EXTERNAL = "external"
    SCHEDULE = "schedule"
    CLOCK = "clock"
    UNKNOWN = "unknown"


def _bounded_text(name: str, value: object, *, allow_empty: bool = False, maximum: int = 512) -> str:
    text = str(value).strip()
    if not text and not allow_empty:
        raise SemanticContractError(f"{name} must be non-empty")
    if len(text) > maximum:
        raise SemanticContractError(f"{name} exceeds {maximum} characters")
    return text


def _mapping(name: str, value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticContractError(f"{name} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise SemanticContractError(f"{name} keys must be strings")
    return value


@dataclass(frozen=True, slots=True)
class MemorySemanticContract:
    region: str
    access: MemoryAccessKind = MemoryAccessKind.PLAIN
    ordering: MemoryOrdering | None = None
    alias: AliasRelation = AliasRelation.UNKNOWN
    synchronization_scope: str = "system"

    def __post_init__(self) -> None:
        object.__setattr__(self, "region", _bounded_text("memory region", self.region))
        if not isinstance(self.access, MemoryAccessKind):
            object.__setattr__(self, "access", MemoryAccessKind(str(self.access)))
        if self.ordering is not None and not isinstance(self.ordering, MemoryOrdering):
            object.__setattr__(self, "ordering", MemoryOrdering(str(self.ordering)))
        if not isinstance(self.alias, AliasRelation):
            object.__setattr__(self, "alias", AliasRelation(str(self.alias)))
        object.__setattr__(
            self, "synchronization_scope", _bounded_text("synchronization_scope", self.synchronization_scope)
        )
        if self.access is MemoryAccessKind.ATOMIC and self.ordering is None:
            raise SemanticContractError("atomic memory access requires ordering")
        if self.access is not MemoryAccessKind.ATOMIC and self.ordering is not None:
            raise SemanticContractError("ordering is only valid for atomic memory access")

    def as_json(self) -> Mapping[str, Any]:
        return {
            "region": self.region,
            "access": self.access.value,
            "ordering": None if self.ordering is None else self.ordering.value,
            "alias": self.alias.value,
            "synchronization_scope": self.synchronization_scope,
        }


@dataclass(frozen=True, slots=True)
class IntegerSemanticContract:
    overflow: OverflowSemantics
    division_by_zero: DivisionByZeroSemantics | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.overflow, OverflowSemantics):
            object.__setattr__(self, "overflow", OverflowSemantics(str(self.overflow)))
        if self.division_by_zero is not None and not isinstance(self.division_by_zero, DivisionByZeroSemantics):
            object.__setattr__(
                self, "division_by_zero", DivisionByZeroSemantics(str(self.division_by_zero))
            )

    def as_json(self) -> Mapping[str, Any]:
        return {
            "overflow": self.overflow.value,
            "division_by_zero": None if self.division_by_zero is None else self.division_by_zero.value,
        }


@dataclass(frozen=True, slots=True)
class FloatSemanticContract:
    mode: FloatMode = FloatMode.STRICT_IEEE
    rounding: RoundingMode = RoundingMode.NEAREST_EVEN
    nan: NaNSemantics = NaNSemantics.PRESERVE
    preserve_signed_zero: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.mode, FloatMode):
            object.__setattr__(self, "mode", FloatMode(str(self.mode)))
        if not isinstance(self.rounding, RoundingMode):
            object.__setattr__(self, "rounding", RoundingMode(str(self.rounding)))
        if not isinstance(self.nan, NaNSemantics):
            object.__setattr__(self, "nan", NaNSemantics(str(self.nan)))
        if not isinstance(self.preserve_signed_zero, bool):
            raise SemanticContractError("preserve_signed_zero must be bool")

    def as_json(self) -> Mapping[str, Any]:
        return {
            "mode": self.mode.value,
            "rounding": self.rounding.value,
            "nan": self.nan.value,
            "preserve_signed_zero": self.preserve_signed_zero,
        }


@dataclass(frozen=True, slots=True)
class NondeterminismContract:
    kind: NondeterminismKind
    source: str = ""
    seed_source: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, NondeterminismKind):
            object.__setattr__(self, "kind", NondeterminismKind(str(self.kind)))
        object.__setattr__(self, "source", _bounded_text("nondeterminism source", self.source, allow_empty=True))
        object.__setattr__(self, "seed_source", _bounded_text("seed_source", self.seed_source, allow_empty=True))
        if self.kind is NondeterminismKind.SEEDED and not self.seed_source:
            raise SemanticContractError("seeded nondeterminism requires seed_source")
        if self.kind in {NondeterminismKind.EXTERNAL, NondeterminismKind.SCHEDULE, NondeterminismKind.CLOCK} and not self.source:
            raise SemanticContractError(f"{self.kind.value} nondeterminism requires source")

    def as_json(self) -> Mapping[str, Any]:
        return {"kind": self.kind.value, "source": self.source, "seed_source": self.seed_source}


@dataclass(frozen=True, slots=True)
class InstructionSemanticContract:
    memory: MemorySemanticContract | None = None
    integer: IntegerSemanticContract | None = None
    floating: FloatSemanticContract | None = None
    nondeterminism: NondeterminismContract | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version <= 0:
            raise SemanticContractError("semantic contract schema_version must be positive integer")

    def as_json(self) -> Mapping[str, Any]:
        return {
            "schema_version": self.schema_version,
            "memory": None if self.memory is None else self.memory.as_json(),
            "integer": None if self.integer is None else self.integer.as_json(),
            "floating": None if self.floating is None else self.floating.as_json(),
            "nondeterminism": None if self.nondeterminism is None else self.nondeterminism.as_json(),
        }

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(self.as_json(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class SemanticContractCodec:
    """Parse the canonical instruction ``semantic_contract`` attribute."""

    ALLOWED_TOP_LEVEL = frozenset({"schema_version", "memory", "integer", "floating", "nondeterminism"})

    @classmethod
    def from_instruction(cls, instruction: Instruction) -> InstructionSemanticContract | None:
        raw = instruction.attributes.get("semantic_contract")
        if raw is None:
            return None
        data = _mapping("semantic_contract", raw)
        unknown = set(data) - cls.ALLOWED_TOP_LEVEL
        if unknown:
            raise SemanticContractError("unknown semantic contract fields: " + ", ".join(sorted(map(str, unknown))))

        memory = None
        if data.get("memory") is not None:
            item = _mapping("semantic_contract.memory", data["memory"])
            allowed = {"region", "access", "ordering", "alias", "synchronization_scope"}
            extra = set(item) - allowed
            if extra:
                raise SemanticContractError("unknown memory contract fields: " + ", ".join(sorted(map(str, extra))))
            if "region" not in item:
                raise SemanticContractError("memory contract requires region")
            access = MemoryAccessKind(str(item.get("access", MemoryAccessKind.PLAIN.value)))
            ordering_raw = item.get("ordering")
            ordering = None if ordering_raw is None else MemoryOrdering(str(ordering_raw))
            memory = MemorySemanticContract(
                region=str(item["region"]),
                access=access,
                ordering=ordering,
                alias=AliasRelation(str(item.get("alias", AliasRelation.UNKNOWN.value))),
                synchronization_scope=str(item.get("synchronization_scope", "system")),
            )

        integer = None
        if data.get("integer") is not None:
            item = _mapping("semantic_contract.integer", data["integer"])
            allowed = {"overflow", "division_by_zero"}
            extra = set(item) - allowed
            if extra:
                raise SemanticContractError("unknown integer contract fields: " + ", ".join(sorted(map(str, extra))))
            if "overflow" not in item:
                raise SemanticContractError("integer contract requires overflow")
            division = item.get("division_by_zero")
            integer = IntegerSemanticContract(
                overflow=OverflowSemantics(str(item["overflow"])),
                division_by_zero=None if division is None else DivisionByZeroSemantics(str(division)),
            )

        floating = None
        if data.get("floating") is not None:
            item = _mapping("semantic_contract.floating", data["floating"])
            allowed = {"mode", "rounding", "nan", "preserve_signed_zero"}
            extra = set(item) - allowed
            if extra:
                raise SemanticContractError("unknown floating contract fields: " + ", ".join(sorted(map(str, extra))))
            floating = FloatSemanticContract(
                mode=FloatMode(str(item.get("mode", FloatMode.STRICT_IEEE.value))),
                rounding=RoundingMode(str(item.get("rounding", RoundingMode.NEAREST_EVEN.value))),
                nan=NaNSemantics(str(item.get("nan", NaNSemantics.PRESERVE.value))),
                preserve_signed_zero=item.get("preserve_signed_zero", True),
            )

        nondeterminism = None
        if data.get("nondeterminism") is not None:
            item = _mapping("semantic_contract.nondeterminism", data["nondeterminism"])
            allowed = {"kind", "source", "seed_source"}
            extra = set(item) - allowed
            if extra:
                raise SemanticContractError("unknown nondeterminism contract fields: " + ", ".join(sorted(map(str, extra))))
            if "kind" not in item:
                raise SemanticContractError("nondeterminism contract requires kind")
            nondeterminism = NondeterminismContract(
                kind=NondeterminismKind(str(item["kind"])),
                source=str(item.get("source", "")),
                seed_source=str(item.get("seed_source", "")),
            )

        return InstructionSemanticContract(
            memory=memory,
            integer=integer,
            floating=floating,
            nondeterminism=nondeterminism,
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True, slots=True)
class SemanticSafetyProfile:
    require_memory_contract: bool = True
    require_integer_contract: bool = True
    require_float_contract: bool = True
    require_nondeterminism_contract: bool = True
    reject_unknown_effect: bool = True
    reject_unknown_alias: bool = True
    reject_undefined_integer_behavior: bool = True
    reject_poison_integer_behavior: bool = False
    reject_fast_math: bool = True
    reject_assume_no_nan: bool = True
    reject_external_nondeterminism: bool = True
    reject_schedule_nondeterminism: bool = True
    reject_clock_nondeterminism: bool = False


@dataclass(frozen=True, slots=True)
class SemanticDiagnostic:
    code: str
    message: str
    severity: Severity
    function: str
    block: str
    instruction_index: int
    opcode: str


@dataclass(frozen=True, slots=True)
class SemanticFact:
    function: str
    block: str
    instruction_index: int
    opcode: str
    provenance_atoms: Tuple[str, ...]
    contract: InstructionSemanticContract

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            {
                "function": self.function,
                "block": self.block,
                "instruction_index": self.instruction_index,
                "opcode": self.opcode,
                "provenance_atoms": list(self.provenance_atoms),
                "contract": self.contract.as_json(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SemanticRiskSurface:
    atomic_accesses: int = 0
    volatile_accesses: int = 0
    unknown_alias_accesses: int = 0
    undefined_integer_ops: int = 0
    poison_integer_ops: int = 0
    fast_math_ops: int = 0
    assume_no_nan_ops: int = 0
    external_nondeterministic_ops: int = 0
    schedule_nondeterministic_ops: int = 0
    unknown_semantics: int = 0

    def as_json(self) -> Mapping[str, int]:
        return {name: int(getattr(self, name)) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class SemanticAuditReport:
    module_fingerprint: str
    semantic_fingerprint: str
    diagnostics: Tuple[SemanticDiagnostic, ...]
    facts: Tuple[SemanticFact, ...]
    risk: SemanticRiskSurface

    @property
    def valid(self) -> bool:
        return not any(item.severity is Severity.ERROR for item in self.diagnostics)


class ModuleSemanticAuditor:
    INTEGER_OVERFLOW_OPS = frozenset({"add", "sub", "mul", "shl", "neg"})
    INTEGER_DIVISION_OPS = frozenset({"div", "floordiv", "mod"})
    FLOAT_OPS = frozenset({"add", "sub", "mul", "div", "neg", "min", "max"})

    def __init__(self, profile: SemanticSafetyProfile | None = None) -> None:
        self.profile = profile or SemanticSafetyProfile()

    @staticmethod
    def _is_integer_instruction(instruction: Instruction) -> bool:
        names = [result.value_type.name.casefold() for result in instruction.results]
        return any(
            name in {"int", "integer"}
            or re.fullmatch(r"[iu][1-9][0-9]*", name) is not None
            for name in names
        )

    @staticmethod
    def _is_float_instruction(instruction: Instruction) -> bool:
        names = [result.value_type.name.casefold() for result in instruction.results]
        return any(
            name in {"float", "double", "half", "bfloat"}
            or re.fullmatch(r"(?:f|bf)[1-9][0-9]*", name) is not None
            for name in names
        )

    @staticmethod
    def _provenance_atoms(provenance: Sequence[SourceProvenance]) -> Tuple[str, ...]:
        atoms = []
        for item in provenance:
            atoms.append(
                f"{item.artifact_id}:{item.start}:{item.end}:"
                + ",".join(item.evidence_ids)
            )
        return tuple(sorted(set(atoms)))

    def audit(self, module: IRModule) -> SemanticAuditReport:
        diagnostics: list[SemanticDiagnostic] = []
        facts: list[SemanticFact] = []
        counters = {name: 0 for name in SemanticRiskSurface.__dataclass_fields__}

        def emit(code: str, message: str, severity: Severity, function: str, block: str, index: int, opcode: str) -> None:
            diagnostics.append(SemanticDiagnostic(code, message, severity, function, block, index, opcode))

        for function in module.functions:
            for block in function.blocks:
                for index, instruction in enumerate(block.instructions):
                    try:
                        contract = SemanticContractCodec.from_instruction(instruction)
                    except (SemanticContractError, ValueError, TypeError) as exc:
                        counters["unknown_semantics"] += 1
                        emit(
                            "SEM.CONTRACT.INVALID",
                            str(exc),
                            Severity.ERROR,
                            function.name,
                            block.label,
                            index,
                            instruction.opcode,
                        )
                        continue

                    has_memory_effect = bool(
                        {Effect.READ_MEMORY, Effect.WRITE_MEMORY}.intersection(instruction.effects)
                    )
                    is_integer = self._is_integer_instruction(instruction) and (
                        instruction.opcode in self.INTEGER_OVERFLOW_OPS | self.INTEGER_DIVISION_OPS
                    )
                    is_float = self._is_float_instruction(instruction) and instruction.opcode in self.FLOAT_OPS
                    is_nondeterministic = Effect.NONDETERMINISTIC in instruction.effects

                    if contract is not None:
                        facts.append(
                            SemanticFact(
                                function.name,
                                block.label,
                                index,
                                instruction.opcode,
                                self._provenance_atoms(instruction.provenance),
                                contract,
                            )
                        )

                    if Effect.UNKNOWN in instruction.effects and self.profile.reject_unknown_effect:
                        counters["unknown_semantics"] += 1
                        emit("SEM.EFFECT.UNKNOWN", "UNKNOWN effect is forbidden by semantic profile", Severity.ERROR, function.name, block.label, index, instruction.opcode)

                    memory = None if contract is None else contract.memory
                    if has_memory_effect and memory is None and self.profile.require_memory_contract:
                        counters["unknown_semantics"] += 1
                        emit("SEM.MEMORY.MISSING", "memory effect lacks explicit semantic contract", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                    if memory is not None:
                        if not has_memory_effect:
                            emit("SEM.MEMORY.HIDDEN", "memory contract exists without READ_MEMORY/WRITE_MEMORY effect", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                        if memory.access is MemoryAccessKind.ATOMIC:
                            counters["atomic_accesses"] += 1
                            reads = Effect.READ_MEMORY in instruction.effects
                            writes = Effect.WRITE_MEMORY in instruction.effects
                            if reads and not writes and memory.ordering in {MemoryOrdering.RELEASE, MemoryOrdering.ACQ_REL}:
                                emit("SEM.ATOMIC.ORDER", "read-only atomic cannot use release/acq_rel ordering", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                            if writes and not reads and memory.ordering in {MemoryOrdering.ACQUIRE, MemoryOrdering.ACQ_REL}:
                                emit("SEM.ATOMIC.ORDER", "write-only atomic cannot use acquire/acq_rel ordering", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                        elif memory.access is MemoryAccessKind.VOLATILE:
                            counters["volatile_accesses"] += 1
                        if memory.alias is AliasRelation.UNKNOWN:
                            counters["unknown_alias_accesses"] += 1
                            if self.profile.reject_unknown_alias:
                                emit("SEM.ALIAS.UNKNOWN", "memory alias relation is unknown", Severity.ERROR, function.name, block.label, index, instruction.opcode)

                    integer = None if contract is None else contract.integer
                    if is_integer and integer is None and self.profile.require_integer_contract:
                        counters["unknown_semantics"] += 1
                        emit("SEM.INTEGER.MISSING", "integer arithmetic lacks overflow/division semantics", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                    if integer is not None:
                        if integer.overflow is OverflowSemantics.UNDEFINED:
                            counters["undefined_integer_ops"] += 1
                            if self.profile.reject_undefined_integer_behavior:
                                emit("SEM.INTEGER.UNDEFINED", "undefined integer overflow is forbidden", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                        if integer.overflow is OverflowSemantics.POISON:
                            counters["poison_integer_ops"] += 1
                            if self.profile.reject_poison_integer_behavior:
                                emit("SEM.INTEGER.POISON", "poison integer overflow is forbidden", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                        if instruction.opcode in self.INTEGER_DIVISION_OPS and integer.division_by_zero is None:
                            emit("SEM.INTEGER.DIVZERO", "division-like operation must define divide-by-zero behavior", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                        if integer.division_by_zero is DivisionByZeroSemantics.UNDEFINED and self.profile.reject_undefined_integer_behavior:
                            emit("SEM.INTEGER.DIVZERO.UNDEFINED", "undefined divide-by-zero is forbidden", Severity.ERROR, function.name, block.label, index, instruction.opcode)

                    floating = None if contract is None else contract.floating
                    if is_float and floating is None and self.profile.require_float_contract:
                        counters["unknown_semantics"] += 1
                        emit("SEM.FLOAT.MISSING", "floating-point operation lacks explicit numerical semantics", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                    if floating is not None:
                        if floating.mode is FloatMode.FAST_MATH:
                            counters["fast_math_ops"] += 1
                            if self.profile.reject_fast_math:
                                emit("SEM.FLOAT.FAST_MATH", "fast-math semantics are forbidden by profile", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                        if floating.nan is NaNSemantics.ASSUME_ABSENT:
                            counters["assume_no_nan_ops"] += 1
                            if self.profile.reject_assume_no_nan:
                                emit("SEM.FLOAT.NO_NAN", "assuming NaNs absent is forbidden by profile", Severity.ERROR, function.name, block.label, index, instruction.opcode)

                    nondet = None if contract is None else contract.nondeterminism
                    if is_nondeterministic and nondet is None and self.profile.require_nondeterminism_contract:
                        counters["unknown_semantics"] += 1
                        emit("SEM.NONDET.MISSING", "nondeterministic effect lacks source/reproducibility contract", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                    if nondet is not None:
                        if not is_nondeterministic and nondet.kind is not NondeterminismKind.NONE:
                            emit("SEM.NONDET.HIDDEN", "nondeterminism contract exists without NONDETERMINISTIC effect", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                        if nondet.kind is NondeterminismKind.EXTERNAL:
                            counters["external_nondeterministic_ops"] += 1
                            if self.profile.reject_external_nondeterminism:
                                emit("SEM.NONDET.EXTERNAL", "external nondeterminism is forbidden by profile", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                        if nondet.kind is NondeterminismKind.SCHEDULE:
                            counters["schedule_nondeterministic_ops"] += 1
                            if self.profile.reject_schedule_nondeterminism:
                                emit("SEM.NONDET.SCHEDULE", "schedule nondeterminism is forbidden by profile", Severity.ERROR, function.name, block.label, index, instruction.opcode)
                        if nondet.kind is NondeterminismKind.CLOCK and self.profile.reject_clock_nondeterminism:
                            emit("SEM.NONDET.CLOCK", "clock nondeterminism is forbidden by profile", Severity.ERROR, function.name, block.label, index, instruction.opcode)

        facts_tuple = tuple(facts)
        semantic_payload = [
            {
                "function": fact.function,
                "block": fact.block,
                "index": fact.instruction_index,
                "opcode": fact.opcode,
                "provenance": fact.provenance_atoms,
                "contract": fact.contract.as_json(),
            }
            for fact in facts_tuple
        ]
        semantic_fingerprint = hashlib.sha256(
            json.dumps(semantic_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return SemanticAuditReport(
            module_fingerprint=module.fingerprint,
            semantic_fingerprint=semantic_fingerprint,
            diagnostics=tuple(diagnostics),
            facts=facts_tuple,
            risk=SemanticRiskSurface(**counters),
        )


@dataclass(frozen=True, slots=True)
class SemanticDecompilationReport:
    artifact: DecompilationArtifact
    source_audit: SemanticAuditReport
    safe_for_reasoning: bool
    reasons: Tuple[str, ...]
    fingerprint: str


class SemanticDecompiler:
    """Decompile while keeping semantic under-specification visible."""

    def __init__(
        self,
        *,
        decompiler: Decompiler | None = None,
        auditor: ModuleSemanticAuditor | None = None,
    ) -> None:
        self.decompiler = decompiler or Decompiler()
        self.auditor = auditor or ModuleSemanticAuditor()

    def decompile(self, module: IRModule) -> SemanticDecompilationReport:
        audit = self.auditor.audit(module)
        artifact = self.decompiler.decompile(module)
        reasons = []
        if not audit.valid:
            reasons.append("source IR has unresolved machine-semantics obligations")
        if not artifact.structurally_valid_source:
            reasons.append("source IR is structurally invalid")
        if artifact.exact_source_recovery_claimed:
            reasons.append("decompiler asserted exact source recovery")
        safe = not reasons
        payload = {
            "artifact": artifact.fingerprint,
            "semantic_audit": audit.semantic_fingerprint,
            "safe": safe,
            "reasons": reasons,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return SemanticDecompilationReport(artifact, audit, safe, tuple(reasons), fingerprint)


def semantic_contract_attributes(contract: InstructionSemanticContract) -> Mapping[str, Any]:
    """Return canonical instruction attributes for an explicit semantic contract."""
    if not isinstance(contract, InstructionSemanticContract):
        raise TypeError("contract must be InstructionSemanticContract")
    return {"semantic_contract": contract.as_json()}