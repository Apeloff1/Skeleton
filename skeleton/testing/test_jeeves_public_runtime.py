from __future__ import annotations

import pytest

import skeleton.jeeves.agent as agent
from skeleton.jeeves.agent.frontier_runtime import FrontierJeevesAgentRuntime
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.runtime import JeevesAgentRuntime as LegacyRuntimeModuleClass
from skeleton.jeeves.agent.runtime_abstraction import GeneralizingRuntimeEpistemicGuard
from skeleton.jeeves.agent.strict_runtime import StrictJeevesAgentRuntime
from skeleton.jeeves.agent.tools import ToolExecutor, ToolRegistry


def _router() -> ProviderRouter:
    return ProviderRouter([DeterministicProvider([])])


def test_package_default_runtime_is_hardened_frontier_composition() -> None:
    assert agent.JeevesAgentRuntime is FrontierJeevesAgentRuntime
    assert agent.HardenedJeevesAgentRuntime is FrontierJeevesAgentRuntime
    assert agent.LegacyJeevesAgentRuntime is LegacyRuntimeModuleClass
    assert issubclass(FrontierJeevesAgentRuntime, StrictJeevesAgentRuntime)
    assert issubclass(StrictJeevesAgentRuntime, LegacyRuntimeModuleClass)


def test_default_runtime_constructs_generalizing_epistemic_guard() -> None:
    runtime = agent.JeevesAgentRuntime(provider_router=_router())

    assert isinstance(runtime, FrontierJeevesAgentRuntime)
    assert isinstance(runtime.runtime_guard, GeneralizingRuntimeEpistemicGuard)
    assert runtime.runtime_guard.tool_executor is runtime.tool_executor
    assert runtime.runtime_guard.policy.enabled is True


def test_legacy_runtime_is_explicit_not_package_default() -> None:
    legacy = agent.LegacyJeevesAgentRuntime(provider_router=_router())
    hardened = agent.JeevesAgentRuntime(provider_router=_router())

    assert type(legacy) is LegacyRuntimeModuleClass
    assert not hasattr(legacy, "runtime_guard")
    assert hasattr(hardened, "runtime_guard")


def test_explicit_custom_guard_is_respected_only_with_same_executor() -> None:
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    strict = StrictJeevesAgentRuntime(
        provider_router=_router(),
        tool_registry=registry,
        tool_executor=executor,
    )
    custom_guard = strict.runtime_guard

    runtime = FrontierJeevesAgentRuntime(
        provider_router=_router(),
        tool_registry=registry,
        tool_executor=executor,
        runtime_guard=custom_guard,
    )

    assert runtime.runtime_guard is custom_guard
    assert runtime.runtime_guard.tool_executor is runtime.tool_executor


def test_custom_guard_with_different_executor_is_rejected() -> None:
    strict = StrictJeevesAgentRuntime(provider_router=_router())
    custom_guard = strict.runtime_guard

    with pytest.raises(ValueError, match="must use this runtime's ToolExecutor"):
        FrontierJeevesAgentRuntime(
            provider_router=_router(),
            runtime_guard=custom_guard,
        )


def test_argument_abstractor_cannot_silently_override_explicit_guard() -> None:
    registry = ToolRegistry()
    executor = ToolExecutor(registry)
    strict = StrictJeevesAgentRuntime(
        provider_router=_router(),
        tool_registry=registry,
        tool_executor=executor,
    )
    custom_guard = strict.runtime_guard

    with pytest.raises(ValueError, match="cannot be combined"):
        FrontierJeevesAgentRuntime(
            provider_router=_router(),
            tool_registry=registry,
            tool_executor=executor,
            runtime_guard=custom_guard,
            argument_abstractor=agent.ArgumentAbstractor(),
        )