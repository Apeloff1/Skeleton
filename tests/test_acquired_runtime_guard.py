from skeleton.acquired.runtime_guard import (
    AdaptiveGate,
    AdmissionVerdict,
    ChaosGovernor,
    DegradationRung,
    WorkPriority,
)
from skeleton.kernel.events import EventBus


class FakeClock:
    def __init__(self, value: float = 0.0):
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_adaptive_gate_sheds_bulk_before_control_reserve():
    clock = FakeClock()
    gate = AdaptiveGate(2, 0, clock=clock, control_reserve_ratio=0.5)

    assert gate.admit(WorkPriority.STANDARD) is AdmissionVerdict.ADMITTED
    assert gate.admit(WorkPriority.BULK) is AdmissionVerdict.ADMITTED
    assert gate.admit(WorkPriority.BULK) is AdmissionVerdict.SHED
    assert gate.admit(WorkPriority.CONTROL) is AdmissionVerdict.ADMITTED
    assert gate.admit(WorkPriority.CONTROL) is AdmissionVerdict.SHED

    stats = gate.stats()
    assert stats["admitted"] == 3
    assert stats["shed"] == 2


def test_adaptive_gate_refills_main_bucket_and_reserve():
    clock = FakeClock()
    gate = AdaptiveGate(2, 1, clock=clock, control_reserve_ratio=0.5)

    gate.admit()
    gate.admit()
    gate.admit(WorkPriority.CONTROL)
    assert gate.stats()["control_reserve_available"] == 0

    clock.advance(2.0)
    stats = gate.stats()
    assert stats["tokens_available"] == 2.0
    assert stats["control_reserve_available"] == 1


def test_chaos_governor_escalates_one_rung_at_a_time():
    clock = FakeClock()
    governor = ChaosGovernor(
        window_span=30,
        min_samples=4,
        escalate_at=0.25,
        recover_at=0.05,
        clock=clock,
    )

    for _ in range(3):
        assert governor.observe(False) is DegradationRung.NORMAL
    assert governor.observe(False) is DegradationRung.REDUCED_CACHING
    assert governor.observe(False) is DegradationRung.SHED_BACKGROUND
    assert governor.observe(False) is DegradationRung.STALE_READS
    assert governor.observe(False) is DegradationRung.EMERGENCY_READ_ONLY

    policy = governor.policy()
    assert policy.permits_writes is False
    assert policy.permits_background is False
    assert policy.should_cache is False
    assert policy.stale_reads_allowed is True


def test_chaos_governor_recovers_after_bad_window_expires():
    clock = FakeClock()
    governor = ChaosGovernor(
        window_span=10,
        min_samples=4,
        escalate_at=0.25,
        recover_at=0.05,
        clock=clock,
    )

    for _ in range(5):
        governor.observe(False)
    assert governor.rung >= DegradationRung.SHED_BACKGROUND

    clock.advance(11)
    for _ in range(3):
        governor.observe(True)
        assert governor.rung >= DegradationRung.SHED_BACKGROUND
    recovered = governor.observe(True)
    assert recovered < DegradationRung.SHED_BACKGROUND


def test_runtime_guard_emits_transition_and_admission_events():
    clock = FakeClock()
    bus = EventBus()
    observed = []
    bus.subscribe("acquired.runtime.*", observed.append)

    gate = AdaptiveGate(1, 0, clock=clock, bus=bus)
    gate.admit(WorkPriority.STANDARD)
    gate.admit(WorkPriority.BULK)

    governor = ChaosGovernor(
        min_samples=2,
        escalate_at=0.25,
        recover_at=0.05,
        clock=clock,
        bus=bus,
    )
    governor.observe(False)
    governor.observe(False)

    topics = [event.topic for event in observed]
    assert topics.count("acquired.runtime.admission") == 2
    assert "acquired.runtime.degradation" in topics
