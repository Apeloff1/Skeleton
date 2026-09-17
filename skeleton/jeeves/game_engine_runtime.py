"""Unified executable game-engine router for Jeeves.

Callers choose an EngineEra and do not need to know whether that era is owned
by the legacy, transitional-3D, or modern runtime family. Each family keeps its
own historically appropriate implementation while sharing one create/evaluate/
improve boundary.
"""

from __future__ import annotations

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
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
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
