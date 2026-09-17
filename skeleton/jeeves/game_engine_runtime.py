"""Unified executable game-engine router for Jeeves.

Callers choose an EngineEra and do not need to know whether that era is owned
by the legacy, transitional-3D, or modern runtime family. Each family keeps its
own historically appropriate implementation while sharing one create/evaluate/
improve boundary.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .game_engine_3d import (
    THREE_D_ERAS,
    ThreeDEngineLab,
)
from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
    SandboxSnapshot,
    VirtualFileTree,
)
from .game_engine_legacy import (
    LEGACY_ERAS,
    LegacyEngineLab,
)
from .game_engine_modern import (
    MODERN_ERAS,
    ModernEngineLab,
)


class EngineFamily(str, Enum):
    LEGACY = "legacy_2d"
    TRANSITION_3D = "transition_3d"
    MODERN = "modern_hd_next"


ERA_FAMILY = {
    **{
        era: EngineFamily.LEGACY
        for era in LEGACY_ERAS
    },
    **{
        era: EngineFamily.TRANSITION_3D
        for era in THREE_D_ERAS
    },
    **{
        era: EngineFamily.MODERN
        for era in MODERN_ERAS
    },
}


def engine_family(
    era: EngineEra | str,
) -> EngineFamily:
    try:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
    except ValueError as exc:
        raise GameEngineLabError(
            f"unknown engine era: {era!r}"
        ) from exc
    try:
        return ERA_FAMILY[key]
    except KeyError as exc:
        raise GameEngineLabError(
            f"no executable runtime family for {key.value}"
        ) from exc


@dataclass(frozen=True, slots=True)
class RoutedEngineSandbox:
    era: EngineEra
    family: EngineFamily
    native: Any

    @property
    def tree(self) -> VirtualFileTree:
        return self.native.tree

    @property
    def gameplay_dialect(self) -> str | None:
        return self.native.gameplay_dialect

    def machine(self) -> Any:
        return self.native.machine()

    def with_tree(
        self,
        tree: VirtualFileTree,
    ) -> "RoutedEngineSandbox":
        native = type(self.native)(
            self.era,
            tree,
            self.gameplay_dialect,
        )
        return RoutedEngineSandbox(
            self.era,
            self.family,
            native,
        )

    def apply(
        self,
        patches: Iterable[SandboxPatch],
    ) -> "RoutedEngineSandbox":
        return RoutedEngineSandbox(
            self.era,
            self.family,
            self.native.apply(patches),
        )


@dataclass(frozen=True, slots=True)
class RoutedImprovementResult:
    sandbox: RoutedEngineSandbox
    report: Any
    rounds: tuple[Any, ...]
    promoted: bool


class ExecutableGameEngineLab:
    """Jeeves' single runtime surface across the complete era ladder."""

    def __init__(self) -> None:
        self.legacy = LegacyEngineLab()
        self.transition_3d = ThreeDEngineLab()
        self.modern = ModernEngineLab()

    def _lab(
        self,
        era: EngineEra | str,
    ) -> tuple[
        EngineEra,
        EngineFamily,
        Any,
    ]:
        try:
            key = (
                era
                if isinstance(era, EngineEra)
                else EngineEra(str(era))
            )
        except ValueError as exc:
            raise GameEngineLabError(
                f"unknown engine era: {era!r}"
            ) from exc
        family = engine_family(key)
        if family is EngineFamily.LEGACY:
            lab = self.legacy
        elif family is EngineFamily.TRANSITION_3D:
            lab = self.transition_3d
        else:
            lab = self.modern
        return key, family, lab

    def create(
        self,
        era: EngineEra | str,
        gameplay_dialect: str | None = None,
    ) -> RoutedEngineSandbox:
        key, family, lab = self._lab(
            era
        )
        return RoutedEngineSandbox(
            key,
            family,
            lab.create(
                key,
                gameplay_dialect,
            ),
        )

    def evaluate(
        self,
        sandbox: RoutedEngineSandbox,
    ) -> Any:
        _, expected, lab = self._lab(
            sandbox.era
        )
        if sandbox.family is not expected:
            raise GameEngineLabError(
                "sandbox family does not match era"
            )
        return lab.evaluate(
            sandbox.native
        )

    def adversarial_improve(
        self,
        sandbox: RoutedEngineSandbox,
        *,
        target: float = 1.0,
        max_rounds: int = 6,
        improver=None,
    ) -> RoutedImprovementResult:
        _, expected, lab = self._lab(
            sandbox.era
        )
        if sandbox.family is not expected:
            raise GameEngineLabError(
                "sandbox family does not match era"
            )
        result = lab.adversarial_improve(
            sandbox.native,
            target=target,
            max_rounds=max_rounds,
            improver=improver,
        )
        return RoutedImprovementResult(
            RoutedEngineSandbox(
                sandbox.era,
                sandbox.family,
                result.sandbox,
            ),
            result.report,
            tuple(result.rounds),
            result.promoted,
        )

    def canonical_repair(
        self,
        sandbox: RoutedEngineSandbox,
        report: Any,
    ) -> tuple[SandboxPatch, ...]:
        _, expected, lab = self._lab(
            sandbox.era
        )
        if sandbox.family is not expected:
            raise GameEngineLabError(
                "sandbox family does not match era"
            )
        return tuple(
            lab.canonical_repair(
                sandbox.native,
                report,
            )
        )

    def build_all(
        self,
        gameplay_dialect: str | None = None,
    ) -> tuple[RoutedEngineSandbox, ...]:
        return tuple(
            self.create(
                era,
                gameplay_dialect,
            )
            for era in EngineEra
        )

    def evaluate_all(
        self,
        gameplay_dialect: str | None = None,
    ) -> tuple[tuple[EngineEra, Any], ...]:
        return tuple(
            (
                sandbox.era,
                self.evaluate(
                    sandbox
                ),
            )
            for sandbox
            in self.build_all(
                gameplay_dialect
            )
        )


