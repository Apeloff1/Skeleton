"""Resilience Fortress — unified interface — split from resilience_extended (v16.2)."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

from skeleton.kernel.events import DomainEvent, EventBus
from .types import ThreatLevel, ThreatReport
from .sanitiser import InputSanitiser
from .guardrails import OutputGuardrail
from .exfiltration import ExfiltrationDetector
from .shadow import ShadowMode

# =============================================================================
# RESILIENCE FORTRESS — MAIN INTERFACE
# =============================================================================

class ResilienceFortress:
    """
    Unified adversarial resilience interface.
    Composes sanitiser, guardrails, exfiltration detector, and shadow mode.
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self.sanitiser = InputSanitiser()
        self.guardrail = OutputGuardrail()
        self.exfiltration = ExfiltrationDetector(bus)
        self.shadow = ShadowMode(bus)
        self._bus = bus
        self._block_count = 0
        self._sanitize_count = 0

    def process_input(self, raw_input: str, user_id: str) -> Tuple[str, ThreatReport]:
        sanitized, report = self.sanitiser.sanitise(raw_input)
        if report.level == ThreatLevel.CRITICAL:
            self._block_count += 1
        elif report.level in (ThreatLevel.MALICIOUS, ThreatLevel.SUSPICIOUS):
            self._sanitize_count += 1
        return sanitized, report

    def process_output(
        self,
        output: str,
        user_id: str,
        query: str,
    ) -> Dict[str, Any]:
        guardrail_result = self.guardrail.evaluate(output)
        exfil_report = self.exfiltration.monitor_query(query, output, user_id)

        result = {
            "safe": guardrail_result["safe"] and exfil_report is None,
            "guardrail": guardrail_result,
            "exfiltration": exfil_report.to_dict() if exfil_report else None,
            "deliverable": (
                guardrail_result.get("redacted_output") or output
                if guardrail_result["safe"]
                else "[OUTPUT BLOCKED: SAFETY VIOLATION]"
            ),
        }

        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="resilience.output.processed",
                    payload={
                        "user_id": user_id,
                        "safe": result["safe"],
                        "guardrail_score": guardrail_result["score"],
                        "exfiltration_detected": exfil_report is not None,
                    },
                    correlation_id=f"res_{user_id}_{int(time.time())}",
                )
            )

        return result

    def stats(self) -> Dict[str, Any]:
        return {
            "inputs_blocked": self._block_count,
            "inputs_sanitized": self._sanitize_count,
            "exfiltration_queries": len(self.exfiltration._query_history),
            "suspicious_users": len(self.exfiltration._suspicious_patterns),
            "shadow_experiments": len(self.shadow._experiments),
            "active_experiments": sum(1 for e in self.shadow._experiments.values() if e.active),
        }
