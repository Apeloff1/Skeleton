"""Hardware-bounded Jeeves planning profiles over one installed GGUF.

A profile configures the EXISTING StrictJeevesAgentRuntime; it never spawns
another provider or weakens source rights, tool grants, memory custody,
SQLite receipts or model-call budgets. Advanced mode enables finite
verification/replanning only when there is enough operator-admitted capacity.

A model may recommend an alternative workflow but cannot select or increase
this host-owned profile. Both profiles remain fail-on-unresolved.
"""
from __future__ import annotations

from dataclasses import dataclass

from skeleton.jeeves.agent.runtime import AgentConfig

PROFILE_GUARDED = "guarded"
PROFILE_ADVANCED = "advanced"
PROFILES = frozenset((PROFILE_GUARDED, PROFILE_ADVANCED))


class NativeProfileHold(ValueError):
    """Selected planner topology cannot fit the admitted native model budget."""


@dataclass(frozen=True, slots=True)
class NativePlanningProfile:
    name: str
    config: AgentConfig
    maximum_plan_steps: int
    maximum_replans: int
    grounding_repairs: int
    independent_model_verification_requested: bool
    evidence_verification_requested: bool
    stage_memory: bool

    def __post_init__(self):
        if (
            type(self.name) is not str
            or self.name not in PROFILES
            or type(self.config) is not AgentConfig
            or type(self.maximum_plan_steps) is not int
            or self.maximum_plan_steps != self.config.maximum_plan_steps
            or type(self.maximum_replans) is not int
            or self.maximum_replans != self.config.maximum_replans
            or type(self.grounding_repairs) is not int
            or self.grounding_repairs != self.config.grounding_repairs
            or type(self.independent_model_verification_requested) is not bool
            or self.independent_model_verification_requested is not self.config.enable_model_verification
            or type(self.evidence_verification_requested) is not bool
            or self.evidence_verification_requested is not self.config.verify_read_only_with_model
            or self.stage_memory is not False
            or self.config.stage_memory_candidates is not False
            or self.config.stage_success_episode is not False
            or self.config.fail_on_unresolved is not True
        ):
            raise NativeProfileHold("profile cannot prove strict source/model budget")

    def to_public(self) -> dict[str, object]:
        """Requested policy, not a claim that model verification succeeded."""
        return {
            "schema": "jeeves.desktop.native-planning-profile.v1",
            "profile": self.name,
            "maximum_plan_steps": self.maximum_plan_steps,
            "maximum_replans": self.maximum_replans,
            "grounding_repairs": self.grounding_repairs,
            "model_verification_requested": self.independent_model_verification_requested,
            "evidence_verification_requested": self.evidence_verification_requested,
            "persistent_memory_promotion_enabled": False,
            "tool_grants_changed_by_profile": False,
            "additional_provider_started": False,
            "model_verification_executed_proved": False,
            "release_certified": False,
        }


def choose_profile(
    *,
    name: str,
    native_max_output_tokens: int,
    maximum_steps: int,
    maximum_model_calls: int,
    maximum_wall_seconds: int,
    signed_source_available: bool,
) -> NativePlanningProfile:
    if type(name) is not str or name not in PROFILES:
        raise NativeProfileHold("unsupported operator-selected native planning topology")
    for label, value, lo, hi in (
        ("native output ceiling", native_max_output_tokens, 1, 8192),
        ("step budget", maximum_steps, 1, 64),
        ("model call budget", maximum_model_calls, 1, 64),
        ("wall budget", maximum_wall_seconds, 1, 600),
    ):
        if type(value) is not int or not lo <= value <= hi:
            raise NativeProfileHold("invalid finite planning " + label)
    if type(signed_source_available) is not bool:
        raise NativeProfileHold("explicit signed-source capability bit required")

    if name == PROFILE_ADVANCED:
        if maximum_steps < 4 or maximum_model_calls < 6:
            raise NativeProfileHold(
                "advanced verification requires at least 4 steps and 6 native calls"
            )
        plan_steps = min(32, maximum_steps)
        replans = min(2, max(0, (maximum_model_calls - 4) // 2))
        repairs = 1 if maximum_model_calls >= 8 else 0
        verify_model = True
        verify_read_only = signed_source_available and maximum_model_calls >= 8
        # The same native output ceiling bounds every phase. Smaller prompt
        # envelopes cap verifier and step work, not override backend context.
        planner_tokens = native_max_output_tokens
        step_tokens = native_max_output_tokens
        verify_tokens = max(1, min(native_max_output_tokens, max(64, native_max_output_tokens // 2)))
        final_tokens = native_max_output_tokens
    else:
        plan_steps = min(4, maximum_steps)
        replans = 0
        repairs = 0
        verify_model = False
        verify_read_only = False
        planner_tokens = native_max_output_tokens
        step_tokens = native_max_output_tokens
        verify_tokens = native_max_output_tokens
        final_tokens = native_max_output_tokens

    policy = AgentConfig(
        planner_max_tokens=planner_tokens,
        step_max_tokens=step_tokens,
        verifier_max_tokens=verify_tokens,
        final_max_tokens=final_tokens,
        model_temperature=0.0,
        maximum_plan_steps=plan_steps,
        maximum_replans=replans,
        grounding_repairs=repairs,
        enable_model_verification=verify_model,
        verify_read_only_with_model=verify_read_only,
        # No hidden memory-staging, tool-budget or provider escalation.
        stage_memory_candidates=False,
        stage_success_episode=False,
        bridge_verified_evidence=False,
        fail_on_unresolved=True,
    )
    return NativePlanningProfile(
        name=name,
        config=policy,
        maximum_plan_steps=plan_steps,
        maximum_replans=replans,
        grounding_repairs=repairs,
        independent_model_verification_requested=verify_model,
        evidence_verification_requested=verify_read_only,
        stage_memory=False,
    )


__all__ = [
    "PROFILE_GUARDED", "PROFILE_ADVANCED", "PROFILES",
    "NativeProfileHold", "NativePlanningProfile", "choose_profile",
]