def build_executable_game_engine(
    era: EngineEra | str,
    gameplay_dialect: str | None = None,
) -> RoutedEngineSandbox:
    return ExecutableGameEngineLab().create(
        era,
        gameplay_dialect,
    )


@dataclass(frozen=True, slots=True)
class EvolutionRound:
    index: int
    before_digest: str
    selected_digest: str | None
    candidate_count: int
    before_score: float
    selected_score: float
    accepted: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EngineEvolutionSession:
    sandbox: RoutedEngineSandbox
    checkpoints: tuple[SandboxSnapshot, ...]
    sequence: int

    @classmethod
    def start(
        cls,
        sandbox: RoutedEngineSandbox,
    ) -> "EngineEvolutionSession":
        snapshot = sandbox.tree.snapshot(
            sandbox.era,
            0,
            None,
        )
        return cls(
            sandbox,
            (snapshot,),
            1,
        )

    @property
    def latest_checkpoint(
        self,
    ) -> SandboxSnapshot:
        return self.checkpoints[-1]

    def checkpoint(
        self,
        sandbox: RoutedEngineSandbox,
    ) -> "EngineEvolutionSession":
        if sandbox.era is not self.sandbox.era:
            raise GameEngineLabError(
                "cannot checkpoint a different engine era"
            )
        if sandbox.family is not self.sandbox.family:
            raise GameEngineLabError(
                "cannot checkpoint a different engine family"
            )
        parent = self.latest_checkpoint.tree_digest
        snapshot = sandbox.tree.snapshot(
            sandbox.era,
            self.sequence,
            parent,
        )
        return EngineEvolutionSession(
            sandbox,
            self.checkpoints + (snapshot,),
            self.sequence + 1,
        )

    @property
    def lineage_digest(self) -> str:
        payload = "|".join(
            (
                f"{snapshot.sequence}:"
                f"{snapshot.parent_digest or '-'}:"
                f"{snapshot.tree_digest}"
            )
            for snapshot in self.checkpoints
        )
        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    def verify_lineage(self) -> bool:
        if not self.checkpoints:
            raise GameEngineLabError(
                "evolution session has no checkpoints"
            )
        parent: str | None = None
        expected_sequence = 0
        for snapshot in self.checkpoints:
            if snapshot.era is not self.sandbox.era:
                raise GameEngineLabError(
                    "evolution checkpoint era mismatch"
                )
            if snapshot.sequence != expected_sequence:
                raise GameEngineLabError(
                    "evolution checkpoint sequence mismatch"
                )
            if snapshot.parent_digest != parent:
                raise GameEngineLabError(
                    "evolution checkpoint parent mismatch"
                )
            VirtualFileTree.restore(
                snapshot
            )
            parent = snapshot.tree_digest
            expected_sequence += 1
        return True

    def restore(
        self,
        index: int = -1,
    ) -> "EngineEvolutionSession":
        if not self.checkpoints:
            raise GameEngineLabError(
                "evolution session has no checkpoints"
            )
        try:
            snapshot = self.checkpoints[index]
        except IndexError as exc:
            raise GameEngineLabError(
                "evolution checkpoint index out of range"
            ) from exc
        if snapshot.era is not self.sandbox.era:
            raise GameEngineLabError(
                "evolution checkpoint era mismatch"
            )
        tree = VirtualFileTree.restore(
            snapshot
        )
        restored = self.sandbox.with_tree(
            tree
        )
        return EngineEvolutionSession(
            restored,
            self.checkpoints,
            max(
                self.sequence,
                snapshot.sequence + 1,
            ),
        )


@dataclass(frozen=True, slots=True)
class EvolutionResult:
    session: EngineEvolutionSession
    report: Any
    rounds: tuple[EvolutionRound, ...]
    target_met: bool


