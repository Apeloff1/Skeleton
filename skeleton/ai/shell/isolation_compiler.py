"""Compile AI plan effects into the existing shell IsolationRequirement."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skeleton.shells.ai.effects import EffectKind, EffectRegistry
from skeleton.shells.ai.risk import RiskAssessment, RiskBand
from skeleton.shells.ai.types import AIIntent, AIPlanProposal
from skeleton.shells.isolation import IsolationLevel, IsolationRequirement


@dataclass(frozen=True)
class AIIsolationDecision:
    requirement: IsolationRequirement
    effects: tuple[EffectKind, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "requirement": self.requirement.to_dict(),
            "effects": [item.value for item in self.effects],
            "reasons": list(self.reasons),
        }


class AIIsolationCompiler:
    """Derive a minimum isolation requirement from reviewed effects.

    This compiler is declarative. Enforcement still belongs to the lower shell
    isolation backend or sandbox implementation.
    """

    def __init__(
        self,
        effects: EffectRegistry,
        *,
        default_write_roots: tuple[str, ...] = (),
    ) -> None:
        roots = []
        for raw in default_write_roots:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                raise ValueError("AI isolation write roots must be absolute")
            roots.append(str(path.resolve(strict=False)))
        self.effects = effects
        self.default_write_roots = tuple(sorted(set(roots)))

    def compile(
        self,
        intent: AIIntent,
        proposal: AIPlanProposal,
        risk: RiskAssessment,
        *,
        requested_write_roots: tuple[str, ...] = (),
    ) -> AIIsolationDecision:
        observed: set[EffectKind] = set()
        reasons = []
        for action in proposal.actions:
            contract = self.effects.inspect(action.command)
            if contract is None:
                reasons.append(f"unknown effect contract for {action.command}")
                continue
            observed.update(contract.effects)

        high_risk_effects = {
            EffectKind.DELETE_FILESYSTEM,
            EffectKind.PACKAGE_CHANGE,
            EffectKind.SECRET_ACCESS,
            EffectKind.PRIVILEGED,
            EffectKind.DEPLOYMENT,
            EffectKind.EXTERNAL_SIDE_EFFECT,
        }
        if observed & high_risk_effects or risk.band in {
            RiskBand.HIGH,
            RiskBand.CRITICAL,
        }:
            level = IsolationLevel.SANDBOXED
            reasons.append("high-risk effect or risk band requires sandbox isolation")
        elif observed & {
            EffectKind.WRITE_FILESYSTEM,
            EffectKind.NETWORK,
            EffectKind.VCS_WRITE,
            EffectKind.PROCESS_CONTROL,
        }:
            level = IsolationLevel.WORKSPACE
            reasons.append("mutable or external effect requires workspace isolation")
        else:
            level = IsolationLevel.WORKSPACE
            reasons.append("read-only AI execution remains workspace isolated")

        has_write = bool(
            observed
            & {
                EffectKind.WRITE_FILESYSTEM,
                EffectKind.DELETE_FILESYSTEM,
                EffectKind.VCS_WRITE,
                EffectKind.PACKAGE_CHANGE,
            }
        )
        has_network = EffectKind.NETWORK in observed
        if has_network and not intent.constraint.allow_network:
            reasons.append("network effect conflicts with intent and remains disabled")
        if has_write and not intent.constraint.allow_writes:
            reasons.append("write effect conflicts with intent and source remains read-only")

        roots = []
        allowed_roots = tuple(Path(root) for root in self.default_write_roots)
        for raw in requested_write_roots:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                raise ValueError("requested AI isolation write roots must be absolute")
            resolved_path = path.resolve(strict=False)
            if not allowed_roots:
                raise ValueError("no AI isolation write roots are configured")
            try:
                permitted = any(
                    resolved_path == allowed
                    or resolved_path.is_relative_to(allowed)
                    for allowed in allowed_roots
                )
            except AttributeError:
                permitted = any(
                    resolved_path == allowed
                    or str(resolved_path).startswith(str(allowed) + "/")
                    for allowed in allowed_roots
                )
            if not permitted:
                raise ValueError("requested write root is outside configured AI root set")
            roots.append(str(resolved_path))

        effective_write = has_write and intent.constraint.allow_writes
        requirement = IsolationRequirement(
            level=level,
            require_private_tmp=True,
            require_clean_environment=True,
            require_readonly_source=not effective_write,
            allow_network=has_network and intent.constraint.allow_network,
            allow_home=False,
            allowed_write_roots=tuple(roots if effective_write else ()),
        )
        return AIIsolationDecision(
            requirement,
            tuple(sorted(observed, key=lambda item: item.value)),
            tuple(reasons),
        )
