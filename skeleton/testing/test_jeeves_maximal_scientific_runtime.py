from __future__ import annotations

import json

import pytest

from skeleton.jeeves.agent.interpretive_science import ScientificLensLab
from skeleton.jeeves.agent.memory import MemoryNamespace
from skeleton.jeeves.agent.provider import DeterministicProvider, ProviderRouter
from skeleton.jeeves.agent.scientific_runtime import (
    MaximalScientificJeevesRuntime,
    ScientificJeevesRuntime,
)


def _runtime(cls):
    provider = DeterministicProvider(("unused",))
    return cls(provider_router=ProviderRouter((provider,)))


def test_maximal_scientific_runtime_expands_registry_without_changing_default() -> None:
    ordinary = _runtime(ScientificJeevesRuntime)
    maximal = _runtime(MaximalScientificJeevesRuntime)

    ordinary_keys = {item.key for item in ordinary.nuance_runtime.semantic_registry.all()}
    maximal_keys = {item.key for item in maximal.nuance_runtime.semantic_registry.all()}

    assert "scalar_implicature" not in ordinary_keys
    assert "scalar_implicature" in maximal_keys
    assert len(maximal_keys) > len(ordinary_keys)
    assert ordinary.scientific_summary()["maximal_semantics_enabled"] is False
    assert maximal.scientific_summary()["maximal_semantics_enabled"] is True
    assert (
        maximal.scientific_summary()["semantic_lens_count"]
        == len(maximal_keys)
    )


def test_maximal_runtime_uses_wider_bounded_lens_policy() -> None:
    runtime = _runtime(MaximalScientificJeevesRuntime)

    assert runtime.nuance_runtime.policy.max_lenses == 28
    assert runtime.nuance_runtime.policy.max_lenses_per_family == 5
    assert runtime.nuance_runtime.policy.minimum_rare_lenses_when_supported == 3


def test_maximal_runtime_routes_extreme_lens_with_governance_metadata() -> None:
    runtime = _runtime(MaximalScientificJeevesRuntime)
    namespace = MemoryNamespace("tenant", "user", "workspace", "session")
    frame = runtime.nuance_runtime.prepare(
        namespace,
        "Some outcomes may be possible, but the stronger claim was not asserted.",
        context_tags=("pragmatics",),
        requested_lenses=("scalar_implicature",),
        capture_interaction=False,
    )

    selected = {item.key for item in frame.lens_selection.lenses}
    assert "scalar_implicature" in selected
    assert frame.lens_governance is not None
    record = frame.lens_governance.record_for("scalar_implicature")
    assert record is not None
    assert record.declared_maturity == "empirical"
    assert record.transfer_warning
    assert record.lineage
    assert record.decision.factual_assertion_authorized is False
    assert record.decision.causal_assertion_authorized is False


def test_maximal_workbench_exposes_rare_lens_science_audit() -> None:
    runtime = _runtime(MaximalScientificJeevesRuntime)
    namespace = MemoryNamespace("tenant", "user", "workspace", "session")
    frame = runtime.nuance_runtime.prepare(
        namespace,
        "Some outcomes may be possible, but the stronger claim was not asserted.",
        context_tags=("pragmatics",),
        requested_lenses=("scalar_implicature",),
        capture_interaction=False,
    )

    section = runtime.scientific_context._workbench_section(frame)
    payload = json.loads(section.content)
    scalar = next(
        row for row in payload["lenses"]
        if row["key"] == "scalar_implicature"
    )

    assert scalar["declared_maturity"] == "empirical"
    assert scalar["transfer_warning"]
    assert scalar["lineage"]
    assert scalar["scientific_grade"] == "interpretive"
    assert scalar["factual_assertion_authorized"] is False
    assert scalar["causal_assertion_authorized"] is False
    assert payload["lens_governance_fingerprint"] == frame.lens_governance.fingerprint


def test_scientific_runtimes_can_share_one_lens_science_ledger() -> None:
    lab = ScientificLensLab()
    first_provider = DeterministicProvider(("unused",))
    second_provider = DeterministicProvider(("unused",))
    first = ScientificJeevesRuntime(
        provider_router=ProviderRouter((first_provider,)),
        lens_lab=lab,
    )
    second = MaximalScientificJeevesRuntime(
        provider_router=ProviderRouter((second_provider,)),
        lens_lab=lab,
    )

    assert first.lens_lab is lab
    assert second.lens_lab is lab
    assert first.nuance_runtime.lens_lab is lab
    assert second.nuance_runtime.lens_lab is lab
    assert (
        first.scientific_summary()["lens_science"]["lens_lab_fingerprint"]
        == second.scientific_summary()["lens_science"]["lens_lab_fingerprint"]
    )


def test_maximal_wrapper_owns_mode_flag() -> None:
    provider = DeterministicProvider(("unused",))
    with pytest.raises(TypeError, match="owns maximal_semantics"):
        MaximalScientificJeevesRuntime(
            provider_router=ProviderRouter((provider,)),
            maximal_semantics=False,
        )
