"""Bounded formal-method contracts and model checker for VOL-081.

This module intentionally does not claim universal correctness. It turns formal
methods into scoped engineering evidence:

* specifications name assumptions and implementation bindings;
* proof obligations are explicit and consequence-ranked;
* state-space exploration is deterministic and bounded;
* counterexamples are immutable, content-addressed, and replayable;
* a "proved" result always means proved within the declared finite model/bounds.

The checker is provider-neutral and contains no network, filesystem, credential,
or execution authority.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import importlib
import inspect
import itertools
import json
import math
import re
from types import MappingProxyType
from typing import Callable, Iterable, Mapping, Sequence

FORMAL_SCHEMA = "skeleton.contracts.formal-methods.v1"
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_TEXT = 8192
_MAX_DOMAINS = 64
_MAX_DOMAIN_VALUES = 4096
_MAX_BINDINGS = 256
_MAX_ASSUMPTIONS = 256
_MAX_OBLIGATIONS = 512
_MAX_STATES_HARD = 1_000_000
_MAX_TRANSITIONS_HARD = 10_000_000
_MAX_DEPTH_HARD = 100_000

Scalar = str | int | bool | None
Predicate = Callable[["FormalState"], bool]
TransitionPredicate = Callable[["FormalState", "FormalState", str], bool]
TransitionFunction = Callable[["FormalState"], Sequence["TransitionCandidate"]]


class FormalMethodError(RuntimeError):
    """Formal specification, model, traceability, or replay contract failed."""


class ObligationKind(str, Enum):
    INVARIANT = "invariant"
    TRANSITION = "transition"
    REACHABILITY = "reachability"
    DEADLOCK_FREE = "deadlock_free"


class ProofStatus(str, Enum):
    PROVED_WITHIN_MODEL = "proved_within_model"
    REFUTED = "refuted"
    INCONCLUSIVE_BOUND = "inconclusive_bound"


class ExplorationStop(str, Enum):
    COMPLETE = "complete"
    STATE_BOUND = "state_bound"
    TRANSITION_BOUND = "transition_bound"
    DEPTH_BOUND = "depth_bound"


def _token(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise FormalMethodError(f"{field} must be text")
    if value != value.strip() or not value or len(value) > 192:
        raise FormalMethodError(f"{field} must be canonical bounded text")
    if not _TOKEN_RE.fullmatch(value):
        raise FormalMethodError(f"{field} must be a canonical token")
    return value


def _text(value: object, field: str, *, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise FormalMethodError(f"{field} must be text")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise FormalMethodError(f"{field} must be non-empty bounded text")
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in normalized):
        raise FormalMethodError(f"{field} contains control characters")
    return normalized


def _positive_int(value: object, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FormalMethodError(f"{field} must be an integer")
    if not 1 <= value <= maximum:
        raise FormalMethodError(f"{field} must be within [1, {maximum}]")
    return value


def _rank(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise FormalMethodError(f"{field} must be an integer within [1, 5]")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise FormalMethodError(f"{field} must be lowercase sha256")
    return value


def _canonical_json(value: object, field: str = "payload") -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise FormalMethodError(f"{field} must be deterministic JSON") from exc


def _digest(value: object, field: str = "payload") -> str:
    return sha256(_canonical_json(value, field)).hexdigest()


def _normalize_scalar(value: object, field: str) -> Scalar:
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > _MAX_TEXT:
            raise FormalMethodError(f"{field} text is too long")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise FormalMethodError(f"{field} must be finite")
        raise FormalMethodError(
            f"{field} floating values are forbidden; use exact integer/string encoding"
        )
    raise FormalMethodError(
        f"{field} must be a deterministic scalar (str/int/bool/null)"
    )


@dataclass(frozen=True, slots=True)
class FormalState:
    """Canonical immutable finite-model state."""

    values: tuple[tuple[str, Scalar], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.values, tuple):
            raise FormalMethodError("state values must be a tuple")
        seen: set[str] = set()
        normalized: list[tuple[str, Scalar]] = []
        for item in self.values:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
            ):
                raise FormalMethodError("state entries must be (name, value) tuples")
            name = _token(item[0], "state variable")
            if name in seen:
                raise FormalMethodError("duplicate state variable")
            seen.add(name)
            normalized.append(
                (name, _normalize_scalar(item[1], f"state[{name}]"))
            )
        normalized.sort(key=lambda item: item[0])
        object.__setattr__(self, "values", tuple(normalized))

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "FormalState":
        if not isinstance(values, Mapping):
            raise FormalMethodError("state must be a mapping")
        return cls(tuple((str(key), value) for key, value in values.items()))

    def to_mapping(self) -> Mapping[str, Scalar]:
        return MappingProxyType(dict(self.values))

    def get(self, name: str) -> Scalar:
        normalized = _token(name, "state variable")
        for key, value in self.values:
            if key == normalized:
                return value
        raise KeyError(normalized)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "state",
                "values": [[name, value] for name, value in self.values],
            }
        )


@dataclass(frozen=True, slots=True)
class StateVariable:
    name: str
    domain: tuple[Scalar, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _token(self.name, "variable name"))
        if not isinstance(self.domain, tuple) or not self.domain:
            raise FormalMethodError("state-variable domain must be a non-empty tuple")
        if len(self.domain) > _MAX_DOMAIN_VALUES:
            raise FormalMethodError(
                f"state-variable domain exceeds {_MAX_DOMAIN_VALUES} values"
            )
        normalized: list[Scalar] = []
        seen: set[bytes] = set()
        for value in self.domain:
            scalar = _normalize_scalar(value, f"domain[{self.name}]")
            marker = _canonical_json(scalar, f"domain[{self.name}]")
            if marker in seen:
                raise FormalMethodError(
                    f"state-variable domain {self.name} contains duplicate value"
                )
            seen.add(marker)
            normalized.append(scalar)
        normalized.sort(key=lambda item: _canonical_json(item))
        object.__setattr__(self, "domain", tuple(normalized))

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "state-variable",
                "name": self.name,
                "domain": list(self.domain),
            }
        )


@dataclass(frozen=True, slots=True)
class FormalAssumption:
    assumption_id: str
    statement: str
    falsification_condition: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assumption_id",
            _token(self.assumption_id, "assumption_id"),
        )
        object.__setattr__(
            self,
            "statement",
            _text(self.statement, "assumption statement"),
        )
        object.__setattr__(
            self,
            "falsification_condition",
            _text(
                self.falsification_condition,
                "assumption falsification_condition",
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "assumption",
                "assumption_id": self.assumption_id,
                "statement": self.statement,
                "falsification_condition": self.falsification_condition,
            }
        )


@dataclass(frozen=True, slots=True)
class ImplementationBinding:
    """Content-bound link from a formal spec to one implementation symbol."""

    contract_id: str
    module_path: str
    symbol: str
    source_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "contract_id",
            _token(self.contract_id, "contract_id"),
        )
        object.__setattr__(
            self,
            "module_path",
            _token(self.module_path, "module_path"),
        )
        object.__setattr__(
            self,
            "symbol",
            _token(self.symbol, "symbol"),
        )
        object.__setattr__(
            self,
            "source_sha256",
            _sha256(self.source_sha256, "source_sha256"),
        )

    @classmethod
    def from_object(
        cls,
        *,
        contract_id: str,
        obj: object,
        canonical_module_path: str | None = None,
        canonical_symbol: str | None = None,
    ) -> "ImplementationBinding":
        discovered_module = getattr(obj, "__module__", None)
        discovered_symbol = (
            getattr(obj, "__qualname__", None)
            or getattr(obj, "__name__", None)
        )
        if not isinstance(discovered_module, str) or not discovered_module:
            raise FormalMethodError("implementation object has no module")
        if not isinstance(discovered_symbol, str) or not discovered_symbol:
            raise FormalMethodError("implementation object has no symbol name")
        module_path = (
            discovered_module
            if canonical_module_path is None
            else _token(canonical_module_path, "canonical_module_path")
        )
        symbol = (
            discovered_symbol
            if canonical_symbol is None
            else _token(canonical_symbol, "canonical_symbol")
        )
        try:
            source = inspect.getsource(obj)
        except (OSError, TypeError) as exc:
            raise FormalMethodError(
                "implementation source is unavailable for binding"
            ) from exc
        return cls(
            contract_id=contract_id,
            module_path=module_path,
            symbol=symbol,
            source_sha256=sha256(source.encode("utf-8")).hexdigest(),
        )

    def resolve(self) -> object:
        try:
            module = importlib.import_module(self.module_path)
        except Exception as exc:
            raise FormalMethodError(
                f"cannot import implementation module {self.module_path}"
            ) from exc
        current: object = module
        for component in self.symbol.split("."):
            if component == "<locals>":
                raise FormalMethodError(
                    "local implementation symbols cannot be resolved by binding"
                )
            try:
                current = getattr(current, component)
            except AttributeError as exc:
                raise FormalMethodError(
                    f"implementation symbol {self.symbol} is missing"
                ) from exc
        return current

    def verify(self) -> None:
        obj = self.resolve()
        try:
            source = inspect.getsource(obj)
        except (OSError, TypeError) as exc:
            raise FormalMethodError(
                "resolved implementation source is unavailable"
            ) from exc
        actual = sha256(source.encode("utf-8")).hexdigest()
        if actual != self.source_sha256:
            raise FormalMethodError(
                f"implementation binding drift for {self.contract_id}"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "implementation-binding",
                "contract_id": self.contract_id,
                "module_path": self.module_path,
                "symbol": self.symbol,
                "source_sha256": self.source_sha256,
            }
        )


@dataclass(frozen=True, slots=True)
class ProofObligation:
    obligation_id: str
    kind: ObligationKind
    statement: str
    predicate_name: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "obligation_id",
            _token(self.obligation_id, "obligation_id"),
        )
        if not isinstance(self.kind, ObligationKind):
            raise FormalMethodError("kind must be ObligationKind")
        object.__setattr__(
            self,
            "statement",
            _text(self.statement, "obligation statement"),
        )
        if self.kind is ObligationKind.DEADLOCK_FREE:
            if self.predicate_name is not None:
                raise FormalMethodError(
                    "deadlock-free obligation must not define predicate_name"
                )
        else:
            if self.predicate_name is None:
                raise FormalMethodError(
                    f"{self.kind.value} obligation requires predicate_name"
                )
            object.__setattr__(
                self,
                "predicate_name",
                _token(self.predicate_name, "predicate_name"),
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "proof-obligation",
                "obligation_id": self.obligation_id,
                "obligation_kind": self.kind.value,
                "statement": self.statement,
                "predicate_name": self.predicate_name,
            }
        )


@dataclass(frozen=True, slots=True)
class FormalSpecification:
    spec_id: str
    title: str
    consequence_rank: int
    ambiguity_rank: int
    variables: tuple[StateVariable, ...]
    assumptions: tuple[FormalAssumption, ...]
    implementation_bindings: tuple[ImplementationBinding, ...]
    obligations: tuple[ProofObligation, ...]
    initial_predicate_name: str
    transition_relation_name: str
    terminal_predicate_name: str | None = None
    max_states: int = 10_000
    max_transitions: int = 100_000
    max_depth: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(self, "spec_id", _token(self.spec_id, "spec_id"))
        object.__setattr__(self, "title", _text(self.title, "title"))
        object.__setattr__(
            self,
            "consequence_rank",
            _rank(self.consequence_rank, "consequence_rank"),
        )
        object.__setattr__(
            self,
            "ambiguity_rank",
            _rank(self.ambiguity_rank, "ambiguity_rank"),
        )

        if not isinstance(self.variables, tuple) or not self.variables:
            raise FormalMethodError("variables must be a non-empty tuple")
        if len(self.variables) > _MAX_DOMAINS:
            raise FormalMethodError(f"variables exceed {_MAX_DOMAINS}")
        variable_names: set[str] = set()
        for variable in self.variables:
            if not isinstance(variable, StateVariable):
                raise FormalMethodError("variables must contain StateVariable")
            if variable.name in variable_names:
                raise FormalMethodError("duplicate state variable name")
            variable_names.add(variable.name)
        object.__setattr__(
            self,
            "variables",
            tuple(sorted(self.variables, key=lambda item: item.name)),
        )
        theoretical_state_count = 1
        for variable in self.variables:
            theoretical_state_count *= len(variable.domain)
            if theoretical_state_count > _MAX_STATES_HARD:
                raise FormalMethodError(
                    "declared Cartesian state space exceeds hard enumeration bound"
                )

        if not isinstance(self.assumptions, tuple):
            raise FormalMethodError("assumptions must be a tuple")
        if len(self.assumptions) > _MAX_ASSUMPTIONS:
            raise FormalMethodError(f"assumptions exceed {_MAX_ASSUMPTIONS}")
        assumption_ids: set[str] = set()
        for assumption in self.assumptions:
            if not isinstance(assumption, FormalAssumption):
                raise FormalMethodError(
                    "assumptions must contain FormalAssumption"
                )
            if assumption.assumption_id in assumption_ids:
                raise FormalMethodError("duplicate assumption identity")
            assumption_ids.add(assumption.assumption_id)
        object.__setattr__(
            self,
            "assumptions",
            tuple(
                sorted(
                    self.assumptions,
                    key=lambda item: item.assumption_id,
                )
            ),
        )

        if (
            not isinstance(self.implementation_bindings, tuple)
            or not self.implementation_bindings
        ):
            raise FormalMethodError(
                "implementation_bindings must be a non-empty tuple"
            )
        if len(self.implementation_bindings) > _MAX_BINDINGS:
            raise FormalMethodError(
                f"implementation_bindings exceed {_MAX_BINDINGS}"
            )
        binding_ids: set[str] = set()
        for binding in self.implementation_bindings:
            if not isinstance(binding, ImplementationBinding):
                raise FormalMethodError(
                    "implementation_bindings must contain ImplementationBinding"
                )
            if binding.contract_id in binding_ids:
                raise FormalMethodError(
                    "duplicate implementation contract_id"
                )
            binding_ids.add(binding.contract_id)
        object.__setattr__(
            self,
            "implementation_bindings",
            tuple(
                sorted(
                    self.implementation_bindings,
                    key=lambda item: item.contract_id,
                )
            ),
        )

        if not isinstance(self.obligations, tuple) or not self.obligations:
            raise FormalMethodError("obligations must be a non-empty tuple")
        if len(self.obligations) > _MAX_OBLIGATIONS:
            raise FormalMethodError(
                f"obligations exceed {_MAX_OBLIGATIONS}"
            )
        obligation_ids: set[str] = set()
        for obligation in self.obligations:
            if not isinstance(obligation, ProofObligation):
                raise FormalMethodError(
                    "obligations must contain ProofObligation"
                )
            if obligation.obligation_id in obligation_ids:
                raise FormalMethodError(
                    "duplicate proof-obligation identity"
                )
            obligation_ids.add(obligation.obligation_id)
        object.__setattr__(
            self,
            "obligations",
            tuple(
                sorted(
                    self.obligations,
                    key=lambda item: item.obligation_id,
                )
            ),
        )

        object.__setattr__(
            self,
            "initial_predicate_name",
            _token(
                self.initial_predicate_name,
                "initial_predicate_name",
            ),
        )
        object.__setattr__(
            self,
            "transition_relation_name",
            _token(
                self.transition_relation_name,
                "transition_relation_name",
            ),
        )
        if self.terminal_predicate_name is not None:
            object.__setattr__(
                self,
                "terminal_predicate_name",
                _token(
                    self.terminal_predicate_name,
                    "terminal_predicate_name",
                ),
            )

        object.__setattr__(
            self,
            "max_states",
            _positive_int(
                self.max_states,
                "max_states",
                maximum=_MAX_STATES_HARD,
            ),
        )
        object.__setattr__(
            self,
            "max_transitions",
            _positive_int(
                self.max_transitions,
                "max_transitions",
                maximum=_MAX_TRANSITIONS_HARD,
            ),
        )
        object.__setattr__(
            self,
            "max_depth",
            _positive_int(
                self.max_depth,
                "max_depth",
                maximum=_MAX_DEPTH_HARD,
            ),
        )

    @property
    def selection_score(self) -> int:
        """Higher consequence + ambiguity means stronger formal-method priority."""

        return self.consequence_rank * self.ambiguity_rank

    @property
    def theoretical_state_count(self) -> int:
        result = 1
        for variable in self.variables:
            result *= len(variable.domain)
            if result > _MAX_STATES_HARD:
                return result
        return result

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "formal-specification",
                "spec_id": self.spec_id,
                "title": self.title,
                "consequence_rank": self.consequence_rank,
                "ambiguity_rank": self.ambiguity_rank,
                "variables": [item.digest for item in self.variables],
                "assumptions": [item.digest for item in self.assumptions],
                "implementation_bindings": [
                    item.digest for item in self.implementation_bindings
                ],
                "obligations": [item.digest for item in self.obligations],
                "initial_predicate_name": self.initial_predicate_name,
                "transition_relation_name": self.transition_relation_name,
                "terminal_predicate_name": self.terminal_predicate_name,
                "max_states": self.max_states,
                "max_transitions": self.max_transitions,
                "max_depth": self.max_depth,
            }
        )


@dataclass(frozen=True, slots=True)
class TransitionCandidate:
    action: str
    next_state: FormalState

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", _token(self.action, "action"))
        if not isinstance(self.next_state, FormalState):
            raise FormalMethodError("next_state must be FormalState")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "transition-candidate",
                "action": self.action,
                "next_state_digest": self.next_state.digest,
            }
        )


class ModelSemantics:
    """Runtime semantics bound by names recorded in a FormalSpecification."""

    def __init__(
        self,
        *,
        model_id: str,
        initial_predicate_name: str,
        initial_predicate: Predicate,
        transition_relation_name: str,
        transitions: TransitionFunction,
        predicates: Mapping[str, Callable[..., bool]],
        terminal_predicate_name: str | None = None,
        terminal_predicate: Predicate | None = None,
    ) -> None:
        self.model_id = _token(model_id, "model_id")
        self.initial_predicate_name = _token(
            initial_predicate_name,
            "initial_predicate_name",
        )
        self.transition_relation_name = _token(
            transition_relation_name,
            "transition_relation_name",
        )
        if not callable(initial_predicate):
            raise FormalMethodError("initial_predicate must be callable")
        if not callable(transitions):
            raise FormalMethodError("transitions must be callable")
        self.initial_predicate = initial_predicate
        self.transitions = transitions

        if not isinstance(predicates, Mapping):
            raise FormalMethodError("predicates must be a mapping")
        normalized_predicates: dict[str, Callable[..., bool]] = {}
        for name, predicate in predicates.items():
            normalized_name = _token(name, "predicate name")
            if not callable(predicate):
                raise FormalMethodError(
                    f"predicate {normalized_name} must be callable"
                )
            normalized_predicates[normalized_name] = predicate
        self.predicates = MappingProxyType(normalized_predicates)

        if (terminal_predicate_name is None) != (terminal_predicate is None):
            raise FormalMethodError(
                "terminal predicate name and callable must be supplied together"
            )
        self.terminal_predicate_name = (
            None
            if terminal_predicate_name is None
            else _token(
                terminal_predicate_name,
                "terminal_predicate_name",
            )
        )
        if terminal_predicate is not None and not callable(terminal_predicate):
            raise FormalMethodError("terminal_predicate must be callable")
        self.terminal_predicate = terminal_predicate

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "model-semantics",
                "model_id": self.model_id,
                "initial_predicate_name": self.initial_predicate_name,
                "transition_relation_name": self.transition_relation_name,
                "predicate_names": sorted(self.predicates),
                "terminal_predicate_name": self.terminal_predicate_name,
            }
        )


@dataclass(frozen=True, slots=True)
class TraceStep:
    depth: int
    action: str
    before: FormalState
    after: FormalState

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "depth",
            _positive_int(
                self.depth,
                "trace depth",
                maximum=_MAX_DEPTH_HARD,
            ),
        )
        object.__setattr__(self, "action", _token(self.action, "action"))
        if not isinstance(self.before, FormalState):
            raise FormalMethodError("trace before must be FormalState")
        if not isinstance(self.after, FormalState):
            raise FormalMethodError("trace after must be FormalState")

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "trace-step",
                "depth": self.depth,
                "action": self.action,
                "before_digest": self.before.digest,
                "after_digest": self.after.digest,
            }
        )


@dataclass(frozen=True, slots=True)
class Counterexample:
    obligation_id: str
    reason: str
    initial_state: FormalState
    failing_state: FormalState
    trace: tuple[TraceStep, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "obligation_id",
            _token(self.obligation_id, "obligation_id"),
        )
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        if not isinstance(self.initial_state, FormalState):
            raise FormalMethodError("initial_state must be FormalState")
        if not isinstance(self.failing_state, FormalState):
            raise FormalMethodError("failing_state must be FormalState")
        if not isinstance(self.trace, tuple):
            raise FormalMethodError("trace must be a tuple")
        previous = self.initial_state
        for index, step in enumerate(self.trace, start=1):
            if not isinstance(step, TraceStep):
                raise FormalMethodError("trace must contain TraceStep")
            if step.depth != index:
                raise FormalMethodError(
                    "counterexample trace depth must be contiguous"
                )
            if step.before != previous:
                raise FormalMethodError(
                    "counterexample trace is disconnected"
                )
            previous = step.after
        if self.trace and self.trace[-1].after != self.failing_state:
            raise FormalMethodError(
                "counterexample failing_state disagrees with trace"
            )
        if not self.trace and self.initial_state != self.failing_state:
            raise FormalMethodError(
                "zero-step counterexample must fail in initial state"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "counterexample",
                "obligation_id": self.obligation_id,
                "reason": self.reason,
                "initial_state_digest": self.initial_state.digest,
                "failing_state_digest": self.failing_state.digest,
                "trace": [item.digest for item in self.trace],
            }
        )


@dataclass(frozen=True, slots=True)
class ProofResult:
    obligation_id: str
    status: ProofStatus
    explored_states: int
    explored_transitions: int
    counterexample: Counterexample | None = None
    witness_state_digest: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "obligation_id",
            _token(self.obligation_id, "obligation_id"),
        )
        if not isinstance(self.status, ProofStatus):
            raise FormalMethodError("status must be ProofStatus")
        object.__setattr__(
            self,
            "explored_states",
            _positive_int(
                self.explored_states,
                "explored_states",
                maximum=_MAX_STATES_HARD,
            ),
        )
        if (
            isinstance(self.explored_transitions, bool)
            or not isinstance(self.explored_transitions, int)
            or not 0 <= self.explored_transitions <= _MAX_TRANSITIONS_HARD
        ):
            raise FormalMethodError(
                "explored_transitions must be a bounded non-negative integer"
            )
        if self.counterexample is not None:
            if not isinstance(self.counterexample, Counterexample):
                raise FormalMethodError(
                    "counterexample must be Counterexample"
                )
            if self.status is not ProofStatus.REFUTED:
                raise FormalMethodError(
                    "counterexample is valid only for refuted obligations"
                )
            if self.counterexample.obligation_id != self.obligation_id:
                raise FormalMethodError(
                    "counterexample obligation identity mismatch"
                )
        if self.witness_state_digest is not None:
            object.__setattr__(
                self,
                "witness_state_digest",
                _sha256(
                    self.witness_state_digest,
                    "witness_state_digest",
                ),
            )
            if self.status is not ProofStatus.PROVED_WITHIN_MODEL:
                raise FormalMethodError(
                    "witness is valid only for proved obligations"
                )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "proof-result",
                "obligation_id": self.obligation_id,
                "status": self.status.value,
                "explored_states": self.explored_states,
                "explored_transitions": self.explored_transitions,
                "counterexample_digest": (
                    None
                    if self.counterexample is None
                    else self.counterexample.digest
                ),
                "witness_state_digest": self.witness_state_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class FormalRunReport:
    spec_id: str
    spec_digest: str
    semantics_digest: str
    stop_reason: ExplorationStop
    explored_states: int
    explored_transitions: int
    maximum_depth_reached: int
    results: tuple[ProofResult, ...]
    assumptions: tuple[FormalAssumption, ...]
    scope_statement: str = (
        "Results are scoped to the declared finite model, assumptions, "
        "implementation bindings, predicates, and exploration bounds."
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "spec_id", _token(self.spec_id, "spec_id"))
        object.__setattr__(
            self,
            "spec_digest",
            _sha256(self.spec_digest, "spec_digest"),
        )
        object.__setattr__(
            self,
            "semantics_digest",
            _sha256(self.semantics_digest, "semantics_digest"),
        )
        if not isinstance(self.stop_reason, ExplorationStop):
            raise FormalMethodError("stop_reason must be ExplorationStop")
        object.__setattr__(
            self,
            "explored_states",
            _positive_int(
                self.explored_states,
                "explored_states",
                maximum=_MAX_STATES_HARD,
            ),
        )
        if (
            isinstance(self.explored_transitions, bool)
            or not isinstance(self.explored_transitions, int)
            or not 0 <= self.explored_transitions <= _MAX_TRANSITIONS_HARD
        ):
            raise FormalMethodError("invalid explored_transitions")
        if (
            isinstance(self.maximum_depth_reached, bool)
            or not isinstance(self.maximum_depth_reached, int)
            or not 0 <= self.maximum_depth_reached <= _MAX_DEPTH_HARD
        ):
            raise FormalMethodError("invalid maximum_depth_reached")
        if not isinstance(self.results, tuple) or not self.results:
            raise FormalMethodError("results must be a non-empty tuple")
        result_ids: set[str] = set()
        for result in self.results:
            if not isinstance(result, ProofResult):
                raise FormalMethodError("results must contain ProofResult")
            if result.obligation_id in result_ids:
                raise FormalMethodError("duplicate proof-result identity")
            result_ids.add(result.obligation_id)
        if not isinstance(self.assumptions, tuple):
            raise FormalMethodError("assumptions must be a tuple")
        object.__setattr__(
            self,
            "scope_statement",
            _text(self.scope_statement, "scope_statement"),
        )

    @property
    def universally_proves_implementation_correct(self) -> bool:
        return False

    @property
    def all_obligations_proved_within_model(self) -> bool:
        if self.stop_reason is not ExplorationStop.COMPLETE:
            return False
        return all(
            result.status is ProofStatus.PROVED_WITHIN_MODEL
            for result in self.results
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "formal-run-report",
                "spec_id": self.spec_id,
                "spec_digest": self.spec_digest,
                "semantics_digest": self.semantics_digest,
                "stop_reason": self.stop_reason.value,
                "explored_states": self.explored_states,
                "explored_transitions": self.explored_transitions,
                "maximum_depth_reached": self.maximum_depth_reached,
                "results": [item.digest for item in self.results],
                "assumptions": [item.digest for item in self.assumptions],
                "scope_statement": self.scope_statement,
            }
        )


class FormalSpecificationRegistry:
    """Content-addressed formal-spec registry with implementation lookup."""

    def __init__(self) -> None:
        self._specs: dict[str, FormalSpecification] = {}

    def register(self, spec: FormalSpecification) -> FormalSpecification:
        if not isinstance(spec, FormalSpecification):
            raise TypeError("spec must be FormalSpecification")
        existing = self._specs.get(spec.spec_id)
        if existing is not None:
            if existing == spec:
                return existing
            raise FormalMethodError("formal specification identity collision")
        self._specs[spec.spec_id] = spec
        return spec

    def get(self, spec_id: str) -> FormalSpecification:
        normalized = _token(spec_id, "spec_id")
        try:
            return self._specs[normalized]
        except KeyError as exc:
            raise FormalMethodError(
                f"unknown formal specification {normalized}"
            ) from exc

    def for_contract(
        self,
        contract_id: str,
    ) -> tuple[FormalSpecification, ...]:
        normalized = _token(contract_id, "contract_id")
        return tuple(
            sorted(
                (
                    spec
                    for spec in self._specs.values()
                    if any(
                        binding.contract_id == normalized
                        for binding in spec.implementation_bindings
                    )
                ),
                key=lambda item: (
                    -item.selection_score,
                    item.spec_id,
                ),
            )
        )

    def prioritized(self) -> tuple[FormalSpecification, ...]:
        return tuple(
            sorted(
                self._specs.values(),
                key=lambda item: (
                    -item.selection_score,
                    item.spec_id,
                ),
            )
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema": FORMAL_SCHEMA,
                "kind": "formal-specification-registry",
                "specifications": [
                    self._specs[key].digest
                    for key in sorted(self._specs)
                ],
            }
        )


@dataclass(slots=True)
class _Node:
    state: FormalState
    depth: int
    initial_state: FormalState
    trace: tuple[TraceStep, ...]


class BoundedModelChecker:
    """Deterministic exhaustive checker bounded by the specification."""

    @staticmethod
    def _validate_semantics(
        spec: FormalSpecification,
        semantics: ModelSemantics,
    ) -> None:
        if semantics.initial_predicate_name != spec.initial_predicate_name:
            raise FormalMethodError(
                "initial predicate name does not match specification"
            )
        if semantics.transition_relation_name != spec.transition_relation_name:
            raise FormalMethodError(
                "transition relation name does not match specification"
            )
        if semantics.terminal_predicate_name != spec.terminal_predicate_name:
            raise FormalMethodError(
                "terminal predicate name does not match specification"
            )
        for obligation in spec.obligations:
            if obligation.predicate_name is None:
                continue
            if obligation.predicate_name not in semantics.predicates:
                raise FormalMethodError(
                    f"missing predicate {obligation.predicate_name}"
                )

    @staticmethod
    def _validate_state(
        spec: FormalSpecification,
        state: FormalState,
    ) -> None:
        expected = {
            variable.name: variable
            for variable in spec.variables
        }
        actual = state.to_mapping()
        if set(actual) != set(expected):
            raise FormalMethodError(
                "model state variables do not match specification"
            )
        for name, variable in expected.items():
            if actual[name] not in variable.domain:
                raise FormalMethodError(
                    f"state value for {name} escapes declared domain"
                )

    @staticmethod
    def _enumerate_domain(
        spec: FormalSpecification,
    ) -> Iterable[FormalState]:
        variables = spec.variables
        domains = [variable.domain for variable in variables]
        for values in itertools.product(*domains):
            yield FormalState(
                tuple(
                    (variable.name, value)
                    for variable, value in zip(variables, values)
                )
            )

    @staticmethod
    def _bool_result(
        *,
        name: str,
        callback: Callable[..., bool],
        args: tuple[object, ...],
    ) -> bool:
        try:
            result = callback(*args)
        except Exception as exc:
            raise FormalMethodError(
                f"model predicate {name} raised an exception"
            ) from exc
        if not isinstance(result, bool):
            raise FormalMethodError(
                f"model predicate {name} must return bool"
            )
        return result

    @staticmethod
    def _terminal(
        spec: FormalSpecification,
        semantics: ModelSemantics,
        state: FormalState,
    ) -> bool:
        if spec.terminal_predicate_name is None:
            return False
        assert semantics.terminal_predicate is not None
        return BoundedModelChecker._bool_result(
            name=spec.terminal_predicate_name,
            callback=semantics.terminal_predicate,
            args=(state,),
        )

    @staticmethod
    def _counterexample(
        obligation: ProofObligation,
        node: _Node,
        reason: str,
    ) -> Counterexample:
        return Counterexample(
            obligation_id=obligation.obligation_id,
            reason=reason,
            initial_state=node.initial_state,
            failing_state=node.state,
            trace=node.trace,
        )

    def check(
        self,
        spec: FormalSpecification,
        semantics: ModelSemantics,
        *,
        verify_implementation_bindings: bool = True,
    ) -> FormalRunReport:
        if not isinstance(spec, FormalSpecification):
            raise TypeError("spec must be FormalSpecification")
        if not isinstance(semantics, ModelSemantics):
            raise TypeError("semantics must be ModelSemantics")
        self._validate_semantics(spec, semantics)

        if verify_implementation_bindings:
            for binding in spec.implementation_bindings:
                binding.verify()

        initial_states: list[FormalState] = []
        for state in self._enumerate_domain(spec):
            self._validate_state(spec, state)
            if self._bool_result(
                name=spec.initial_predicate_name,
                callback=semantics.initial_predicate,
                args=(state,),
            ):
                initial_states.append(state)
        if not initial_states:
            raise FormalMethodError(
                "formal model has no state satisfying initial predicate"
            )
        if len(initial_states) > spec.max_states:
            raise FormalMethodError(
                "initial-state set already exceeds max_states"
            )
        initial_states.sort(key=lambda item: item.digest)

        queue: deque[_Node] = deque(
            _Node(
                state=state,
                depth=0,
                initial_state=state,
                trace=(),
            )
            for state in initial_states
        )
        visited: dict[str, _Node] = {
            node.state.digest: node
            for node in queue
        }
        transition_count = 0
        maximum_depth = 0
        stop_reason = ExplorationStop.COMPLETE

        obligations = {
            item.obligation_id: item
            for item in spec.obligations
        }
        counterexamples: dict[str, Counterexample] = {}
        reachability_witnesses: dict[str, str] = {}

        while queue:
            node = queue.popleft()
            maximum_depth = max(maximum_depth, node.depth)

            for obligation in spec.obligations:
                if obligation.obligation_id in counterexamples:
                    continue
                if obligation.kind is ObligationKind.INVARIANT:
                    predicate = semantics.predicates[obligation.predicate_name or ""]
                    holds = self._bool_result(
                        name=obligation.predicate_name or "",
                        callback=predicate,
                        args=(node.state,),
                    )
                    if not holds:
                        counterexamples[obligation.obligation_id] = (
                            self._counterexample(
                                obligation,
                                node,
                                "state invariant is false",
                            )
                        )
                elif obligation.kind is ObligationKind.REACHABILITY:
                    if obligation.obligation_id in reachability_witnesses:
                        continue
                    predicate = semantics.predicates[obligation.predicate_name or ""]
                    reached = self._bool_result(
                        name=obligation.predicate_name or "",
                        callback=predicate,
                        args=(node.state,),
                    )
                    if reached:
                        reachability_witnesses[
                            obligation.obligation_id
                        ] = node.state.digest

            terminal = self._terminal(spec, semantics, node.state)
            if node.depth >= spec.max_depth:
                if not terminal:
                    stop_reason = ExplorationStop.DEPTH_BOUND
                continue
            if terminal:
                continue

            try:
                raw_transitions = semantics.transitions(node.state)
            except Exception as exc:
                raise FormalMethodError(
                    "transition relation raised an exception"
                ) from exc
            if isinstance(raw_transitions, (str, bytes)) or not isinstance(
                raw_transitions,
                Sequence,
            ):
                raise FormalMethodError(
                    "transition relation must return a finite sequence"
                )
            candidates = tuple(raw_transitions)
            for candidate in candidates:
                if not isinstance(candidate, TransitionCandidate):
                    raise FormalMethodError(
                        "transition relation must return TransitionCandidate"
                    )
                self._validate_state(spec, candidate.next_state)
            candidates = tuple(
                sorted(
                    candidates,
                    key=lambda item: (
                        item.action,
                        item.next_state.digest,
                    ),
                )
            )
            pair_ids: set[tuple[str, str]] = set()
            for candidate in candidates:
                pair = (candidate.action, candidate.next_state.digest)
                if pair in pair_ids:
                    raise FormalMethodError(
                        "transition relation returned duplicate transition"
                    )
                pair_ids.add(pair)

            if not candidates:
                for obligation in spec.obligations:
                    if (
                        obligation.kind is ObligationKind.DEADLOCK_FREE
                        and obligation.obligation_id not in counterexamples
                    ):
                        counterexamples[obligation.obligation_id] = (
                            self._counterexample(
                                obligation,
                                node,
                                "non-terminal state has no outgoing transition",
                            )
                        )
                continue

            for candidate in candidates:
                if transition_count >= spec.max_transitions:
                    stop_reason = ExplorationStop.TRANSITION_BOUND
                    queue.clear()
                    break
                transition_count += 1

                step = TraceStep(
                    depth=node.depth + 1,
                    action=candidate.action,
                    before=node.state,
                    after=candidate.next_state,
                )
                child = _Node(
                    state=candidate.next_state,
                    depth=node.depth + 1,
                    initial_state=node.initial_state,
                    trace=node.trace + (step,),
                )

                for obligation in spec.obligations:
                    if (
                        obligation.kind is ObligationKind.TRANSITION
                        and obligation.obligation_id not in counterexamples
                    ):
                        predicate = semantics.predicates[
                            obligation.predicate_name or ""
                        ]
                        holds = self._bool_result(
                            name=obligation.predicate_name or "",
                            callback=predicate,
                            args=(
                                node.state,
                                candidate.next_state,
                                candidate.action,
                            ),
                        )
                        if not holds:
                            counterexamples[obligation.obligation_id] = (
                                Counterexample(
                                    obligation_id=obligation.obligation_id,
                                    reason="transition predicate is false",
                                    initial_state=node.initial_state,
                                    failing_state=candidate.next_state,
                                    trace=child.trace,
                                )
                            )

                child_digest = candidate.next_state.digest
                if child_digest in visited:
                    continue
                if len(visited) >= spec.max_states:
                    if stop_reason is ExplorationStop.COMPLETE:
                        stop_reason = ExplorationStop.STATE_BOUND
                    continue
                visited[child_digest] = child
                queue.append(child)

        complete = stop_reason is ExplorationStop.COMPLETE
        results: list[ProofResult] = []
        explored_states = len(visited)

        for obligation in spec.obligations:
            counterexample = counterexamples.get(obligation.obligation_id)
            if counterexample is not None:
                status = ProofStatus.REFUTED
                witness = None
            elif obligation.kind is ObligationKind.REACHABILITY:
                witness = reachability_witnesses.get(obligation.obligation_id)
                if witness is not None:
                    status = ProofStatus.PROVED_WITHIN_MODEL
                elif complete:
                    status = ProofStatus.REFUTED
                    first = initial_states[0]
                    counterexample = Counterexample(
                        obligation_id=obligation.obligation_id,
                        reason=(
                            "reachability predicate was false in every "
                            "reachable state of the complete bounded model"
                        ),
                        initial_state=first,
                        failing_state=first,
                        trace=(),
                    )
                else:
                    status = ProofStatus.INCONCLUSIVE_BOUND
            elif complete:
                status = ProofStatus.PROVED_WITHIN_MODEL
                witness = None
            else:
                status = ProofStatus.INCONCLUSIVE_BOUND
                witness = None

            results.append(
                ProofResult(
                    obligation_id=obligation.obligation_id,
                    status=status,
                    explored_states=explored_states,
                    explored_transitions=transition_count,
                    counterexample=counterexample,
                    witness_state_digest=witness,
                )
            )

        return FormalRunReport(
            spec_id=spec.spec_id,
            spec_digest=spec.digest,
            semantics_digest=semantics.digest,
            stop_reason=stop_reason,
            explored_states=explored_states,
            explored_transitions=transition_count,
            maximum_depth_reached=maximum_depth,
            results=tuple(
                sorted(
                    results,
                    key=lambda item: item.obligation_id,
                )
            ),
            assumptions=spec.assumptions,
        )

    def replay_counterexample(
        self,
        spec: FormalSpecification,
        semantics: ModelSemantics,
        counterexample: Counterexample,
    ) -> None:
        """Fail closed unless every recorded counterexample step still exists."""

        if not isinstance(spec, FormalSpecification):
            raise TypeError("spec must be FormalSpecification")
        if not isinstance(semantics, ModelSemantics):
            raise TypeError("semantics must be ModelSemantics")
        if not isinstance(counterexample, Counterexample):
            raise TypeError("counterexample must be Counterexample")
        self._validate_semantics(spec, semantics)
        self._validate_state(spec, counterexample.initial_state)
        if not self._bool_result(
            name=spec.initial_predicate_name,
            callback=semantics.initial_predicate,
            args=(counterexample.initial_state,),
        ):
            raise FormalMethodError(
                "counterexample no longer starts from an initial state"
            )

        current = counterexample.initial_state
        for step in counterexample.trace:
            if step.before != current:
                raise FormalMethodError("counterexample replay trace disconnected")
            raw = semantics.transitions(current)
            if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
                raise FormalMethodError(
                    "transition relation must return a finite sequence"
                )
            matches = tuple(
                candidate
                for candidate in raw
                if isinstance(candidate, TransitionCandidate)
                and candidate.action == step.action
                and candidate.next_state == step.after
            )
            if len(matches) != 1:
                raise FormalMethodError(
                    "counterexample transition no longer replays uniquely"
                )
            current = step.after

        if current != counterexample.failing_state:
            raise FormalMethodError(
                "counterexample replay does not reach failing_state"
            )


__all__ = [
    "FORMAL_SCHEMA",
    "BoundedModelChecker",
    "Counterexample",
    "ExplorationStop",
    "FormalAssumption",
    "FormalMethodError",
    "FormalRunReport",
    "FormalSpecification",
    "FormalSpecificationRegistry",
    "FormalState",
    "ImplementationBinding",
    "ModelSemantics",
    "ObligationKind",
    "ProofObligation",
    "ProofResult",
    "ProofStatus",
    "StateVariable",
    "TraceStep",
    "TransitionCandidate",
]
