from __future__ import annotations

from core.shift_supervisor.assurance_model_boundary import AssuranceModelBoundary


class TestAssuranceModelBoundary:
    def test_rejects_missing_actor(self) -> None:
        boundary = AssuranceModelBoundary()
        decision = boundary.admit(
            actor="",
            correlation_id="corr-1",
            operation="model.call",
            payload={"prompt": "test"},
        )
        assert decision.allowed is False
        assert decision.reason == "missing_actor"

    def test_rejects_missing_correlation(self) -> None:
        boundary = AssuranceModelBoundary()
        decision = boundary.admit(
            actor="supervisor",
            correlation_id="",
            operation="model.call",
            payload={"prompt": "test"},
        )
        assert decision.allowed is False
        assert decision.reason == "missing_correlation_id"

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
        assert first.assurance.digest == second.assurance.digest
