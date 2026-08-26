"""Tests for the resilience fortress."""

from skeleton.resilience import ResilienceFortress


class TestFortress:
    def test_process_input_returns_report(self):
        fortress = ResilienceFortress()
        sanitized, report = fortress.process_input("hello world", "user_1")
        assert isinstance(sanitized, str)
        assert report is not None
        stats = fortress.stats()
        assert "inputs_blocked" in stats

    def test_process_output_shape(self):
        fortress = ResilienceFortress()
        result = fortress.process_output("all good", "user_1", "what is 2+2?")
        assert "safe" in result
        assert "deliverable" in result
