"""Cross-era benchmark and red-team arena for Jeeves game engines.

This layer consumes the canonical executable router/evolution surface. It does
not introduce another runtime. Its job is to make "quality meets expectation"
falsifiable across the complete Pong-to-next engine ladder and to prove that
candidate selection recovers from bounded adversarial damage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from .game_engine_runtime import (
    AdversarialEngineEvolution,
    EngineFamily,
    EngineEvolutionSession,
    ExecutableGameEngineLab,
    RoutedEngineSandbox,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class QualityExpectation:
    minimum_score: float = 1.0
    maximum_failures: int = 0
    require_passed: bool = True
    max_rounds: int = 8
    max_candidates: int = 16

    def __post_init__(self) -> None:
        if not 0 < self.minimum_score <= 1:
            raise GameEngineLabError(
                "minimum_score must be within (0, 1]"
            )
        if (
            not isinstance(self.maximum_failures, int)
            or self.maximum_failures < 0
        ):
            raise GameEngineLabError(
                "maximum_failures must be a non-negative integer"
            )
        if not isinstance(self.max_rounds, int) or not 1 <= self.max_rounds <= 64:
            raise GameEngineLabError(
                "max_rounds must be within [1, 64]"
            )
        if (
            not isinstance(self.max_candidates, int)
            or not 1 <= self.max_candidates <= 128
        ):
            raise GameEngineLabError(
                "max_candidates must be within [1, 128]"
            )

    def accepts(self, report: Any) -> bool:
        return (
            float(report.score) >= self.minimum_score
            and len(tuple(report.failed)) <= self.maximum_failures
            and (not self.require_passed or bool(report.passed))
        )


@dataclass(frozen=True, slots=True)
class EngineBenchmarkEntry:
    era: EngineEra
    family: EngineFamily
    tree_digest: str
    score: float
    passed: bool
    failures: tuple[str, ...]
    probe_digest: str
    meets_expectation: bool


@dataclass(frozen=True, slots=True)
class EngineBenchmarkReport:
    entries: tuple[EngineBenchmarkEntry, ...]
    expectation: QualityExpectation
    digest: str

    @property
    def all_meet_expectation(self) -> bool:
        return bool(self.entries) and all(
            entry.meets_expectation for entry in self.entries
        )

    @property
    def minimum_score(self) -> float:
        if not self.entries:
            return 0.0
        return min(entry.score for entry in self.entries)


@dataclass(frozen=True, slots=True)
class AttackVerdict:
    name: str
    detected: bool
    candidate_count: int
    accepted: bool
    recovered: bool
    attacked_score: float
    recovered_score: float
    checkpoint_count: int
    selected_digest: str | None


@dataclass(frozen=True, slots=True)
class EraTournamentReport:
    era: EngineEra
    family: EngineFamily
    baseline_digest: str
    baseline_score: float
    attacks: tuple[AttackVerdict, ...]
    expectation: QualityExpectation
    digest: str

    @property
    def passed(self) -> bool:
        return bool(self.attacks) and all(
            verdict.detected
            and verdict.accepted
            and verdict.recovered
            for verdict in self.attacks
            if verdict.name != "stale_patch"
        ) and all(
            verdict.detected and verdict.recovered
            for verdict in self.attacks
            if verdict.name == "stale_patch"
        )


class GameEngineBenchmarkArena:
    """Evidence-oriented matrix and recovery tournament over every engine era."""

    def __init__(
        self,
        lab: ExecutableGameEngineLab | None = None,
        expectation: QualityExpectation | None = None,
    ) -> None:
        self.lab = lab or ExecutableGameEngineLab()
        self.expectation = expectation or QualityExpectation()
        self.evolution = AdversarialEngineEvolution(self.lab)

    def _probe_digest(self, report: Any) -> str:
        probes = tuple(
            (
                str(probe.name),
                bool(probe.passed),
                str(probe.detail),
            )
            for probe in report.probes
        )
        return _digest(probes)

    def benchmark_all(
        self,
        gameplay_dialect: str | None = None,
    ) -> EngineBenchmarkReport:
        entries: list[EngineBenchmarkEntry] = []
        for sandbox in self.lab.build_all(gameplay_dialect):
            report = self.lab.evaluate(sandbox)
            entries.append(
                EngineBenchmarkEntry(
                    era=sandbox.era,
                    family=sandbox.family,
                    tree_digest=sandbox.tree.digest,
                    score=float(report.score),
                    passed=bool(report.passed),
                    failures=tuple(str(item) for item in report.failed),
                    probe_digest=self._probe_digest(report),
                    meets_expectation=self.expectation.accepts(report),
                )
            )
        payload = tuple(
            (
                entry.era.value,
                entry.family.value,
                entry.tree_digest,
                entry.score,
                entry.passed,
                entry.failures,
                entry.probe_digest,
                entry.meets_expectation,
            )
            for entry in entries
        )
        return EngineBenchmarkReport(
            entries=tuple(entries),
            expectation=self.expectation,
            digest=_digest(payload),
        )

    def _tuning_path(self, sandbox: RoutedEngineSandbox) -> str:
        if sandbox.family is EngineFamily.LEGACY:
            return "engine/legacy_tuning.json"
        if sandbox.family is EngineFamily.TRANSITION_3D:
            return "engine/3d_tuning.json"
        return "engine/modern_tuning.json"

    def _runtime_path(self, sandbox: RoutedEngineSandbox) -> str:
        if sandbox.family is EngineFamily.LEGACY:
            return "engine/legacy_runtime.py"
        if sandbox.family is EngineFamily.TRANSITION_3D:
            return "engine/3d_runtime.py"
        return "engine/modern_runtime.py"

    def tuning_overflow_attack(
        self,
        sandbox: RoutedEngineSandbox,
    ) -> RoutedEngineSandbox:
        path = self._tuning_path(sandbox)
        try:
            payload = json.loads(sandbox.tree.read(path))
        except json.JSONDecodeError as exc:
            raise GameEngineLabError(
                "canonical tuning is not valid JSON"
            ) from exc
        if not isinstance(payload, dict) or not payload:
            raise GameEngineLabError(
                "canonical tuning must be a non-empty object"
            )
        field = sorted(payload)[0]
        payload[field] = 1_000_000_000
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
        sandbox: RoutedEngineSandbox,
    ) -> RoutedEngineSandbox:
        path = self._runtime_path(sandbox)
        return sandbox.apply(
            (
                SandboxPatch(
                    path,
                    None,
                    sandbox.tree.file_digest(path),
                ),
            )
        )

    def _decoy_candidate(
        self,
        sandbox: RoutedEngineSandbox,
    ) -> tuple[SandboxPatch, ...]:
        path = self._runtime_path(sandbox)
        digest = sandbox.tree.file_digest(path)
        if digest is None:
            # If the runtime itself is the attacked field, corrupt a mandatory
            # base manifest instead. The decoy remains strictly non-repairing.
            path = "engine/manifest.json"
            digest = sandbox.tree.file_digest(path)
        return (
            SandboxPatch(
                path,
                None,
                digest,
            ),
        )

    def _stale_candidate(
        self,
        sandbox: RoutedEngineSandbox,
    ) -> tuple[SandboxPatch, ...]:
        path = "engine/manifest.json"
        return (
            SandboxPatch(
                path,
                sandbox.tree.read(path),
                "0" * 64,
            ),
        )

    def _recovery_round(
        self,
        attacked: RoutedEngineSandbox,
    ) -> AttackVerdict:
        attacked_report = self.lab.evaluate(attacked)
        session = self.evolution.start(attacked)
        repair = self.lab.canonical_repair(
            attacked,
            attacked_report,
        )
        candidates = (
            self._decoy_candidate(attacked),
            self._stale_candidate(attacked),
            repair,
        )
        (
            promoted,
            recovered_report,
            round_result,
        ) = self.evolution.tournament_round(
            session,
            candidates,
            index=1,
            max_candidates=self.expectation.max_candidates,
        )
        return AttackVerdict(
            name="",
            detected=not bool(attacked_report.passed),
            candidate_count=round_result.candidate_count,
            accepted=round_result.accepted,
            recovered=self.expectation.accepts(recovered_report),
            attacked_score=float(attacked_report.score),
            recovered_score=float(recovered_report.score),
            checkpoint_count=len(promoted.checkpoints),
            selected_digest=round_result.selected_digest,
        )

    def _stale_patch_verdict(
        self,
        baseline: RoutedEngineSandbox,
    ) -> AttackVerdict:
        before_digest = baseline.tree.digest
        before = self.lab.evaluate(baseline)
        try:
            baseline.apply(self._stale_candidate(baseline))
        except GameEngineLabError:
            detected = True
        else:
            detected = False
        after = self.lab.evaluate(baseline)
        return AttackVerdict(
            name="stale_patch",
            detected=detected,
            candidate_count=1,
            accepted=False,
            recovered=self.expectation.accepts(after)
            and baseline.tree.digest == before_digest,
            attacked_score=float(before.score),
            recovered_score=float(after.score),
            checkpoint_count=1,
            selected_digest=None,
        )

    def tournament(
        self,
        era: EngineEra | str,
        gameplay_dialect: str | None = None,
    ) -> EraTournamentReport:
        baseline = self.lab.create(era, gameplay_dialect)
        baseline_report = self.lab.evaluate(baseline)
        if not self.expectation.accepts(baseline_report):
            raise GameEngineLabError(
                "canonical engine does not meet tournament expectation"
            )

        tuning = self._recovery_round(
            self.tuning_overflow_attack(baseline)
        )
        tuning = AttackVerdict(
            "tuning_overflow",
            tuning.detected,
            tuning.candidate_count,
            tuning.accepted,
            tuning.recovered,
            tuning.attacked_score,
            tuning.recovered_score,
            tuning.checkpoint_count,
            tuning.selected_digest,
        )

        contract = self._recovery_round(
            self.contract_delete_attack(baseline)
        )
        contract = AttackVerdict(
            "contract_delete",
            contract.detected,
            contract.candidate_count,
            contract.accepted,
            contract.recovered,
            contract.attacked_score,
            contract.recovered_score,
            contract.checkpoint_count,
            contract.selected_digest,
        )
        stale = self._stale_patch_verdict(baseline)
        attacks = (tuning, contract, stale)
        payload = {
            "era": baseline.era.value,
            "family": baseline.family.value,
            "baseline_digest": baseline.tree.digest,
            "baseline_score": baseline_report.score,
            "attacks": tuple(
                (
                    attack.name,
                    attack.detected,
                    attack.candidate_count,
                    attack.accepted,
                    attack.recovered,
                    attack.attacked_score,
                    attack.recovered_score,
                    attack.checkpoint_count,
                    attack.selected_digest,
                )
                for attack in attacks
            ),
        }
        return EraTournamentReport(
            era=baseline.era,
            family=baseline.family,
            baseline_digest=baseline.tree.digest,
            baseline_score=float(baseline_report.score),
            attacks=attacks,
            expectation=self.expectation,
            digest=_digest(payload),
        )

    def tournament_all(
        self,
        gameplay_dialect: str | None = None,
    ) -> tuple[EraTournamentReport, ...]:
        return tuple(
            self.tournament(era, gameplay_dialect)
            for era in EngineEra
        )


def build_game_engine_benchmark_arena(
    expectation: QualityExpectation | None = None,
) -> GameEngineBenchmarkArena:
    return GameEngineBenchmarkArena(expectation=expectation)
