"""Composite game-project quality and evolution for Jeeves.

Runtime, compiled assets, deterministic scripts, physics, audio, animation,
and navigation are separate evidence planes. Promotion is Pareto-safe: a candidate must not
regress any plane and must strictly improve at least one. This prevents a fix
in one subsystem from smuggling degradation through another.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .game_engine_animation import (
    AnimationAdversary,
    AnimationQualityReport,
    AnimationSceneSource,
    attach_animation_build,
    canonical_animation_patches,
    canonical_animation_source,
)
from .game_engine_audio import (
    AudioAdversary,
    AudioQualityReport,
    AudioSceneSource,
    attach_audio_build,
    canonical_audio_patches,
    canonical_audio_source,
)
from .game_engine_assets import (
    AssetCompilerAdversary,
    AssetQualityReport,
    SourceAsset,
    attach_asset_build,
    canonical_asset_patches,
    canonical_asset_sources,
)
from .game_engine_navigation import (
    NavigationAdversary,
    NavigationQualityReport,
    NavigationSource,
    attach_navigation_build,
    canonical_navigation_patches,
    canonical_navigation_source,
)
from .game_engine_physics import (
    PhysicsAdversary,
    PhysicsQualityReport,
    PhysicsSceneSource,
    attach_physics_build,
    canonical_physics_patches,
    canonical_physics_source,
)
from .game_engine_scripts import (
    ScriptAdversary,
    ScriptQualityReport,
    ScriptSource,
    attach_script_build,
    canonical_script_patches,
    canonical_script_sources,
)
from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from .game_engine_runtime import (
    EngineEvolutionSession,
    ExecutableGameEngineLab,
    RoutedEngineSandbox,
    runtime_nonregressing,
    runtime_strictly_improves,
    EVIDENCE_PLANE_PREFIXES,
)


@dataclass(frozen=True, slots=True)
class GameProjectSandbox:
    engine: RoutedEngineSandbox
    sources: tuple[SourceAsset, ...]
    scripts: tuple[ScriptSource, ...]
    physics: PhysicsSceneSource
    audio: AudioSceneSource
    animation: AnimationSceneSource
    navigation: NavigationSource

    @property
    def era(self) -> EngineEra:
        return self.engine.era

    @property
    def family(self):
        return self.engine.family

    @property
    def gameplay_dialect(
        self,
    ) -> str | None:
        return self.engine.gameplay_dialect

    @property
    def tree(self):
        return self.engine.tree

    def machine(self):
        return self.engine.machine()

    def apply(
        self,
        patches: Iterable[SandboxPatch],
    ) -> "GameProjectSandbox":
        return GameProjectSandbox(
            self.engine.apply(patches),
            self.sources,
            self.scripts,
            self.physics,
            self.audio,
            self.animation,
            self.navigation,
        )


@dataclass(frozen=True, slots=True)
class ProjectQualityReport:
    era: EngineEra
    runtime: Any
    assets: AssetQualityReport
    scripts: ScriptQualityReport
    physics: PhysicsQualityReport
    audio: AudioQualityReport
    animation: AnimationQualityReport
    navigation: NavigationQualityReport

    @property
    def passed(self) -> bool:
        return (
            bool(self.runtime.passed)
            and self.assets.passed
            and self.scripts.passed
            and self.physics.passed
            and self.audio.passed
            and self.animation.passed
            and self.navigation.passed
        )

    @property
    def score(self) -> float:
        # Give all seven project planes equal authority regardless of how many
        # individual probes each underlying plane exposes.
        return (
            float(self.runtime.score)
            + self.assets.score
            + self.scripts.score
            + self.physics.score
            + self.audio.score
            + self.animation.score
            + self.navigation.score
        ) / 7.0

    @property
    def failed(self) -> tuple[str, ...]:
        return (
            tuple(
                "runtime:" + name
                for name
                in self.runtime.failed
            )
            + tuple(
                "assets:" + name
                for name
                in self.assets.failed
            )
            + tuple(
                "scripts:" + name
                for name
                in self.scripts.failed
            )
            + tuple(
                "physics:" + name
                for name
                in self.physics.failed
            )
            + tuple(
                "audio:" + name
                for name
                in self.audio.failed
            )
            + tuple(
                "animation:" + name
                for name
                in self.animation.failed
            )
            + tuple(
                "navigation:" + name
                for name
                in self.navigation.failed
            )
        )

    @property
    def runtime_score(self) -> float:
        return float(
            self.runtime.score
        )

    @property
    def asset_score(self) -> float:
        return self.assets.score

    @property
    def script_score(self) -> float:
        return self.scripts.score

    @property
    def physics_score(self) -> float:
        return self.physics.score

    @property
    def audio_score(self) -> float:
        return self.audio.score

    @property
    def animation_score(self) -> float:
        return self.animation.score

    @property
    def navigation_score(self) -> float:
        return self.navigation.score


class ExecutableGameProjectLab:
    """Build and evaluate complete era projects, not isolated subsystems."""

    def __init__(
        self,
        engine_lab: ExecutableGameEngineLab | None = None,
        asset_adversary: AssetCompilerAdversary | None = None,
        script_adversary: ScriptAdversary | None = None,
        physics_adversary: PhysicsAdversary | None = None,
        audio_adversary: AudioAdversary | None = None,
        animation_adversary: AnimationAdversary | None = None,
        navigation_adversary: NavigationAdversary | None = None,
    ) -> None:
        self.engine_lab = (
            engine_lab
            or ExecutableGameEngineLab()
        )
        self.asset_adversary = (
            asset_adversary
            or AssetCompilerAdversary()
        )
        self.script_adversary = (
            script_adversary
            or ScriptAdversary()
        )
        self.physics_adversary = (
            physics_adversary
            or PhysicsAdversary()
        )
        self.audio_adversary = (
            audio_adversary
            or AudioAdversary()
        )
        self.animation_adversary = (
            animation_adversary
            or AnimationAdversary()
        )
        self.navigation_adversary = (
            navigation_adversary
            or NavigationAdversary()
        )

    def create(
        self,
        era: EngineEra | str,
        gameplay_dialect: str | None = None,
        *,
        sources: Iterable[SourceAsset] | None = None,
        scripts: Iterable[ScriptSource] | None = None,
        physics: PhysicsSceneSource | None = None,
        audio: AudioSceneSource | None = None,
        animation: AnimationSceneSource | None = None,
        navigation: NavigationSource | None = None,
    ) -> GameProjectSandbox:
        engine = self.engine_lab.create(
            era,
            gameplay_dialect,
        )
        source_values = (
            tuple(sources)
            if sources is not None
            else canonical_asset_sources(
                engine.era
            )
        )
        compiled_assets = attach_asset_build(
            engine,
            source_values,
        )
        script_values = (
            tuple(scripts)
            if scripts is not None
            else canonical_script_sources(
                engine.era
            )
        )
        compiled_scripts = attach_script_build(
            compiled_assets,
            script_values,
        )
        physics_source = (
            physics
            if physics is not None
            else canonical_physics_source(
                engine.era
            )
        )
        compiled_physics = attach_physics_build(
            compiled_scripts,
            physics_source,
        )
        audio_source = (
            audio
            if audio is not None
            else canonical_audio_source(
                engine.era
            )
        )
        compiled_audio = attach_audio_build(
            compiled_physics,
            audio_source,
        )
        animation_source = (
            animation
            if animation is not None
            else canonical_animation_source(
                engine.era
            )
        )
        compiled_animation = attach_animation_build(
            compiled_audio,
            animation_source,
        )
        navigation_source = (
            navigation
            if navigation is not None
            else canonical_navigation_source(
                engine.era
            )
        )
        compiled = attach_navigation_build(
            compiled_animation,
            navigation_source,
        )
        return GameProjectSandbox(
            compiled,
            source_values,
            script_values,
            physics_source,
            audio_source,
            animation_source,
            navigation_source,
        )

    def evaluate(
        self,
        project: GameProjectSandbox,
    ) -> ProjectQualityReport:
        runtime = (
            self.engine_lab.evaluate(
                project.engine
            )
        )
        assets = (
            self.asset_adversary.evaluate(
                project.engine,
                project.sources,
            )
        )
        scripts = (
            self.script_adversary.evaluate(
                project.engine,
                project.scripts,
            )
        )
        physics = (
            self.physics_adversary.evaluate(
                project.engine,
                project.physics,
            )
        )
        audio = (
            self.audio_adversary.evaluate(
                project.engine,
                project.audio,
            )
        )
        animation = (
            self.animation_adversary.evaluate(
                project.engine,
                project.animation,
            )
        )
        navigation = (
            self.navigation_adversary.evaluate(
                project.engine,
                project.navigation,
            )
        )
        return ProjectQualityReport(
            project.era,
            runtime,
            assets,
            scripts,
            physics,
            audio,
            animation,
            navigation,
        )

    def canonical_repair(
        self,
        project: GameProjectSandbox,
        report: ProjectQualityReport,
    ) -> tuple[SandboxPatch, ...]:
        runtime_patches = tuple(
            self.engine_lab.canonical_repair(
                project.engine,
                report.runtime,
            )
        )
        asset_patches = (
            canonical_asset_patches(
                project.engine,
                project.sources,
            )
        )
        script_patches = (
            canonical_script_patches(
                project.engine,
                project.scripts,
            )
        )
        physics_patches = (
            canonical_physics_patches(
                project.engine,
                project.physics,
            )
        )
        audio_patches = (
            canonical_audio_patches(
                project.engine,
                project.audio,
            )
        )
        animation_patches = (
            canonical_animation_patches(
                project.engine,
                project.animation,
            )
        )
        navigation_patches = (
            canonical_navigation_patches(
                project.engine,
                project.navigation,
            )
        )
        paths = [
            patch.path
            for patch
            in (
                runtime_patches
                + asset_patches
                + script_patches
                + physics_patches
                + audio_patches
                + animation_patches
                + navigation_patches
            )
        ]
        if len(paths) != len(
            set(paths)
        ):
            raise GameEngineLabError(
                "project repair planes overlap"
            )
        return (
            runtime_patches
            + asset_patches
            + script_patches
            + physics_patches
            + audio_patches
            + animation_patches
            + navigation_patches
        )


def _nonregressing_improvement(
    before: ProjectQualityReport,
    after: ProjectQualityReport,
) -> bool:
    runtime_plane_ok = (
        runtime_nonregressing(
            before.runtime,
            after.runtime,
        )
    )
    assets_nonregressing = (
        after.asset_score
        >= before.asset_score
        and len(
            after.assets.failed
        )
        <= len(
            before.assets.failed
        )
    )
    scripts_nonregressing = (
        after.script_score
        >= before.script_score
        and len(
            after.scripts.failed
        )
        <= len(
            before.scripts.failed
        )
    )
    physics_nonregressing = (
        after.physics_score
        >= before.physics_score
        and len(
            after.physics.failed
        )
        <= len(
            before.physics.failed
        )
    )
    audio_nonregressing = (
        after.audio_score
        >= before.audio_score
        and len(
            after.audio.failed
        )
        <= len(
            before.audio.failed
        )
    )
    animation_nonregressing = (
        after.animation_score
        >= before.animation_score
        and len(
            after.animation.failed
        )
        <= len(
            before.animation.failed
        )
    )
    navigation_nonregressing = (
        after.navigation_score
        >= before.navigation_score
        and len(
            after.navigation.failed
        )
        <= len(
            before.navigation.failed
        )
    )
    strict = (
        runtime_strictly_improves(
            before.runtime,
            after.runtime,
        )
        or after.asset_score
        > before.asset_score
        or after.script_score
        > before.script_score
        or after.physics_score
        > before.physics_score
        or after.audio_score
        > before.audio_score
        or after.animation_score
        > before.animation_score
        or after.navigation_score
        > before.navigation_score
        or len(after.failed)
        < len(before.failed)
    )
    return (
        runtime_plane_ok
        and assets_nonregressing
        and scripts_nonregressing
        and physics_nonregressing
        and audio_nonregressing
        and animation_nonregressing
        and navigation_nonregressing
        and strict
    )


def _meets_target(
    report: ProjectQualityReport,
    target: float,
) -> bool:
    return (
        report.passed
        and report.runtime_score
        >= target
        and report.asset_score
        >= target
        and report.script_score
        >= target
        and report.physics_score
        >= target
        and report.audio_score
        >= target
        and report.animation_score
        >= target
        and report.navigation_score
        >= target
    )


@dataclass(frozen=True, slots=True)
class ProjectEvolutionRound:
    index: int
    before_digest: str
    selected_digest: str | None
    candidate_count: int
    before_runtime_score: float
    selected_runtime_score: float
    before_asset_score: float
    selected_asset_score: float
    before_script_score: float
    selected_script_score: float
    before_physics_score: float
    selected_physics_score: float
    before_audio_score: float
    selected_audio_score: float
    before_animation_score: float
    selected_animation_score: float
    before_navigation_score: float
    selected_navigation_score: float
    accepted: bool
    failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProjectEvolutionSession:
    engine_session: EngineEvolutionSession
    sources: tuple[SourceAsset, ...]
    scripts: tuple[ScriptSource, ...]
    physics: PhysicsSceneSource
    audio: AudioSceneSource
    animation: AnimationSceneSource
    navigation: NavigationSource

    @classmethod
    def start(
        cls,
        project: GameProjectSandbox,
    ) -> "ProjectEvolutionSession":
        return cls(
            EngineEvolutionSession.start(
                project.engine
            ),
            project.sources,
            project.scripts,
            project.physics,
            project.audio,
            project.animation,
            project.navigation,
        )

    @property
    def sandbox(
        self,
    ) -> GameProjectSandbox:
        return GameProjectSandbox(
            self.engine_session.sandbox,
            self.sources,
            self.scripts,
            self.physics,
            self.audio,
            self.animation,
            self.navigation,
        )

    @property
    def checkpoints(self):
        return self.engine_session.checkpoints

    @property
    def sequence(self) -> int:
        return self.engine_session.sequence

    @property
    def lineage_digest(self) -> str:
        return (
            self.engine_session
            .lineage_digest
        )

    def verify_lineage(self) -> bool:
        return (
            self.engine_session
            .verify_lineage()
        )

    def checkpoint(
        self,
        project: GameProjectSandbox,
    ) -> "ProjectEvolutionSession":
        if (
            project.sources
            != self.sources
        ):
            raise GameEngineLabError(
                "project source recipes cannot change inside a quality lineage"
            )
        if (
            project.scripts
            != self.scripts
        ):
            raise GameEngineLabError(
                "project script recipes cannot change inside a quality lineage"
            )
        if (
            project.physics
            != self.physics
        ):
            raise GameEngineLabError(
                "project physics recipe cannot change inside a quality lineage"
            )
        if (
            project.audio
            != self.audio
        ):
            raise GameEngineLabError(
                "project audio recipe cannot change inside a quality lineage"
            )
        if (
            project.animation
            != self.animation
        ):
            raise GameEngineLabError(
                "project animation recipe cannot change inside a quality lineage"
            )
        if (
            project.navigation
            != self.navigation
        ):
            raise GameEngineLabError(
                "project navigation recipe cannot change inside a quality lineage"
            )
        return ProjectEvolutionSession(
            self.engine_session.checkpoint(
                project.engine
            ),
            self.sources,
            self.scripts,
            self.physics,
            self.audio,
            self.animation,
            self.navigation,
        )

    def restore(
        self,
        index: int = -1,
    ) -> "ProjectEvolutionSession":
        return ProjectEvolutionSession(
            self.engine_session.restore(
                index
            ),
            self.sources,
            self.scripts,
            self.physics,
            self.audio,
            self.animation,
            self.navigation,
        )


@dataclass(frozen=True, slots=True)
class ProjectEvolutionResult:
    session: ProjectEvolutionSession
    report: ProjectQualityReport
    rounds: tuple[
        ProjectEvolutionRound,
        ...,
    ]
    target_met: bool


class AdversarialGameProjectEvolution:
    """Tournament evolution where every project evidence plane has a veto."""

    def __init__(
        self,
        lab: ExecutableGameProjectLab | None = None,
    ) -> None:
        self.lab = (
            lab
            or ExecutableGameProjectLab()
        )

    def start(
        self,
        project: GameProjectSandbox,
    ) -> ProjectEvolutionSession:
        # Evaluation here makes malformed project state fail closed before it
        # becomes the root of a new authoritative lineage.
        self.lab.evaluate(project)
        return ProjectEvolutionSession.start(
            project
        )

    def tournament_round(
        self,
        session: ProjectEvolutionSession,
        candidates: Iterable[
            Iterable[SandboxPatch]
        ],
        *,
        index: int = 1,
        max_candidates: int = 32,
    ) -> tuple[
        ProjectEvolutionSession,
        ProjectQualityReport,
        ProjectEvolutionRound,
    ]:
        if (
            type(max_candidates) is not int
            or not 1
            <= max_candidates
            <= 128
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
                GameProjectSandbox,
                ProjectQualityReport,
            ]
        ] = []
        candidate_count = 0
        for raw in candidates:
            if (
                candidate_count
                >= max_candidates
            ):
                break
            candidate_count += 1
            try:
                patches = tuple(raw)
                if not patches:
                    continue
                if any(
                    (
                        not patch.path.startswith(
                            EVIDENCE_PLANE_PREFIXES
                        )
                        and not self.lab.engine_lab.patch_allowed(
                            session.sandbox.engine,
                            patch,
                        )
                    )
                    for patch in patches
                ):
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
            if not _nonregressing_improvement(
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
            return (
                session,
                before,
                ProjectEvolutionRound(
                    index,
                    session.sandbox.tree.digest,
                    None,
                    candidate_count,
                    before.runtime_score,
                    before.runtime_score,
                    before.asset_score,
                    before.asset_score,
                    before.script_score,
                    before.script_score,
                    before.physics_score,
                    before.physics_score,
                    before.audio_score,
                    before.audio_score,
                    before.animation_score,
                    before.animation_score,
                    before.navigation_score,
                    before.navigation_score,
                    False,
                    before.failed,
                ),
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
        return (
            promoted,
            selected_report,
            ProjectEvolutionRound(
                index,
                session.sandbox.tree.digest,
                selected_digest,
                candidate_count,
                before.runtime_score,
                selected_report.runtime_score,
                before.asset_score,
                selected_report.asset_score,
                before.script_score,
                selected_report.script_score,
                before.physics_score,
                selected_report.physics_score,
                before.audio_score,
                selected_report.audio_score,
                before.animation_score,
                selected_report.animation_score,
                before.navigation_score,
                selected_report.navigation_score,
                True,
                selected_report.failed,
            ),
        )

    def canonical_candidates(
        self,
        session: ProjectEvolutionSession,
        report: ProjectQualityReport,
    ) -> tuple[
        tuple[SandboxPatch, ...],
        ...,
    ]:
        repair = (
            self.lab.canonical_repair(
                session.sandbox,
                report,
            )
        )
        return (
            (repair,)
            if repair
            else ()
        )

    def evolve(
        self,
        session: ProjectEvolutionSession,
        proposer,
        *,
        target: float = 1.0,
        max_rounds: int = 12,
        max_candidates: int = 32,
    ) -> ProjectEvolutionResult:
        if not 0 < target <= 1:
            raise GameEngineLabError(
                "target must be within (0, 1]"
            )
        if (
            type(max_rounds) is not int
            or not 1
            <= max_rounds
            <= 64
        ):
            raise GameEngineLabError(
                "max_rounds must be within [1, 64]"
            )
        current = session
        report = self.lab.evaluate(
            current.sandbox
        )
        rounds: list[
            ProjectEvolutionRound
        ] = []

        if _meets_target(
            report,
            target,
        ):
            return ProjectEvolutionResult(
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

        return ProjectEvolutionResult(
            current,
            report,
            tuple(rounds),
            _meets_target(
                report,
                target,
            ),
        )


def build_executable_game_project(
    era: EngineEra | str,
    gameplay_dialect: str | None = None,
    *,
    sources: Iterable[SourceAsset] | None = None,
    scripts: Iterable[ScriptSource] | None = None,
    physics: PhysicsSceneSource | None = None,
    audio: AudioSceneSource | None = None,
    animation: AnimationSceneSource | None = None,
    navigation: NavigationSource | None = None,
) -> GameProjectSandbox:
    return ExecutableGameProjectLab().create(
        era,
        gameplay_dialect,
        sources=sources,
        scripts=scripts,
        physics=physics,
        audio=audio,
        animation=animation,
        navigation=navigation,
    )
