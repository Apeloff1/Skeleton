"""Provider-neutral gameplay composition over canonical mechanics.

This layer binds combat, progression, economy, and AI-behavior specs from
``skeleton.game.mechanics`` into a validated rule set. It does not fork the
mechanics generator and does not own replay execution, presentation,
transport, or scene ownership.

Composition is fail-closed: unknown kinds, dangling references, dependency
cycles, and incompatible mechanic combinations are rejected with diagnostics
rather than coerced. Successful output is ordered deterministically and
fingerprinted so a later replay-evidence harness can consume it.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Optional, Tuple, Union

from skeleton.game.mechanics import (
    AIBehaviorSpec,
    CombatStyle,
    CombatSystemSpec,
    EconomySystemSpec,
    GameMechanicsGenerator,
    MechanicType,
    ProgressionStyle,
    ProgressionSystemSpec,
)
from skeleton.kernel.errors import KernelError

COMPOSITION_CONTRACT_VERSION = "game.composition.v1"
MECHANICS_SURFACE_VERSION = "game.mechanics.v1"

CANONICAL_KIND_ORDER: Tuple[MechanicType, ...] = (
    MechanicType.PROGRESSION,
    MechanicType.ECONOMY,
    MechanicType.COMBAT,
    MechanicType.AI_BEHAVIOR,
)
COMPOSABLE_KINDS = frozenset(CANONICAL_KIND_ORDER)
SINGLETON_KINDS = frozenset(
    {MechanicType.COMBAT, MechanicType.PROGRESSION, MechanicType.ECONOMY}
)
_KIND_RANK = {kind: index for index, kind in enumerate(CANONICAL_KIND_ORDER)}

MAX_COMPONENTS = 16
MAX_AI_COMPONENTS = 8
MAX_COMPONENT_ID_CHARS = 64
MAX_DEPENDENCIES = 8
MAX_EVENTS = 256
MAX_DELTA = 1_000_000
MAX_DIAGNOSTIC_CHARS = 240

_COMPONENT_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

MechanicSpec = Union[
    CombatSystemSpec, ProgressionSystemSpec, EconomySystemSpec, AIBehaviorSpec
]


class GameCompositionError(KernelError):
    """Fail-closed contract violation for gameplay composition."""

    code = "GAME.COMPOSITION"
    http_status = 422


class CompositionEventKind(str, Enum):
    AWARD_XP = "award_xp"
    CREDIT = "credit"
    SPEND = "spend"
    AI_TRANSITION = "ai_transition"


def _bounded_text(name: str, value: object, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GameCompositionError(
            f"{name} must be a non-empty string",
            context={"field": name, "reason": "invalid_identifier"},
        )
    token = value.strip()
    if len(token) > maximum:
        raise GameCompositionError(
            f"{name} is too long",
            context={"field": name, "reason": "too_long", "max_chars": maximum},
        )
    return token


def _bounded_token(name: str, value: object) -> str:
    return _bounded_text(name, value, MAX_COMPONENT_ID_CHARS)


def _component_id(value: object) -> str:
    token = _bounded_token("component_id", value)
    if _COMPONENT_ID_RE.fullmatch(token) is None:
        raise GameCompositionError(
            "component_id must be a lowercase token",
            context={"field": "component_id", "reason": "invalid_identifier", "value": token},
        )
    return token


def _mechanics_version(value: object) -> str:
    token = _bounded_token("version", value)
    if token != MECHANICS_SURFACE_VERSION:
        raise GameCompositionError(
            "unsupported mechanics surface version",
            context={
                "field": "version",
                "reason": "unsupported_version",
                "value": token,
                "expected": MECHANICS_SURFACE_VERSION,
            },
        )
    return token


def _composable_kind(value: object) -> MechanicType:
    if isinstance(value, MechanicType):
        kind = value
    else:
        try:
            kind = MechanicType(value)
        except (TypeError, ValueError) as exc:
            raise GameCompositionError(
                "unknown mechanic kind",
                context={"field": "kind", "reason": "unsupported_kind", "value": value},
            ) from exc
    if kind not in COMPOSABLE_KINDS:
        raise GameCompositionError(
            "mechanic kind is outside the composition contract",
            context={
                "field": "kind",
                "reason": "unsupported_kind",
                "value": kind.value,
                "allowed": tuple(kind.value for kind in CANONICAL_KIND_ORDER),
            },
        )
    return kind


def _spec_matches_kind(kind: MechanicType, spec: object) -> bool:
    expected = {
        MechanicType.COMBAT: CombatSystemSpec,
        MechanicType.PROGRESSION: ProgressionSystemSpec,
        MechanicType.ECONOMY: EconomySystemSpec,
        MechanicType.AI_BEHAVIOR: AIBehaviorSpec,
    }[kind]
    return isinstance(spec, expected)


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise GameCompositionError(
                "non-finite values cannot be canonicalized",
                context={"reason": "invalid_number"},
            )
        return value
    raise GameCompositionError(
        "value is not JSON-canonical",
        context={"reason": "unsupported_type", "type": type(value).__name__},
    )


def _fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        _canonical(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GameCompositionError(
            f"{name} must be an integer",
            context={"field": name, "reason": "invalid_number"},
        )
    if not 1 <= value <= MAX_DELTA:
        raise GameCompositionError(
            f"{name} is outside the accepted range",
            context={"field": name, "reason": "out_of_range", "minimum": 1, "maximum": MAX_DELTA},
        )
    return value


@dataclass(frozen=True)
class CompositionDiagnostic:
    code: str
    message: str
    component_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        code = _bounded_text("diagnostic_code", self.code, MAX_COMPONENT_ID_CHARS)
        message = _bounded_text("diagnostic_message", self.message, MAX_DIAGNOSTIC_CHARS)
        ids = tuple(_component_id(item) for item in self.component_ids)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "component_ids", ids)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "component_ids": list(self.component_ids),
        }


@dataclass(frozen=True)
class MechanicComponentRef:
    component_id: str
    kind: MechanicType
    version: str = MECHANICS_SURFACE_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _component_id(self.component_id))
        object.__setattr__(self, "kind", _composable_kind(self.kind))
        object.__setattr__(self, "version", _mechanics_version(self.version))

    def to_dict(self) -> Dict[str, str]:
        return {
            "component_id": self.component_id,
            "kind": self.kind.value,
            "version": self.version,
        }


@dataclass(frozen=True)
class MechanicComponent:
    ref: MechanicComponentRef
    spec: MechanicSpec
    depends_on: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.ref, MechanicComponentRef):
            raise GameCompositionError("component ref must be MechanicComponentRef")
        if not _spec_matches_kind(self.ref.kind, self.spec):
            raise GameCompositionError(
                "component spec does not match kind",
                context={
                    "reason": "kind_spec_mismatch",
                    "component_id": self.ref.component_id,
                    "kind": self.ref.kind.value,
                    "spec_type": type(self.spec).__name__,
                },
            )
        if not isinstance(self.depends_on, tuple):
            object.__setattr__(self, "depends_on", tuple(self.depends_on))
        if len(self.depends_on) > MAX_DEPENDENCIES:
            raise GameCompositionError(
                "too many dependencies",
                context={"reason": "too_many_dependencies", "maximum": MAX_DEPENDENCIES},
            )
        seen: set[str] = set()
        ordered: List[str] = []
        for dependency in self.depends_on:
            token = _component_id(dependency)
            if token in seen:
                raise GameCompositionError(
                    "dependency references must be unique",
                    context={
                        "reason": "duplicate_dependency",
                        "component_id": self.ref.component_id,
                        "dependency": token,
                    },
                )
            seen.add(token)
            ordered.append(token)
        object.__setattr__(self, "depends_on", tuple(ordered))


@dataclass(frozen=True)
class BoundMechanic:
    ref: MechanicComponentRef
    system: Mapping[str, Any]
    depends_on: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "system", _freeze(self.system))
        object.__setattr__(self, "depends_on", tuple(self.depends_on))


@dataclass(frozen=True)
class CompositionReplayEvidence:
    """Stable envelope for a later replay harness; this is not a replay engine."""

    contract_version: str
    mechanics_version: str
    composition_fingerprint: str
    component_order: Tuple[str, ...]
    component_versions: Tuple[Tuple[str, str], ...]
    kind_order: Tuple[str, ...]
    state_fingerprint: Optional[str] = None
    transition_count: int = 0
    transition_fingerprints: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.contract_version != COMPOSITION_CONTRACT_VERSION:
            raise GameCompositionError(
                "unsupported composition contract version",
                context={"reason": "unsupported_contract_version", "value": self.contract_version},
            )
        if self.mechanics_version != MECHANICS_SURFACE_VERSION:
            raise GameCompositionError(
                "unsupported mechanics surface version",
                context={"reason": "unsupported_version", "value": self.mechanics_version},
            )
        if self.transition_count != len(self.transition_fingerprints):
            raise GameCompositionError(
                "transition evidence is internally inconsistent",
                context={"reason": "replay_evidence_mismatch"},
            )
        object.__setattr__(self, "component_order", tuple(self.component_order))
        object.__setattr__(self, "component_versions", tuple(self.component_versions))
        object.__setattr__(self, "kind_order", tuple(self.kind_order))
        object.__setattr__(self, "transition_fingerprints", tuple(self.transition_fingerprints))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "mechanics_version": self.mechanics_version,
            "composition_fingerprint": self.composition_fingerprint,
            "component_order": list(self.component_order),
            "component_versions": [list(item) for item in self.component_versions],
            "kind_order": list(self.kind_order),
            "state_fingerprint": self.state_fingerprint,
            "transition_count": self.transition_count,
            "transition_fingerprints": list(self.transition_fingerprints),
        }


@dataclass(frozen=True)
class GameplayComposition:
    contract_version: str
    mechanics_version: str
    fingerprint: str
    components: Tuple[BoundMechanic, ...]
    replay_evidence: CompositionReplayEvidence
    systems_by_id: Mapping[str, Mapping[str, Any]] = field(
        init=False, repr=False, default=MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if self.contract_version != COMPOSITION_CONTRACT_VERSION:
            raise GameCompositionError(
                "unsupported composition contract version",
                context={"reason": "unsupported_contract_version", "value": self.contract_version},
            )
        object.__setattr__(self, "components", tuple(self.components))
        by_id = {item.ref.component_id: item.system for item in self.components}
        object.__setattr__(self, "systems_by_id", MappingProxyType(by_id))

    @property
    def order(self) -> Tuple[MechanicComponentRef, ...]:
        return tuple(item.ref for item in self.components)

    def system_for(self, kind: MechanicType) -> Optional[Mapping[str, Any]]:
        for item in self.components:
            if item.ref.kind is kind:
                return item.system
        return None


@dataclass(frozen=True)
class CompositionState:
    tick: int
    xp: int
    level: int
    currency_balances: Mapping[str, int]
    ai_states: Mapping[str, str]
    fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency_balances", MappingProxyType(dict(self.currency_balances)))
        object.__setattr__(self, "ai_states", MappingProxyType(dict(self.ai_states)))


@dataclass(frozen=True)
class CompositionEvent:
    kind: CompositionEventKind
    payload: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CompositionEventKind):
            try:
                object.__setattr__(self, "kind", CompositionEventKind(self.kind))
            except (TypeError, ValueError) as exc:
                raise GameCompositionError(
                    "unknown composition event kind",
                    context={"reason": "unknown_event", "value": self.kind},
                ) from exc
        if not isinstance(self.payload, Mapping):
            raise GameCompositionError(
                "event payload must be a mapping",
                context={"reason": "invalid_payload"},
            )
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


def _reject(diagnostics: Sequence[CompositionDiagnostic]) -> None:
    if not diagnostics:
        return
    unique: List[CompositionDiagnostic] = []
    seen: set[Tuple[str, str, Tuple[str, ...]]] = set()
    for diagnostic in diagnostics:
        key = (diagnostic.code, diagnostic.message, diagnostic.component_ids)
        if key in seen:
            continue
        seen.add(key)
        unique.append(diagnostic)
    raise GameCompositionError(
        "gameplay composition rejected",
        context={
            "diagnostics": [item.to_dict() for item in unique],
            "codes": [item.code for item in unique],
        },
    )


def _note(
    diagnostics: List[CompositionDiagnostic],
    code: str,
    message: str,
    *component_ids: str,
) -> None:
    diagnostics.append(
        CompositionDiagnostic(code=code, message=message, component_ids=tuple(component_ids))
    )


def _validate_members(components: Sequence[MechanicComponent]) -> List[CompositionDiagnostic]:
    diagnostics: List[CompositionDiagnostic] = []
    if not isinstance(components, Sequence) or isinstance(components, (str, bytes)):
        raise GameCompositionError(
            "components must be a sequence",
            context={"reason": "invalid_components"},
        )
    if len(components) == 0:
        _note(diagnostics, "empty_composition", "composition requires at least one mechanic component")
        return diagnostics
    if len(components) > MAX_COMPONENTS:
        _note(
            diagnostics,
            "too_many_components",
            "composition exceeds the component bound",
        )
        return diagnostics
    seen_ids: Dict[str, MechanicComponent] = {}
    seen_kinds: Dict[MechanicType, str] = {}
    seen_entities: Dict[str, str] = {}
    ai_count = 0
    for component in components:
        if not isinstance(component, MechanicComponent):
            raise GameCompositionError(
                "each component must be MechanicComponent",
                context={"reason": "invalid_component_type"},
            )
        component_id = component.ref.component_id
        if component_id in seen_ids:
            _note(
                diagnostics,
                "duplicate_component_id",
                "component ids must be unique",
                seen_ids[component_id].ref.component_id,
                component_id,
            )
        else:
            seen_ids[component_id] = component
        kind = component.ref.kind
        if kind in SINGLETON_KINDS:
            previous = seen_kinds.get(kind)
            if previous is not None:
                _note(
                    diagnostics,
                    "duplicate_kind",
                    f"{kind.value} may appear only once in a composition",
                    previous,
                    component_id,
                )
            else:
                seen_kinds[kind] = component_id
        if kind is MechanicType.AI_BEHAVIOR:
            ai_count += 1
            spec = component.spec
            if not isinstance(spec, AIBehaviorSpec):
                continue
            entity_type = spec.entity_type
            previous_entity = seen_entities.get(entity_type)
            if previous_entity is not None:
                _note(
                    diagnostics,
                    "duplicate_entity_type",
                    "AI entity types must be unique",
                    previous_entity,
                    component_id,
                )
            else:
                seen_entities[entity_type] = component_id
    if ai_count > MAX_AI_COMPONENTS:
        _note(diagnostics, "too_many_ai_components", "too many AI-behavior components")
    return diagnostics


def _semantic_conflicts(components: Sequence[MechanicComponent]) -> List[CompositionDiagnostic]:
    diagnostics: List[CompositionDiagnostic] = []
    by_kind: Dict[MechanicType, List[MechanicComponent]] = {kind: [] for kind in COMPOSABLE_KINDS}
    for component in components:
        by_kind[component.ref.kind].append(component)

    progression = by_kind[MechanicType.PROGRESSION][0] if by_kind[MechanicType.PROGRESSION] else None
    economy = by_kind[MechanicType.ECONOMY][0] if by_kind[MechanicType.ECONOMY] else None
    combat = by_kind[MechanicType.COMBAT][0] if by_kind[MechanicType.COMBAT] else None

    if progression is not None:
        spec = progression.spec
        assert isinstance(spec, ProgressionSystemSpec)
        if spec.style is ProgressionStyle.PRESTIGE and not spec.include_prestige:
            _note(
                diagnostics,
                "conflict_prestige",
                "prestige progression requires include_prestige",
                progression.ref.component_id,
            )
        if spec.style is ProgressionStyle.SKILL_TREE and spec.skill_tree_branches < 1:
            _note(
                diagnostics,
                "conflict_skill_tree",
                "skill-tree progression requires at least one branch",
                progression.ref.component_id,
            )

    if combat is not None:
        spec = combat.spec
        assert isinstance(spec, CombatSystemSpec)
        if spec.party_based and progression is None:
            _note(
                diagnostics,
                "conflict_party_progression",
                "party-based combat requires a progression component",
                combat.ref.component_id,
            )
        if spec.style is CombatStyle.CARD_BASED and spec.party_based:
            _note(
                diagnostics,
                "conflict_card_party",
                "card-based combat cannot be party-based",
                combat.ref.component_id,
            )

    if economy is not None:
        spec = economy.spec
        assert isinstance(spec, EconomySystemSpec)
        if spec.include_crafting:
            if progression is None:
                _note(
                    diagnostics,
                    "conflict_crafting_progression",
                    "crafting economy requires a progression component with skill branches",
                    economy.ref.component_id,
                )
            else:
                progress_spec = progression.spec
                assert isinstance(progress_spec, ProgressionSystemSpec)
                if progress_spec.skill_tree_branches < 1:
                    _note(
                        diagnostics,
                        "conflict_crafting_progression",
                        "crafting economy requires a progression component with skill branches",
                        economy.ref.component_id,
                        progression.ref.component_id,
                    )
    return diagnostics


def _resolve_order(
    components: Sequence[MechanicComponent],
) -> Tuple[Tuple[MechanicComponent, ...], List[CompositionDiagnostic]]:
    diagnostics: List[CompositionDiagnostic] = []
    by_id = {component.ref.component_id: component for component in components}
    indegree = {component.ref.component_id: 0 for component in components}
    dependents: Dict[str, List[str]] = {component.ref.component_id: [] for component in components}

    for component in components:
        for dependency in component.depends_on:
            if dependency == component.ref.component_id:
                _note(
                    diagnostics,
                    "self_dependency",
                    "a component cannot depend on itself",
                    component.ref.component_id,
                )
                continue
            if dependency not in by_id:
                _note(
                    diagnostics,
                    "invalid_dependency",
                    "dependency references an unknown component",
                    component.ref.component_id,
                    dependency,
                )
                continue
            indegree[component.ref.component_id] += 1
            dependents[dependency].append(component.ref.component_id)

    def sort_key(component_id: str) -> Tuple[int, str]:
        component = by_id[component_id]
        return (_KIND_RANK[component.ref.kind], component_id)

    ready = sorted((component_id for component_id, degree in indegree.items() if degree == 0), key=sort_key)
    ordered: List[MechanicComponent] = []
    while ready:
        current_id = ready.pop(0)
        ordered.append(by_id[current_id])
        newly_ready: List[str] = []
        for child in dependents[current_id]:
            indegree[child] -= 1
            if indegree[child] == 0:
                newly_ready.append(child)
        ready.extend(newly_ready)
        ready.sort(key=sort_key)

    if len(ordered) != len(by_id):
        leftover = tuple(sorted(component_id for component_id, degree in indegree.items() if degree > 0))
        _note(
            diagnostics,
            "dependency_cycle",
            "component dependencies form a cycle",
            *leftover,
        )
    return tuple(ordered), diagnostics


def _generate_system(component: MechanicComponent) -> Dict[str, Any]:
    kind = component.ref.kind
    spec = component.spec
    if kind is MechanicType.COMBAT:
        assert isinstance(spec, CombatSystemSpec)
        system = GameMechanicsGenerator.generate_combat_system(spec)
    elif kind is MechanicType.PROGRESSION:
        assert isinstance(spec, ProgressionSystemSpec)
        system = GameMechanicsGenerator.generate_progression_system(spec)
    elif kind is MechanicType.ECONOMY:
        assert isinstance(spec, EconomySystemSpec)
        system = GameMechanicsGenerator.generate_economy_system(spec)
    else:
        assert isinstance(spec, AIBehaviorSpec)
        system = GameMechanicsGenerator.generate_ai_behavior(spec)
    bound = copy.deepcopy(system)
    bound["id"] = f"{kind.value}:{component.ref.component_id}"
    bound["component_id"] = component.ref.component_id
    bound["contract_version"] = component.ref.version
    return bound


def _state_fingerprint(
    *,
    tick: int,
    xp: int,
    level: int,
    currency_balances: Mapping[str, int],
    ai_states: Mapping[str, str],
) -> str:
    return _fingerprint(
        {
            "tick": tick,
            "xp": xp,
            "level": level,
            "currency_balances": dict(currency_balances),
            "ai_states": dict(ai_states),
        }
    )


def _make_state(
    *,
    tick: int,
    xp: int,
    level: int,
    currency_balances: Mapping[str, int],
    ai_states: Mapping[str, str],
) -> CompositionState:
    fingerprint = _state_fingerprint(
        tick=tick,
        xp=xp,
        level=level,
        currency_balances=currency_balances,
        ai_states=ai_states,
    )
    return CompositionState(
        tick=tick,
        xp=xp,
        level=level,
        currency_balances=currency_balances,
        ai_states=ai_states,
        fingerprint=fingerprint,
    )


def _progression_level(system: Mapping[str, Any], xp: int) -> int:
    table = system.get("xp_table")
    if not isinstance(table, (list, tuple)):
        raise GameCompositionError(
            "composed progression is missing an xp table",
            context={"reason": "missing_system"},
        )
    level = 1
    cap = system.get("level_cap", 1)
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise GameCompositionError(
            "composed progression has an invalid level cap",
            context={"reason": "invalid_level_cap"},
        )
    for row in table:
        if not isinstance(row, Mapping):
            raise GameCompositionError(
                "composed progression xp table is invalid",
                context={"reason": "invalid_xp_table"},
            )
        total = row.get("total_xp")
        row_level = row.get("level")
        if isinstance(total, bool) or not isinstance(total, int) or isinstance(row_level, bool) or not isinstance(row_level, int):
            raise GameCompositionError(
                "composed progression xp table is invalid",
                context={"reason": "invalid_xp_table"},
            )
        if xp >= total:
            level = min(row_level + 1, cap)
        else:
            break
    return min(level, cap)


class GameplayComposer:
    """Compose canonical mechanic specs into a deterministic rule set."""

    @staticmethod
    def compose(
        components: Sequence[MechanicComponent],
        *,
        contract_version: str = COMPOSITION_CONTRACT_VERSION,
    ) -> GameplayComposition:
        if contract_version != COMPOSITION_CONTRACT_VERSION:
            raise GameCompositionError(
                "unsupported composition contract version",
                context={"reason": "unsupported_contract_version", "value": contract_version},
            )
        diagnostics = _validate_members(components)
        blocking = {item.code for item in diagnostics} & {
            "empty_composition",
            "too_many_components",
            "duplicate_component_id",
        }
        if not blocking:
            diagnostics.extend(_semantic_conflicts(components))
            ordered, graph_diagnostics = _resolve_order(components)
            diagnostics.extend(graph_diagnostics)
        else:
            ordered = ()
        _reject(diagnostics)

        bound_components: List[BoundMechanic] = []
        for component in ordered:
            bound_components.append(
                BoundMechanic(
                    ref=component.ref,
                    system=_generate_system(component),
                    depends_on=component.depends_on,
                )
            )
        fingerprint = _fingerprint(
            {
                "contract_version": COMPOSITION_CONTRACT_VERSION,
                "mechanics_version": MECHANICS_SURFACE_VERSION,
                "components": [
                    {
                        "ref": item.ref.to_dict(),
                        "depends_on": list(item.depends_on),
                        "system": item.system,
                    }
                    for item in bound_components
                ],
            }
        )
        evidence = CompositionReplayEvidence(
            contract_version=COMPOSITION_CONTRACT_VERSION,
            mechanics_version=MECHANICS_SURFACE_VERSION,
            composition_fingerprint=fingerprint,
            component_order=tuple(item.ref.component_id for item in bound_components),
            component_versions=tuple(
                (item.ref.component_id, item.ref.version) for item in bound_components
            ),
            kind_order=tuple(item.ref.kind.value for item in bound_components),
        )
        return GameplayComposition(
            contract_version=COMPOSITION_CONTRACT_VERSION,
            mechanics_version=MECHANICS_SURFACE_VERSION,
            fingerprint=fingerprint,
            components=tuple(bound_components),
            replay_evidence=evidence,
        )

    @staticmethod
    def initial_state(composition: GameplayComposition) -> CompositionState:
        if not isinstance(composition, GameplayComposition):
            raise GameCompositionError(
                "state transitions require a composed rule set",
                context={"reason": "missing_composition"},
            )
        balances: Dict[str, int] = {}
        economy = composition.system_for(MechanicType.ECONOMY)
        if economy is not None:
            currencies = economy.get("currencies")
            if not isinstance(currencies, Mapping) or not currencies:
                raise GameCompositionError(
                    "composed economy is missing currencies",
                    context={"reason": "missing_system"},
                )
            for name in currencies:
                token = _bounded_token("currency", name)
                balances[token] = 0
        ai_states: Dict[str, str] = {}
        for item in composition.components:
            if item.ref.kind is MechanicType.AI_BEHAVIOR:
                entity = item.system.get("entity_type")
                states = item.system.get("states")
                if not isinstance(entity, str) or not isinstance(states, Mapping) or "idle" not in states:
                    raise GameCompositionError(
                        "composed AI behavior is missing an idle state",
                        context={"reason": "missing_system", "component_id": item.ref.component_id},
                    )
                ai_states[entity] = "idle"
        level = 1 if composition.system_for(MechanicType.PROGRESSION) is not None else 0
        return _make_state(
            tick=0,
            xp=0,
            level=level,
            currency_balances=balances,
            ai_states=ai_states,
        )

    @staticmethod
    def apply_event(
        composition: GameplayComposition,
        state: CompositionState,
        event: CompositionEvent,
    ) -> CompositionState:
        if not isinstance(composition, GameplayComposition):
            raise GameCompositionError(
                "state transitions require a composed rule set",
                context={"reason": "missing_composition"},
            )
        if not isinstance(state, CompositionState):
            raise GameCompositionError(
                "state transitions require CompositionState",
                context={"reason": "invalid_state"},
            )
        if not isinstance(event, CompositionEvent):
            raise GameCompositionError(
                "state transitions require CompositionEvent",
                context={"reason": "unknown_event"},
            )
        expected = _state_fingerprint(
            tick=state.tick,
            xp=state.xp,
            level=state.level,
            currency_balances=state.currency_balances,
            ai_states=state.ai_states,
        )
        if state.fingerprint != expected:
            raise GameCompositionError(
                "composition state fingerprint does not match payload",
                context={"reason": "replay_evidence_mismatch"},
            )

        tick = state.tick + 1
        xp = state.xp
        level = state.level
        balances = dict(state.currency_balances)
        ai_states = dict(state.ai_states)

        if event.kind is CompositionEventKind.AWARD_XP:
            progression = composition.system_for(MechanicType.PROGRESSION)
            if progression is None:
                raise GameCompositionError(
                    "award_xp requires a progression component",
                    context={"reason": "missing_system"},
                )
            amount = _positive_int("amount", event.payload.get("amount"))
            xp = xp + amount
            if xp > MAX_DELTA * 16:
                raise GameCompositionError(
                    "xp overflow",
                    context={"reason": "out_of_range"},
                )
            level = _progression_level(progression, xp)
        elif event.kind is CompositionEventKind.CREDIT:
            currency = _bounded_token("currency", event.payload.get("currency"))
            if currency not in balances:
                raise GameCompositionError(
                    "unknown currency",
                    context={"reason": "unknown_currency", "currency": currency},
                )
            amount = _positive_int("amount", event.payload.get("amount"))
            balances[currency] = balances[currency] + amount
        elif event.kind is CompositionEventKind.SPEND:
            currency = _bounded_token("currency", event.payload.get("currency"))
            if currency not in balances:
                raise GameCompositionError(
                    "unknown currency",
                    context={"reason": "unknown_currency", "currency": currency},
                )
            amount = _positive_int("amount", event.payload.get("amount"))
            if balances[currency] < amount:
                raise GameCompositionError(
                    "insufficient funds",
                    context={"reason": "insufficient_funds", "currency": currency},
                )
            balances[currency] = balances[currency] - amount
        elif event.kind is CompositionEventKind.AI_TRANSITION:
            entity = _bounded_token("entity_type", event.payload.get("entity_type"))
            target = _bounded_token("to_state", event.payload.get("to_state"))
            if entity not in ai_states:
                raise GameCompositionError(
                    "unknown AI entity",
                    context={"reason": "unknown_entity", "entity_type": entity},
                )
            current = ai_states[entity]
            allowed: Optional[Sequence[str]] = None
            for item in composition.components:
                if item.ref.kind is MechanicType.AI_BEHAVIOR and item.system.get("entity_type") == entity:
                    states = item.system.get("states")
                    if isinstance(states, Mapping) and isinstance(states.get(current), Mapping):
                        allowed = states[current].get("transitions")
                    break
            if not isinstance(allowed, (list, tuple)) or target not in allowed:
                raise GameCompositionError(
                    "AI transition is not permitted from the current state",
                    context={
                        "reason": "invalid_transition",
                        "entity_type": entity,
                        "from_state": current,
                        "to_state": target,
                    },
                )
            ai_states[entity] = target
        else:  # pragma: no cover - enum exhaustiveness
            raise GameCompositionError(
                "unknown composition event kind",
                context={"reason": "unknown_event"},
            )

        return _make_state(
            tick=tick,
            xp=xp,
            level=level,
            currency_balances=balances,
            ai_states=ai_states,
        )

    @staticmethod
    def apply_events(
        composition: GameplayComposition,
        events: Sequence[CompositionEvent],
        *,
        state: Optional[CompositionState] = None,
    ) -> Tuple[CompositionState, CompositionReplayEvidence]:
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
            raise GameCompositionError(
                "events must be a sequence",
                context={"reason": "invalid_events"},
            )
        if len(events) > MAX_EVENTS:
            raise GameCompositionError(
                "too many composition events",
                context={"reason": "too_many_events", "maximum": MAX_EVENTS},
            )
        current = state if state is not None else GameplayComposer.initial_state(composition)
        fingerprints: List[str] = []
        for event in events:
            current = GameplayComposer.apply_event(composition, current, event)
            fingerprints.append(current.fingerprint)
        evidence = CompositionReplayEvidence(
            contract_version=composition.contract_version,
            mechanics_version=composition.mechanics_version,
            composition_fingerprint=composition.fingerprint,
            component_order=composition.replay_evidence.component_order,
            component_versions=composition.replay_evidence.component_versions,
            kind_order=composition.replay_evidence.kind_order,
            state_fingerprint=current.fingerprint,
            transition_count=len(fingerprints),
            transition_fingerprints=tuple(fingerprints),
        )
        return current, evidence


def compose_gameplay(
    components: Sequence[MechanicComponent],
    *,
    contract_version: str = COMPOSITION_CONTRACT_VERSION,
) -> GameplayComposition:
    return GameplayComposer.compose(components, contract_version=contract_version)


def initial_composition_state(composition: GameplayComposition) -> CompositionState:
    return GameplayComposer.initial_state(composition)


def apply_composition_events(
    composition: GameplayComposition,
    events: Sequence[CompositionEvent],
    *,
    state: Optional[CompositionState] = None,
) -> Tuple[CompositionState, CompositionReplayEvidence]:
    return GameplayComposer.apply_events(composition, events, state=state)
