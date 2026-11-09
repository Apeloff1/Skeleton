"""Tests for the intelligence orchestrator."""

from skeleton.intelligence import IntelligenceOrchestrator


class TestIntelligenceOrchestrator:
    def test_reason_empty_context(self):
        orch = IntelligenceOrchestrator()
        result = orch.reason("what happens next")
        assert "confidence" in result
        assert result["temporal"] is None or isinstance(result["temporal"], dict)

    def test_reason_with_events(self):
        orch = IntelligenceOrchestrator()
        result = orch.reason(
            "sequence",
            context={
                "events": [
                    {"id": "e1", "description": "boot", "timestamp": 1.0},
                    {"id": "e2", "description": "ready", "timestamp": 2.0},
                ],
                "predict_next": "boot",
            },
        )
        assert "temporal" in result
