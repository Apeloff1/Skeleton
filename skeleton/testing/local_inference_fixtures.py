"""Hermetic serving telemetry for functional local-runtime unit tests.

Real host-pressure probes have their own sampler/admission tests. Functional
tests should not become different workloads when a parallel image build uses
the host's RAM; production sampling and memory shedding remain unchanged.
"""

import pytest

from skeleton.ai.runtime.inference.adaptive_serving import ServingResources


@pytest.fixture(autouse=True)
def local_serving_resources(monkeypatch):
    monkeypatch.setattr(
        "skeleton.ai.runtime.inference.local.sample_serving_resources",
        lambda: ServingResources(
            memory_used_fraction=0.1,
            cpu_load_fraction=0.1,
            available_memory_bytes=8 * 1024**3,
            source="functional_test_fixture",
        ),
    )