CandidateSet = Iterable[SandboxPatch]


def _strictly_improves(
    before: Any,
    after: Any,
) -> bool:
    return (
        after.score > before.score
        or len(after.failed)
        < len(before.failed)
    )


def _meets_target(
    report: Any,
    target: float,
) -> bool:
    return (
        bool(report.passed)
        and report.score >= target
    )


class AdversarialEngineEvolution:
    """Snapshot-backed candidate tournament across every executable era."""

    def __init__(
        self,
        lab: ExecutableGameEngineLab | None = None,
    ) -> None:
        self.lab = (
            lab
            or ExecutableGameEngineLab()
        )

    def start(
        self,
        sandbox: RoutedEngineSandbox,
    ) -> EngineEvolutionSession:
        # Validate the family binding before creating lineage authority.
        self.lab.evaluate(sandbox)
        return EngineEvolutionSession.start(
            sandbox
        )

    def tournament_round(
        self,
        session: EngineEvolutionSession,
        candidates: Iterable[CandidateSet],
        *,
        index: int = 1,
        max_candidates: int = 32,
    ) -> tuple[
        EngineEvolutionSession,
        Any,
        EvolutionRound,
    ]:
        if (
            not isinstance(max_candidates, int)
            or not 1 <= max_candidates <= 128
        ):
            raise GameEngineLabError(
                "max_candidates must be within [1, 128]"
            )
        before = self.lab.evaluate(
            session.sandbox
        )
        evaluated: list[
            tuple[
                float,
                int,
                str,
                RoutedEngineSandbox,
                Any,
            ]
        ] = []
        candidate_count = 0
        for raw in candidates:
            if candidate_count >= max_candidates:
                break
            candidate_count += 1
            try:
                patches = tuple(raw)
                if not patches:
                    continue
                candidate = (
                    session.sandbox.apply(
                        patches
                    )
                )
                if (
                    candidate.tree.digest
                    == session.sandbox.tree.digest
                ):
                    continue
                report = self.lab.evaluate(
                    candidate
                )
            except (
                GameEngineLabError,
                TypeError,
                ValueError,
            ):
                continue
            if not _strictly_improves(
                before,
                report,
            ):
                continue
            evaluated.append(
                (
                    -report.score,
                    len(report.failed),
                    candidate.tree.digest,
                    candidate,
                    report,
                )
            )
        if not evaluated:
            round_result = EvolutionRound(
                index,
                session.sandbox.tree.digest,
                None,
                candidate_count,
                before.score,
                before.score,
                False,
                tuple(before.failed),
            )
            return (
                session,
                before,
                round_result,
            )
        evaluated.sort(
            key=lambda row: (
                row[0],
                row[1],
                row[2],
            )
        )
        (
            _,
            _,
            selected_digest,
            selected,
            selected_report,
        ) = evaluated[0]
        promoted = session.checkpoint(
            selected
        )
        round_result = EvolutionRound(
            index,
            session.sandbox.tree.digest,
            selected_digest,
            candidate_count,
            before.score,
            selected_report.score,
            True,
            tuple(
                selected_report.failed
            ),
        )
        return (
            promoted,
            selected_report,
            round_result,
        )

    def evolve(
        self,
        session: EngineEvolutionSession,
        proposer,
        *,
        target: float = 1.0,
        max_rounds: int = 12,
        max_candidates: int = 32,
    ) -> EvolutionResult:
        if not 0 < target <= 1:
            raise GameEngineLabError(
                "target must be within (0, 1]"
            )
        if (
            not isinstance(max_rounds, int)
            or not 1 <= max_rounds <= 64
        ):
            raise GameEngineLabError(
                "max_rounds must be within [1, 64]"
            )
        current = session
        report = self.lab.evaluate(
            current.sandbox
        )
        rounds: list[
            EvolutionRound
        ] = []
        if _meets_target(
            report,
            target,
        ):
            return EvolutionResult(
                current,
                report,
                (),
                True,
            )
        for index in range(
            1,
            max_rounds + 1,
        ):
            proposed = proposer(
                current,
                report,
            )
            if proposed is None:
                break
            (
                next_session,
                next_report,
                round_result,
            ) = self.tournament_round(
                current,
                proposed,
                index=index,
                max_candidates=max_candidates,
            )
            rounds.append(
                round_result
            )
            if not round_result.accepted:
                break
            current = next_session
            report = next_report
            if _meets_target(
                report,
                target,
            ):
                break
        return EvolutionResult(
            current,
            report,
            tuple(rounds),
            _meets_target(
                report,
                target,
            ),
        )

    def canonical_candidates(
        self,
        session: EngineEvolutionSession,
        report: Any,
    ) -> tuple[tuple[SandboxPatch, ...], ...]:
        repair = self.lab.canonical_repair(
            session.sandbox,
            report,
        )
        return (
            (repair,)
            if repair
            else ()
        )
