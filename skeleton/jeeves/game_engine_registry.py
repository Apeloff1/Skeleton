"""Unified Jeeves registry for every executable game-engine era.

The family modules intentionally keep historically distinct runtime mechanics.
This module supplies the common control plane Jeeves needs: one era registry,
one snapshot lineage, one patch boundary, one adversarial promotion contract,
and a deterministic quality matrix across the entire Pong-to-next ladder.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Iterable

from .game_engine_3d import (
    THREE_D_ERAS,
    ThreeDEngineAdversary,
    build_3d_engine_tree,
    create_3d_machine_from_tree,
)
from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    QualityReport,
    SandboxPatch,
    SandboxSnapshot,
    VirtualFileTree,
    engine_era_profile,
)
from .game_engine_legacy import (
    LEGACY_ERAS,
    LegacyEngineAdversary,
    build_legacy_engine_tree,
    create_legacy_machine_from_tree,
)
from .game_engine_modern import (
    MODERN_ERAS,
    ModernEngineAdversary,
    build_modern_engine_tree,
    create_modern_machine_from_tree,
)


class EngineFamily(str, Enum):
    LEGACY_2D = "legacy_2d"
    TRANSITION_3D = "transition_3d"
    MODERN = "modern"


ERA_FAMILY = {
    **{era: EngineFamily.LEGACY_2D for era in LEGACY_ERAS},
    **{era: EngineFamily.TRANSITION_3D for era in THREE_D_ERAS},
    **{era: EngineFamily.MODERN for era in MODERN_ERAS},
}

if set(ERA_FAMILY) != set(EngineEra):
    raise RuntimeError("engine registry must cover every EngineEra exactly once")


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def engine_family(era: EngineEra | str) -> EngineFamily:
    try:
        key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    except ValueError as exc:
        raise GameEngineLabError(f"unknown engine era: {era!r}") from exc
    return ERA_FAMILY[key]


def build_executable_engine_tree(
    era: EngineEra | str,
    gameplay_dialect: str | None = None,
) -> VirtualFileTree:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    family = engine_family(key)
    if family is EngineFamily.LEGACY_2D:
        return build_legacy_engine_tree(key, gameplay_dialect)
    if family is EngineFamily.TRANSITION_3D:
        return build_3d_engine_tree(key, gameplay_dialect)
    return build_modern_engine_tree(key, gameplay_dialect)


def create_executable_machine(
    era: EngineEra | str,
    tree: VirtualFileTree,
):
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    family = engine_family(key)
    if family is EngineFamily.LEGACY_2D:
        return create_legacy_machine_from_tree(key, tree)
    if family is EngineFamily.TRANSITION_3D:
        return create_3d_machine_from_tree(key, tree)
    return create_modern_machine_from_tree(key, tree)


@dataclass(frozen=True, slots=True)
class UnifiedProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class UnifiedQualityReport:
    era: EngineEra
    family: EngineFamily
    tree_digest: str
    score: float
    passed: bool
    failed: tuple[str, ...]
    probes: tuple[UnifiedProbe, ...]


def _coerce_quality(
    era: EngineEra,
    family: EngineFamily,
    tree: VirtualFileTree,
    report,
) -> UnifiedQualityReport:
    probes = tuple(
        UnifiedProbe(
            str(probe.name),
            bool(probe.passed),
            str(probe.detail),
        )
        for probe in report.probes
    )
    return UnifiedQualityReport(
        era=era,
        family=family,
        tree_digest=tree.digest,
        score=float(report.score),
        passed=bool(report.passed),
        failed=tuple(str(item) for item in report.failed),
        probes=probes,
    )


def evaluate_executable_engine(
    era: EngineEra | str,
    tree: VirtualFileTree,
) -> UnifiedQualityReport:
    key = era if isinstance(era, EngineEra) else EngineEra(str(era))
    family = engine_family(key)
    if family is EngineFamily.LEGACY_2D:
        report = LegacyEngineAdversary().evaluate(key, tree)
    elif family is EngineFamily.TRANSITION_3D:
        report = ThreeDEngineAdversary().evaluate(key, tree)
    else:
        report = ModernEngineAdversary().evaluate(key, tree)
    return _coerce_quality(key, family, tree, report)


@dataclass(frozen=True, slots=True)
class ManagedEngineSandbox:
    era: EngineEra
    family: EngineFamily
    tree: VirtualFileTree
    gameplay_dialect: str | None = None
    sequence: int = 0
    snapshots: tuple[SandboxSnapshot, ...] = ()

    def snapshot(self) -> "ManagedEngineSandbox":
        parent = self.snapshots[-1].tree_digest if self.snapshots else None
        snap = self.tree.snapshot(self.era, self.sequence, parent)
        return replace(
            self,
            sequence=self.sequence + 1,
            snapshots=self.snapshots + (snap,),
        )

    def restore(self, index: int = -1) -> "ManagedEngineSandbox":
        if not self.snapshots:
            raise GameEngineLabError("managed sandbox has no snapshots")
        try:
            snapshot = self.snapshots[index]
        except IndexError as exc:
            raise GameEngineLabError("snapshot index out of range") from exc
        if snapshot.era is not self.era:
            raise GameEngineLabError("snapshot era mismatch")
        return replace(
            self,
            tree=VirtualFileTree.restore(snapshot),
            sequence=snapshot.sequence + 1,
        )

    def apply(self, patches: Iterable[SandboxPatch]) -> "ManagedEngineSandbox":
        return replace(self, tree=self.tree.apply(patches))

    def machine(self):
        return create_executable_machine(self.era, self.tree)


@dataclass(frozen=True, slots=True)
class RegistryImprovementRound:
    index: int
    before_digest: str
    candidate_digest: str
    before_score: float
    candidate_score: float
    accepted: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegistryImprovementResult:
    sandbox: ManagedEngineSandbox
    report: UnifiedQualityReport
    rounds: tuple[RegistryImprovementRound, ...]
    promoted: bool


RegistryImprover = Callable[
    [ManagedEngineSandbox, UnifiedQualityReport],
    Iterable[SandboxPatch],
]


@dataclass(frozen=True, slots=True)
class EngineMatrixEntry:
    era: EngineEra
    family: EngineFamily
    start_year: int
    tree_digest: str
    score: float
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EngineQualityMatrix:
    entries: tuple[EngineMatrixEntry, ...]
    digest: str

    @property
    def all_passed(self) -> bool:
        return bool(self.entries) and all(entry.passed for entry in self.entries)

    @property
    def minimum_score(self) -> float:
        if not self.entries:
            return 0.0
        return min(entry.score for entry in self.entries)


@dataclass(frozen=True, slots=True)
class AttackResult:
    name: str
    detected: bool
    recovered: bool
    before_score: float
    attacked_score: float
    final_score: float
    final_digest: str


@dataclass(frozen=True, slots=True)
class TournamentReport:
    era: EngineEra
    baseline_digest: str
    baseline_score: float
    attacks: tuple[AttackResult, ...]
    digest: str

    @property
    def passed(self) -> bool:
        return bool(self.attacks) and all(
            attack.detected and attack.recovered
            for attack in self.attacks
        )


class JeevesGameEngineRegistry:
    """Pong-to-next sandbox orchestration and adversarial promotion plane."""

    def create(
        self,
        era: EngineEra | str,
        gameplay_dialect: str | None = None,
    ) -> ManagedEngineSandbox:
        key = era if isinstance(era, EngineEra) else EngineEra(str(era))
        tree = build_executable_engine_tree(key, gameplay_dialect)
        return ManagedEngineSandbox(
            era=key,
            family=engine_family(key),
            tree=tree,
            gameplay_dialect=gameplay_dialect,
        ).snapshot()

    def evaluate(
        self,
        sandbox: ManagedEngineSandbox,
    ) -> UnifiedQualityReport:
        expected = engine_family(sandbox.era)
        if sandbox.family is not expected:
            raise GameEngineLabError("managed sandbox family mismatch")
        return evaluate_executable_engine(sandbox.era, sandbox.tree)

    def canonical_repair(
        self,
        sandbox: ManagedEngineSandbox,
        report: UnifiedQualityReport,
    ) -> tuple[SandboxPatch, ...]:
        if report.passed:
            return ()
        canonical = build_executable_engine_tree(
            sandbox.era,
            sandbox.gameplay_dialect,
        )
        current_paths = set(sandbox.tree.files)
        canonical_paths = set(canonical.files)
        candidate_paths = sorted(current_paths | canonical_paths)
        patches: list[SandboxPatch] = []
        for path in candidate_paths:
            wanted = canonical.files.get(path)
            current = sandbox.tree.files.get(path)
            if current == wanted:
                continue
            # Only canonical engine-owned paths are repaired/deleted. A caller's
            # unrelated project content is deliberately left untouched.
            if path not in canonical_paths:
                continue
            patches.append(
                SandboxPatch(
                    path,
                    wanted,
                    sandbox.tree.file_digest(path),
                )
            )
        return tuple(patches)

    def adversarial_improve(
        self,
        sandbox: ManagedEngineSandbox,
        *,
        target: float = 1.0,
        max_rounds: int = 8,
        improver: RegistryImprover | None = None,
    ) -> RegistryImprovementResult:
        if not 0 < target <= 1:
            raise GameEngineLabError("target must be within (0, 1]")
        if not isinstance(max_rounds, int) or not 1 <= max_rounds <= 64:
            raise GameEngineLabError("max_rounds must be within [1, 64]")
        current = sandbox
        report = self.evaluate(current)
        rounds: list[RegistryImprovementRound] = []
        if report.passed and report.score >= target:
            return RegistryImprovementResult(current, report, (), True)
        strategy = improver or self.canonical_repair
        for index in range(1, max_rounds + 1):
            patches = tuple(strategy(current, report))
            if not patches:
                break
            candidate = current.apply(patches)
            next_report = self.evaluate(candidate)
            accepted = (
                candidate.tree.digest != current.tree.digest
                and next_report.score >= report.score
                and len(next_report.failed) <= len(report.failed)
            )
            rounds.append(
                RegistryImprovementRound(
                    index=index,
                    before_digest=current.tree.digest,
                    candidate_digest=candidate.tree.digest,
                    before_score=report.score,
                    candidate_score=next_report.score,
                    accepted=accepted,
                    failures=next_report.failed,
                )
            )
            if not accepted:
                break
            current = candidate.snapshot()
            report = next_report
            if report.passed and report.score >= target:
                break
        return RegistryImprovementResult(
            current,
            report,
            tuple(rounds),
            report.passed and report.score >= target,
        )

    def quality_matrix(
        self,
        gameplay_dialect: str | None = None,
    ) -> EngineQualityMatrix:
        entries: list[EngineMatrixEntry] = []
        for era in EngineEra:
            sandbox = self.create(era, gameplay_dialect)
            report = self.evaluate(sandbox)
            profile = engine_era_profile(era)
            entries.append(
                EngineMatrixEntry(
                    era=era,
                    family=sandbox.family,
                    start_year=profile.start_year,
                    tree_digest=sandbox.tree.digest,
                    score=report.score,
                    passed=report.passed,
                    failures=report.failed,
                )
            )
        payload = [
            (
                entry.era.value,
                entry.family.value,
                entry.start_year,
                entry.tree_digest,
                entry.score,
                entry.passed,
                entry.failures,
            )
            for entry in entries
        ]
        return EngineQualityMatrix(tuple(entries), _digest(payload))

    def tuning_attack(
        self,
        sandbox: ManagedEngineSandbox,
    ) -> ManagedEngineSandbox:
        family = sandbox.family
        if family is EngineFamily.LEGACY_2D:
            path = "engine/legacy_tuning.json"
        elif family is EngineFamily.TRANSITION_3D:
            path = "engine/3d_tuning.json"
        else:
            path = "engine/modern_tuning.json"
        payload = json.loads(sandbox.tree.read(path))
        if not isinstance(payload, dict) or not payload:
            raise GameEngineLabError("tuning attack requires object tuning")
        first = sorted(payload)[0]
        payload[first] = 10**9
        return sandbox.apply(
            (
                SandboxPatch(
                    path,
                    json.dumps(payload, sort_keys=True),
                    sandbox.tree.file_digest(path),
                ),
            )
        )

    def contract_delete_attack(
        self,
        sandbox: ManagedEngineSandbox,
    ) -> ManagedEngineSandbox:
        if sandbox.family is EngineFamily.LEGACY_2D:
            path = "engine/legacy_runtime.py"
        elif sandbox.family is EngineFamily.TRANSITION_3D:
            path = "engine/3d_runtime.py"
        else:
            path = "engine/modern_runtime.py"
        return sandbox.apply(
            (
                SandboxPatch(
                    path,
                    None,
                    sandbox.tree.file_digest(path),
                ),
            )
        )

    def adversarial_tournament(
        self,
        era: EngineEra | str,
        gameplay_dialect: str | None = None,
    ) -> TournamentReport:
        baseline = self.create(era, gameplay_dialect)
        baseline_report = self.evaluate(baseline)
        if not baseline_report.passed:
            raise GameEngineLabError("canonical engine must pass before tournament")
        attacks: list[AttackResult] = []
        for name, attack in (
            ("tuning_overflow", self.tuning_attack),
            ("contract_delete", self.contract_delete_attack),
        ):
            attacked = attack(baseline)
            attacked_report = self.evaluate(attacked)
            result = self.adversarial_improve(attacked)
            attacks.append(
                AttackResult(
                    name=name,
                    detected=not attacked_report.passed,
                    recovered=result.promoted and result.report.passed,
                    before_score=baseline_report.score,
                    attacked_score=attacked_report.score,
                    final_score=result.report.score,
                    final_digest=result.sandbox.tree.digest,
                )
            )
        payload = {
            "era": baseline.era.value,
            "baseline": baseline.tree.digest,
            "attacks": [
                (
                    attack.name,
                    attack.detected,
                    attack.recovered,
                    attack.before_score,
                    attack.attacked_score,
                    attack.final_score,
                    attack.final_digest,
                )
                for attack in attacks
            ],
        }
        return TournamentReport(
            era=baseline.era,
            baseline_digest=baseline.tree.digest,
            baseline_score=baseline_report.score,
            attacks=tuple(attacks),
            digest=_digest(payload),
        )


def build_jeeves_engine_registry() -> JeevesGameEngineRegistry:
    return JeevesGameEngineRegistry()
