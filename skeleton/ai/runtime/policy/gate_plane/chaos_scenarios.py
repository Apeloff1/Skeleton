"""Chaos admission scenarios — Pack B matrix over rung × verb × path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from skeleton.gate_plane.admit import (
    AdmissionDecision,
    AdmissionMatrix,
    AdmissionOutcome,
    evaluate_admission,
)
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor, Rung


@dataclass(frozen=True)
class ChaosScenario:
    name: str
    path: str
    method: str
    attester: Optional[str]
    priority: int
    force_rung: Optional[str]
    gate_capacity: int
    expect: str

    def as_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "method": self.method,
            "attester": self.attester,
            "priority": self.priority,
            "force_rung": self.force_rung,
            "gate_capacity": self.gate_capacity,
            "expect": self.expect,
        }


def _force_rung(gov: ChaosGovernor, rung_name: Optional[str]) -> None:
    if not rung_name:
        return
    # Climb via observes; escalate_at=0 forces climb each min_samples window.
    target = {
        "normal": Rung.NORMAL,
        "reduced_caching": Rung.REDUCED_CACHING,
        "shed_background": Rung.SHED_BACKGROUND,
        "stale_reads": Rung.STALE_READS,
        "emergency_read_only": Rung.EMERGENCY_READ_ONLY,
    }[rung_name]
    # Direct set via private field for deterministic scenarios.
    with gov._lock:
        gov._rung = target


def run_scenario(scenario: ChaosScenario) -> Tuple[AdmissionDecision, bool]:
    gate = AdaptiveGate(capacity=scenario.gate_capacity, refill_per_sec=0)
    gov = ChaosGovernor(min_samples=1000)
    _force_rung(gov, scenario.force_rung)
    matrix = AdmissionMatrix(gate=gate, governor=gov)
    decision = evaluate_admission(
        path=scenario.path,
        method=scenario.method,
        attester=scenario.attester,
        priority=scenario.priority,
        matrix=matrix,
    )
    ok = decision.outcome.value == scenario.expect
    return decision, ok


SCENARIOS: Tuple[ChaosScenario, ...] = (
    ChaosScenario("s0000", "/", "GET", None, 0, None, 0, "open_bypass"),
    ChaosScenario("s0001", "/", "GET", 'gate-bot', 0, None, 0, "open_bypass"),
    ChaosScenario("s0002", "/", "GET", None, 0, None, 8, "open_bypass"),
    ChaosScenario("s0003", "/", "GET", 'gate-bot', 0, None, 8, "open_bypass"),
    ChaosScenario("s0004", "/", "GET", None, 0, None, 256, "open_bypass"),
    ChaosScenario("s0005", "/", "GET", 'gate-bot', 0, None, 256, "open_bypass"),
    ChaosScenario("s0006", "/", "GET", None, 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0007", "/", "GET", 'gate-bot', 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0008", "/", "GET", None, 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0009", "/", "GET", 'gate-bot', 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0010", "/", "GET", None, 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0011", "/", "GET", 'gate-bot', 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0012", "/", "GET", None, 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0013", "/", "GET", 'gate-bot', 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0014", "/", "GET", None, 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0015", "/", "GET", 'gate-bot', 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0016", "/", "GET", None, 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0017", "/", "GET", 'gate-bot', 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0018", "/", "GET", None, 1, None, 0, "open_bypass"),
    ChaosScenario("s0019", "/", "GET", 'gate-bot', 1, None, 0, "open_bypass"),
    ChaosScenario("s0020", "/", "GET", None, 1, None, 8, "open_bypass"),
    ChaosScenario("s0021", "/", "GET", 'gate-bot', 1, None, 8, "open_bypass"),
    ChaosScenario("s0022", "/", "GET", None, 1, None, 256, "open_bypass"),
    ChaosScenario("s0023", "/", "GET", 'gate-bot', 1, None, 256, "open_bypass"),
    ChaosScenario("s0024", "/", "GET", None, 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0025", "/", "GET", 'gate-bot', 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0026", "/", "GET", None, 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0027", "/", "GET", 'gate-bot', 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0028", "/", "GET", None, 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0029", "/", "GET", 'gate-bot', 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0030", "/", "GET", None, 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0031", "/", "GET", 'gate-bot', 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0032", "/", "GET", None, 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0033", "/", "GET", 'gate-bot', 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0034", "/", "GET", None, 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0035", "/", "GET", 'gate-bot', 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0036", "/", "GET", None, 5, None, 0, "open_bypass"),
    ChaosScenario("s0037", "/", "GET", 'gate-bot', 5, None, 0, "open_bypass"),
    ChaosScenario("s0038", "/", "GET", None, 5, None, 8, "open_bypass"),
    ChaosScenario("s0039", "/", "GET", 'gate-bot', 5, None, 8, "open_bypass"),
    ChaosScenario("s0040", "/", "GET", None, 5, None, 256, "open_bypass"),
    ChaosScenario("s0041", "/", "GET", 'gate-bot', 5, None, 256, "open_bypass"),
    ChaosScenario("s0042", "/", "GET", None, 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0043", "/", "GET", 'gate-bot', 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0044", "/", "GET", None, 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0045", "/", "GET", 'gate-bot', 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0046", "/", "GET", None, 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0047", "/", "GET", 'gate-bot', 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0048", "/", "GET", None, 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0049", "/", "GET", 'gate-bot', 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0050", "/", "GET", None, 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0051", "/", "GET", 'gate-bot', 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0052", "/", "GET", None, 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0053", "/", "GET", 'gate-bot', 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0054", "/", "POST", None, 0, None, 0, "open_bypass"),
    ChaosScenario("s0055", "/", "POST", 'gate-bot', 0, None, 0, "open_bypass"),
    ChaosScenario("s0056", "/", "POST", None, 0, None, 8, "open_bypass"),
    ChaosScenario("s0057", "/", "POST", 'gate-bot', 0, None, 8, "open_bypass"),
    ChaosScenario("s0058", "/", "POST", None, 0, None, 256, "open_bypass"),
    ChaosScenario("s0059", "/", "POST", 'gate-bot', 0, None, 256, "open_bypass"),
    ChaosScenario("s0060", "/", "POST", None, 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0061", "/", "POST", 'gate-bot', 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0062", "/", "POST", None, 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0063", "/", "POST", 'gate-bot', 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0064", "/", "POST", None, 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0065", "/", "POST", 'gate-bot', 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0066", "/", "POST", None, 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0067", "/", "POST", 'gate-bot', 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0068", "/", "POST", None, 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0069", "/", "POST", 'gate-bot', 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0070", "/", "POST", None, 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0071", "/", "POST", 'gate-bot', 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0072", "/", "POST", None, 1, None, 0, "open_bypass"),
    ChaosScenario("s0073", "/", "POST", 'gate-bot', 1, None, 0, "open_bypass"),
    ChaosScenario("s0074", "/", "POST", None, 1, None, 8, "open_bypass"),
    ChaosScenario("s0075", "/", "POST", 'gate-bot', 1, None, 8, "open_bypass"),
    ChaosScenario("s0076", "/", "POST", None, 1, None, 256, "open_bypass"),
    ChaosScenario("s0077", "/", "POST", 'gate-bot', 1, None, 256, "open_bypass"),
    ChaosScenario("s0078", "/", "POST", None, 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0079", "/", "POST", 'gate-bot', 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0080", "/", "POST", None, 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0081", "/", "POST", 'gate-bot', 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0082", "/", "POST", None, 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0083", "/", "POST", 'gate-bot', 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0084", "/", "POST", None, 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0085", "/", "POST", 'gate-bot', 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0086", "/", "POST", None, 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0087", "/", "POST", 'gate-bot', 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0088", "/", "POST", None, 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0089", "/", "POST", 'gate-bot', 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0090", "/", "POST", None, 5, None, 0, "open_bypass"),
    ChaosScenario("s0091", "/", "POST", 'gate-bot', 5, None, 0, "open_bypass"),
    ChaosScenario("s0092", "/", "POST", None, 5, None, 8, "open_bypass"),
    ChaosScenario("s0093", "/", "POST", 'gate-bot', 5, None, 8, "open_bypass"),
    ChaosScenario("s0094", "/", "POST", None, 5, None, 256, "open_bypass"),
    ChaosScenario("s0095", "/", "POST", 'gate-bot', 5, None, 256, "open_bypass"),
    ChaosScenario("s0096", "/", "POST", None, 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0097", "/", "POST", 'gate-bot', 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0098", "/", "POST", None, 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0099", "/", "POST", 'gate-bot', 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0100", "/", "POST", None, 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0101", "/", "POST", 'gate-bot', 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0102", "/", "POST", None, 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0103", "/", "POST", 'gate-bot', 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0104", "/", "POST", None, 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0105", "/", "POST", 'gate-bot', 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0106", "/", "POST", None, 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0107", "/", "POST", 'gate-bot', 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0108", "/", "PUT", None, 0, None, 0, "open_bypass"),
    ChaosScenario("s0109", "/", "PUT", 'gate-bot', 0, None, 0, "open_bypass"),
    ChaosScenario("s0110", "/", "PUT", None, 0, None, 8, "open_bypass"),
    ChaosScenario("s0111", "/", "PUT", 'gate-bot', 0, None, 8, "open_bypass"),
    ChaosScenario("s0112", "/", "PUT", None, 0, None, 256, "open_bypass"),
    ChaosScenario("s0113", "/", "PUT", 'gate-bot', 0, None, 256, "open_bypass"),
    ChaosScenario("s0114", "/", "PUT", None, 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0115", "/", "PUT", 'gate-bot', 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0116", "/", "PUT", None, 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0117", "/", "PUT", 'gate-bot', 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0118", "/", "PUT", None, 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0119", "/", "PUT", 'gate-bot', 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0120", "/", "PUT", None, 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0121", "/", "PUT", 'gate-bot', 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0122", "/", "PUT", None, 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0123", "/", "PUT", 'gate-bot', 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0124", "/", "PUT", None, 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0125", "/", "PUT", 'gate-bot', 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0126", "/", "PUT", None, 1, None, 0, "open_bypass"),
    ChaosScenario("s0127", "/", "PUT", 'gate-bot', 1, None, 0, "open_bypass"),
    ChaosScenario("s0128", "/", "PUT", None, 1, None, 8, "open_bypass"),
    ChaosScenario("s0129", "/", "PUT", 'gate-bot', 1, None, 8, "open_bypass"),
    ChaosScenario("s0130", "/", "PUT", None, 1, None, 256, "open_bypass"),
    ChaosScenario("s0131", "/", "PUT", 'gate-bot', 1, None, 256, "open_bypass"),
    ChaosScenario("s0132", "/", "PUT", None, 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0133", "/", "PUT", 'gate-bot', 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0134", "/", "PUT", None, 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0135", "/", "PUT", 'gate-bot', 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0136", "/", "PUT", None, 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0137", "/", "PUT", 'gate-bot', 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0138", "/", "PUT", None, 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0139", "/", "PUT", 'gate-bot', 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0140", "/", "PUT", None, 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0141", "/", "PUT", 'gate-bot', 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0142", "/", "PUT", None, 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0143", "/", "PUT", 'gate-bot', 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0144", "/", "PUT", None, 5, None, 0, "open_bypass"),
    ChaosScenario("s0145", "/", "PUT", 'gate-bot', 5, None, 0, "open_bypass"),
    ChaosScenario("s0146", "/", "PUT", None, 5, None, 8, "open_bypass"),
    ChaosScenario("s0147", "/", "PUT", 'gate-bot', 5, None, 8, "open_bypass"),
    ChaosScenario("s0148", "/", "PUT", None, 5, None, 256, "open_bypass"),
    ChaosScenario("s0149", "/", "PUT", 'gate-bot', 5, None, 256, "open_bypass"),
    ChaosScenario("s0150", "/", "PUT", None, 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0151", "/", "PUT", 'gate-bot', 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0152", "/", "PUT", None, 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0153", "/", "PUT", 'gate-bot', 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0154", "/", "PUT", None, 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0155", "/", "PUT", 'gate-bot', 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0156", "/", "PUT", None, 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0157", "/", "PUT", 'gate-bot', 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0158", "/", "PUT", None, 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0159", "/", "PUT", 'gate-bot', 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0160", "/", "PUT", None, 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0161", "/", "PUT", 'gate-bot', 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0162", "/", "PATCH", None, 0, None, 0, "open_bypass"),
    ChaosScenario("s0163", "/", "PATCH", 'gate-bot', 0, None, 0, "open_bypass"),
    ChaosScenario("s0164", "/", "PATCH", None, 0, None, 8, "open_bypass"),
    ChaosScenario("s0165", "/", "PATCH", 'gate-bot', 0, None, 8, "open_bypass"),
    ChaosScenario("s0166", "/", "PATCH", None, 0, None, 256, "open_bypass"),
    ChaosScenario("s0167", "/", "PATCH", 'gate-bot', 0, None, 256, "open_bypass"),
    ChaosScenario("s0168", "/", "PATCH", None, 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0169", "/", "PATCH", 'gate-bot', 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0170", "/", "PATCH", None, 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0171", "/", "PATCH", 'gate-bot', 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0172", "/", "PATCH", None, 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0173", "/", "PATCH", 'gate-bot', 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0174", "/", "PATCH", None, 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0175", "/", "PATCH", 'gate-bot', 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0176", "/", "PATCH", None, 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0177", "/", "PATCH", 'gate-bot', 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0178", "/", "PATCH", None, 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0179", "/", "PATCH", 'gate-bot', 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0180", "/", "PATCH", None, 1, None, 0, "open_bypass"),
    ChaosScenario("s0181", "/", "PATCH", 'gate-bot', 1, None, 0, "open_bypass"),
    ChaosScenario("s0182", "/", "PATCH", None, 1, None, 8, "open_bypass"),
    ChaosScenario("s0183", "/", "PATCH", 'gate-bot', 1, None, 8, "open_bypass"),
    ChaosScenario("s0184", "/", "PATCH", None, 1, None, 256, "open_bypass"),
    ChaosScenario("s0185", "/", "PATCH", 'gate-bot', 1, None, 256, "open_bypass"),
    ChaosScenario("s0186", "/", "PATCH", None, 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0187", "/", "PATCH", 'gate-bot', 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0188", "/", "PATCH", None, 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0189", "/", "PATCH", 'gate-bot', 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0190", "/", "PATCH", None, 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0191", "/", "PATCH", 'gate-bot', 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0192", "/", "PATCH", None, 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0193", "/", "PATCH", 'gate-bot', 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0194", "/", "PATCH", None, 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0195", "/", "PATCH", 'gate-bot', 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0196", "/", "PATCH", None, 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0197", "/", "PATCH", 'gate-bot', 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0198", "/", "PATCH", None, 5, None, 0, "open_bypass"),
    ChaosScenario("s0199", "/", "PATCH", 'gate-bot', 5, None, 0, "open_bypass"),
    ChaosScenario("s0200", "/", "PATCH", None, 5, None, 8, "open_bypass"),
    ChaosScenario("s0201", "/", "PATCH", 'gate-bot', 5, None, 8, "open_bypass"),
    ChaosScenario("s0202", "/", "PATCH", None, 5, None, 256, "open_bypass"),
    ChaosScenario("s0203", "/", "PATCH", 'gate-bot', 5, None, 256, "open_bypass"),
    ChaosScenario("s0204", "/", "PATCH", None, 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0205", "/", "PATCH", 'gate-bot', 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0206", "/", "PATCH", None, 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0207", "/", "PATCH", 'gate-bot', 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0208", "/", "PATCH", None, 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0209", "/", "PATCH", 'gate-bot', 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0210", "/", "PATCH", None, 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0211", "/", "PATCH", 'gate-bot', 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0212", "/", "PATCH", None, 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0213", "/", "PATCH", 'gate-bot', 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0214", "/", "PATCH", None, 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0215", "/", "PATCH", 'gate-bot', 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0216", "/", "DELETE", None, 0, None, 0, "open_bypass"),
    ChaosScenario("s0217", "/", "DELETE", 'gate-bot', 0, None, 0, "open_bypass"),
    ChaosScenario("s0218", "/", "DELETE", None, 0, None, 8, "open_bypass"),
    ChaosScenario("s0219", "/", "DELETE", 'gate-bot', 0, None, 8, "open_bypass"),
    ChaosScenario("s0220", "/", "DELETE", None, 0, None, 256, "open_bypass"),
    ChaosScenario("s0221", "/", "DELETE", 'gate-bot', 0, None, 256, "open_bypass"),
    ChaosScenario("s0222", "/", "DELETE", None, 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0223", "/", "DELETE", 'gate-bot', 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0224", "/", "DELETE", None, 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0225", "/", "DELETE", 'gate-bot', 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0226", "/", "DELETE", None, 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0227", "/", "DELETE", 'gate-bot', 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0228", "/", "DELETE", None, 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0229", "/", "DELETE", 'gate-bot', 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0230", "/", "DELETE", None, 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0231", "/", "DELETE", 'gate-bot', 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0232", "/", "DELETE", None, 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0233", "/", "DELETE", 'gate-bot', 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0234", "/", "DELETE", None, 1, None, 0, "open_bypass"),
    ChaosScenario("s0235", "/", "DELETE", 'gate-bot', 1, None, 0, "open_bypass"),
    ChaosScenario("s0236", "/", "DELETE", None, 1, None, 8, "open_bypass"),
    ChaosScenario("s0237", "/", "DELETE", 'gate-bot', 1, None, 8, "open_bypass"),
    ChaosScenario("s0238", "/", "DELETE", None, 1, None, 256, "open_bypass"),
    ChaosScenario("s0239", "/", "DELETE", 'gate-bot', 1, None, 256, "open_bypass"),
    ChaosScenario("s0240", "/", "DELETE", None, 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0241", "/", "DELETE", 'gate-bot', 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0242", "/", "DELETE", None, 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0243", "/", "DELETE", 'gate-bot', 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0244", "/", "DELETE", None, 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0245", "/", "DELETE", 'gate-bot', 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0246", "/", "DELETE", None, 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0247", "/", "DELETE", 'gate-bot', 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0248", "/", "DELETE", None, 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0249", "/", "DELETE", 'gate-bot', 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0250", "/", "DELETE", None, 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0251", "/", "DELETE", 'gate-bot', 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0252", "/", "DELETE", None, 5, None, 0, "open_bypass"),
    ChaosScenario("s0253", "/", "DELETE", 'gate-bot', 5, None, 0, "open_bypass"),
    ChaosScenario("s0254", "/", "DELETE", None, 5, None, 8, "open_bypass"),
    ChaosScenario("s0255", "/", "DELETE", 'gate-bot', 5, None, 8, "open_bypass"),
    ChaosScenario("s0256", "/", "DELETE", None, 5, None, 256, "open_bypass"),
    ChaosScenario("s0257", "/", "DELETE", 'gate-bot', 5, None, 256, "open_bypass"),
    ChaosScenario("s0258", "/", "DELETE", None, 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0259", "/", "DELETE", 'gate-bot', 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0260", "/", "DELETE", None, 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0261", "/", "DELETE", 'gate-bot', 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0262", "/", "DELETE", None, 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0263", "/", "DELETE", 'gate-bot', 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0264", "/", "DELETE", None, 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0265", "/", "DELETE", 'gate-bot', 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0266", "/", "DELETE", None, 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0267", "/", "DELETE", 'gate-bot', 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0268", "/", "DELETE", None, 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0269", "/", "DELETE", 'gate-bot', 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0270", "/", "HEAD", None, 0, None, 0, "open_bypass"),
    ChaosScenario("s0271", "/", "HEAD", 'gate-bot', 0, None, 0, "open_bypass"),
    ChaosScenario("s0272", "/", "HEAD", None, 0, None, 8, "open_bypass"),
    ChaosScenario("s0273", "/", "HEAD", 'gate-bot', 0, None, 8, "open_bypass"),
    ChaosScenario("s0274", "/", "HEAD", None, 0, None, 256, "open_bypass"),
    ChaosScenario("s0275", "/", "HEAD", 'gate-bot', 0, None, 256, "open_bypass"),
    ChaosScenario("s0276", "/", "HEAD", None, 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0277", "/", "HEAD", 'gate-bot', 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0278", "/", "HEAD", None, 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0279", "/", "HEAD", 'gate-bot', 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0280", "/", "HEAD", None, 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0281", "/", "HEAD", 'gate-bot', 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0282", "/", "HEAD", None, 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0283", "/", "HEAD", 'gate-bot', 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0284", "/", "HEAD", None, 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0285", "/", "HEAD", 'gate-bot', 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0286", "/", "HEAD", None, 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0287", "/", "HEAD", 'gate-bot', 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0288", "/", "HEAD", None, 1, None, 0, "open_bypass"),
    ChaosScenario("s0289", "/", "HEAD", 'gate-bot', 1, None, 0, "open_bypass"),
    ChaosScenario("s0290", "/", "HEAD", None, 1, None, 8, "open_bypass"),
    ChaosScenario("s0291", "/", "HEAD", 'gate-bot', 1, None, 8, "open_bypass"),
    ChaosScenario("s0292", "/", "HEAD", None, 1, None, 256, "open_bypass"),
    ChaosScenario("s0293", "/", "HEAD", 'gate-bot', 1, None, 256, "open_bypass"),
    ChaosScenario("s0294", "/", "HEAD", None, 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0295", "/", "HEAD", 'gate-bot', 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0296", "/", "HEAD", None, 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0297", "/", "HEAD", 'gate-bot', 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0298", "/", "HEAD", None, 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0299", "/", "HEAD", 'gate-bot', 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0300", "/", "HEAD", None, 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0301", "/", "HEAD", 'gate-bot', 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0302", "/", "HEAD", None, 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0303", "/", "HEAD", 'gate-bot', 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0304", "/", "HEAD", None, 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0305", "/", "HEAD", 'gate-bot', 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0306", "/", "HEAD", None, 5, None, 0, "open_bypass"),
    ChaosScenario("s0307", "/", "HEAD", 'gate-bot', 5, None, 0, "open_bypass"),
    ChaosScenario("s0308", "/", "HEAD", None, 5, None, 8, "open_bypass"),
    ChaosScenario("s0309", "/", "HEAD", 'gate-bot', 5, None, 8, "open_bypass"),
    ChaosScenario("s0310", "/", "HEAD", None, 5, None, 256, "open_bypass"),
    ChaosScenario("s0311", "/", "HEAD", 'gate-bot', 5, None, 256, "open_bypass"),
    ChaosScenario("s0312", "/", "HEAD", None, 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0313", "/", "HEAD", 'gate-bot', 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0314", "/", "HEAD", None, 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0315", "/", "HEAD", 'gate-bot', 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0316", "/", "HEAD", None, 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0317", "/", "HEAD", 'gate-bot', 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0318", "/", "HEAD", None, 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0319", "/", "HEAD", 'gate-bot', 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0320", "/", "HEAD", None, 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0321", "/", "HEAD", 'gate-bot', 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0322", "/", "HEAD", None, 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0323", "/", "HEAD", 'gate-bot', 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0324", "/", "OPTIONS", None, 0, None, 0, "open_bypass"),
    ChaosScenario("s0325", "/", "OPTIONS", 'gate-bot', 0, None, 0, "open_bypass"),
    ChaosScenario("s0326", "/", "OPTIONS", None, 0, None, 8, "open_bypass"),
    ChaosScenario("s0327", "/", "OPTIONS", 'gate-bot', 0, None, 8, "open_bypass"),
    ChaosScenario("s0328", "/", "OPTIONS", None, 0, None, 256, "open_bypass"),
    ChaosScenario("s0329", "/", "OPTIONS", 'gate-bot', 0, None, 256, "open_bypass"),
    ChaosScenario("s0330", "/", "OPTIONS", None, 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0331", "/", "OPTIONS", 'gate-bot', 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0332", "/", "OPTIONS", None, 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0333", "/", "OPTIONS", 'gate-bot', 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0334", "/", "OPTIONS", None, 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0335", "/", "OPTIONS", 'gate-bot', 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0336", "/", "OPTIONS", None, 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0337", "/", "OPTIONS", 'gate-bot', 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0338", "/", "OPTIONS", None, 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0339", "/", "OPTIONS", 'gate-bot', 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0340", "/", "OPTIONS", None, 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0341", "/", "OPTIONS", 'gate-bot', 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0342", "/", "OPTIONS", None, 1, None, 0, "open_bypass"),
    ChaosScenario("s0343", "/", "OPTIONS", 'gate-bot', 1, None, 0, "open_bypass"),
    ChaosScenario("s0344", "/", "OPTIONS", None, 1, None, 8, "open_bypass"),
    ChaosScenario("s0345", "/", "OPTIONS", 'gate-bot', 1, None, 8, "open_bypass"),
    ChaosScenario("s0346", "/", "OPTIONS", None, 1, None, 256, "open_bypass"),
    ChaosScenario("s0347", "/", "OPTIONS", 'gate-bot', 1, None, 256, "open_bypass"),
    ChaosScenario("s0348", "/", "OPTIONS", None, 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0349", "/", "OPTIONS", 'gate-bot', 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0350", "/", "OPTIONS", None, 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0351", "/", "OPTIONS", 'gate-bot', 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0352", "/", "OPTIONS", None, 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0353", "/", "OPTIONS", 'gate-bot', 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0354", "/", "OPTIONS", None, 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0355", "/", "OPTIONS", 'gate-bot', 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0356", "/", "OPTIONS", None, 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0357", "/", "OPTIONS", 'gate-bot', 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0358", "/", "OPTIONS", None, 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0359", "/", "OPTIONS", 'gate-bot', 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0360", "/", "OPTIONS", None, 5, None, 0, "open_bypass"),
    ChaosScenario("s0361", "/", "OPTIONS", 'gate-bot', 5, None, 0, "open_bypass"),
    ChaosScenario("s0362", "/", "OPTIONS", None, 5, None, 8, "open_bypass"),
    ChaosScenario("s0363", "/", "OPTIONS", 'gate-bot', 5, None, 8, "open_bypass"),
    ChaosScenario("s0364", "/", "OPTIONS", None, 5, None, 256, "open_bypass"),
    ChaosScenario("s0365", "/", "OPTIONS", 'gate-bot', 5, None, 256, "open_bypass"),
    ChaosScenario("s0366", "/", "OPTIONS", None, 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0367", "/", "OPTIONS", 'gate-bot', 5, 'normal', 0, "open_bypass"),
    ChaosScenario("s0368", "/", "OPTIONS", None, 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0369", "/", "OPTIONS", 'gate-bot', 5, 'normal', 8, "open_bypass"),
    ChaosScenario("s0370", "/", "OPTIONS", None, 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0371", "/", "OPTIONS", 'gate-bot', 5, 'normal', 256, "open_bypass"),
    ChaosScenario("s0372", "/", "OPTIONS", None, 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0373", "/", "OPTIONS", 'gate-bot', 5, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0374", "/", "OPTIONS", None, 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0375", "/", "OPTIONS", 'gate-bot', 5, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0376", "/", "OPTIONS", None, 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0377", "/", "OPTIONS", 'gate-bot', 5, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0378", "/health", "GET", None, 0, None, 0, "open_bypass"),
    ChaosScenario("s0379", "/health", "GET", 'gate-bot', 0, None, 0, "open_bypass"),
    ChaosScenario("s0380", "/health", "GET", None, 0, None, 8, "open_bypass"),
    ChaosScenario("s0381", "/health", "GET", 'gate-bot', 0, None, 8, "open_bypass"),
    ChaosScenario("s0382", "/health", "GET", None, 0, None, 256, "open_bypass"),
    ChaosScenario("s0383", "/health", "GET", 'gate-bot', 0, None, 256, "open_bypass"),
    ChaosScenario("s0384", "/health", "GET", None, 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0385", "/health", "GET", 'gate-bot', 0, 'normal', 0, "open_bypass"),
    ChaosScenario("s0386", "/health", "GET", None, 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0387", "/health", "GET", 'gate-bot', 0, 'normal', 8, "open_bypass"),
    ChaosScenario("s0388", "/health", "GET", None, 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0389", "/health", "GET", 'gate-bot', 0, 'normal', 256, "open_bypass"),
    ChaosScenario("s0390", "/health", "GET", None, 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0391", "/health", "GET", 'gate-bot', 0, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0392", "/health", "GET", None, 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0393", "/health", "GET", 'gate-bot', 0, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0394", "/health", "GET", None, 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0395", "/health", "GET", 'gate-bot', 0, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0396", "/health", "GET", None, 1, None, 0, "open_bypass"),
    ChaosScenario("s0397", "/health", "GET", 'gate-bot', 1, None, 0, "open_bypass"),
    ChaosScenario("s0398", "/health", "GET", None, 1, None, 8, "open_bypass"),
    ChaosScenario("s0399", "/health", "GET", 'gate-bot', 1, None, 8, "open_bypass"),
    ChaosScenario("s0400", "/health", "GET", None, 1, None, 256, "open_bypass"),
    ChaosScenario("s0401", "/health", "GET", 'gate-bot', 1, None, 256, "open_bypass"),
    ChaosScenario("s0402", "/health", "GET", None, 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0403", "/health", "GET", 'gate-bot', 1, 'normal', 0, "open_bypass"),
    ChaosScenario("s0404", "/health", "GET", None, 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0405", "/health", "GET", 'gate-bot', 1, 'normal', 8, "open_bypass"),
    ChaosScenario("s0406", "/health", "GET", None, 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0407", "/health", "GET", 'gate-bot', 1, 'normal', 256, "open_bypass"),
    ChaosScenario("s0408", "/health", "GET", None, 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0409", "/health", "GET", 'gate-bot', 1, 'emergency_read_only', 0, "open_bypass"),
    ChaosScenario("s0410", "/health", "GET", None, 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0411", "/health", "GET", 'gate-bot', 1, 'emergency_read_only', 8, "open_bypass"),
    ChaosScenario("s0412", "/health", "GET", None, 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0413", "/health", "GET", 'gate-bot', 1, 'emergency_read_only', 256, "open_bypass"),
    ChaosScenario("s0414", "/health", "GET", None, 5, None, 0, "open_bypass"),
    ChaosScenario("s0415", "/health", "GET", 'gate-bot', 5, None, 0, "open_bypass"),
    ChaosScenario("s0416", "/health", "GET", None, 5, None, 8, "open_bypass"),
    ChaosScenario("s0417", "/health", "GET", 'gate-bot', 5, None, 8, "open_bypass"),
    ChaosScenario("s0418", "/health", "GET", None, 5, None, 256, "open_bypass"),
    ChaosScenario("s0419", "/health", "GET", 'gate-bot', 5, None, 256, "open_bypass"),
)


def scenario_catalog() -> List[Dict[str, object]]:
    return [s.as_dict() for s in SCENARIOS]


def run_all(limit: Optional[int] = None) -> Dict[str, object]:
    items = SCENARIOS if limit is None else SCENARIOS[:limit]
    passed = 0
    failed: List[str] = []
    for s in items:
        _dec, ok = run_scenario(s)
        if ok:
            passed += 1
        else:
            failed.append(s.name)
    return {"total": len(items), "passed": passed, "failed": failed}

def scenarios_for_root() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/"]

def scenarios_for_health() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/health"]

def scenarios_for_ready() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/ready"]

def scenarios_for_api_v1_health() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/health"]

def scenarios_for_api_v1_forge_kinds() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/forge/kinds"]

def scenarios_for_api_v1_forge_blueprint() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/forge/blueprint"]

def scenarios_for_api_v1_gameforge_run() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/gameforge/run"]

def scenarios_for_api_v1_swarm_tasks() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/swarm/tasks"]

def scenarios_for_api_v1_jeeves_ask() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/jeeves/ask"]

def scenarios_for_api_v1_memory_query() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/memory/query"]

def scenarios_for_api_v1_retrieval_feedback() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/retrieval/feedback"]

def scenarios_for_api_v1_cortex_status() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/cortex/status"]

def scenarios_for_cockpit() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/cockpit"]

def scenarios_for_docs() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/docs"]

def scenarios_for_openapi_json() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/openapi.json"]

def scenarios_for_api_fabric_events() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/fabric/events"]

def scenarios_for_api_legions_enlist() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/legions/enlist"]

def scenarios_for_api_governance_decide() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/governance/decide"]

def scenarios_for_api_cognition_beliefs() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/cognition/beliefs"]

def scenarios_for_api_lafs_put() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/lafs/put"]

def scenarios_for_api_studio_publish() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/studio/publish"]

def scenarios_for_api_court_convene() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/court/convene"]

def scenarios_for_api_v1_pipeline_npc() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/pipeline/npc"]

def scenarios_for_api_v1_intelligence_route() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/intelligence/route"]

def scenarios_for_api_v1_resilience_fortress() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/resilience/fortress"]

def scenarios_for_api_v1_context_compose() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/context/compose"]

def scenarios_for_api_v1_ledger_append() -> List[ChaosScenario]:
    return [s for s in SCENARIOS if s.path == "/api/v1/ledger/append"]
