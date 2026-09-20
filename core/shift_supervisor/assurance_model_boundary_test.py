from __future__ import annotations

import pytest

from core.shift_supervisor.assurance_model_boundary import AssuranceModelBoundary


class TestAssuranceModelBoundary:
    def test_requires_actor(self) -> None:
        boundary = AssuranceModelBoundary()
        with pytest.raises(ValueError):
            boundary.admit(
                actor="",
                correlation_id="corr-1",
                operation="model.call",
                payload={"prompt": "test"},
            )

    def test_requires_correlation(self) -> None:
        boundary = AssuranceModelBoundary()
        with pytest.raises(ValueError):
            boundary.admit(
                actor="supervisor",
                correlation_id="",
                operation="model.call",
                payload={"prompt": "test"},
            )

    def test_stable_payload_identity(self) -> None:
        boundary = AssuranceModelBoundary()
        first = boundary.admit(
            actor="supervisor",
            correlation_id="corr-1",
            operation="model.call",
            payload={"b": 2, "a": 1},
        )
        second = boundary.admit(
            actor="supervisor",
            correlation_id="corr-1",
            operation="model.call",
            payload={"a": 1, "b": 2},
        )
        assert first.payload_digest == second.payload_digest
