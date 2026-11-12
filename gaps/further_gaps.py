"""Further gaps.
Observability, versioning, and recovery for local model and pipeline.
"""
from typing import Dict, Any

class FurtherGaps:
    def fill(self) -> Dict[str, Any]:
        return {
            "observability": {
                "logging": "Structured logs for each phase with timing and outcome",
                "metrics": "Track success rate, retry count, and quality scores",
                "tracing": "Run ID propagated through Jeeves to export"
            },
            "versioning": {
                "pipeline": "Semantic version on every export provenance",
                "logic": "Hash of applied how/why/when set recorded",
                "model": "Local model identifier and fallback used noted"
            },
            "recovery": {
                "partial": "Resume from last successful phase on interrupt",
                "rollback": "Discard incomplete export on validation failure",
                "user_message": "Clear explanation when fallback or recovery activates"
            },
            "further_gaps_filled": True
        }
