"""Resource-gated execution policy for recovered source-assurance owners.

This is cooperative admission of known source suites, not a kernel resource
controller. It does not load a model, spawn arbitrary commands, or reserve
physical memory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import time

from skeleton.app.offline_cpu_budget import (
    CpuTopology, MemoryTopology, plan_cpu_workers, probe_cpu_topology, probe_memory_topology,
)
from skeleton.app.offline_energy_budget import (
    EnergyPolicy, PowerObservation, plan_energy_workers, probe_power,
)
from skeleton.app.offline_energy_hysteresis import EnergyHysteresis, HysteresisPolicy
from skeleton.app.recovered_evidence import EvidenceError, integer, digest
from skeleton.app.local_source_assurance import SUITES

GIB = 1024**3
MIB = 1024**2


@dataclass(frozen=True)
class AdmissionPolicy:
    max_workers: int = 4
    per_worker_mib: int = 256
    reserve_mib: int = 512
    interactive_cores: int = 1
    sample_count: int = 3
    interval_ms: int = 100
    max_probe_ns: int = 2_000_000_000
    max_age_ns: int = 2_000_000_000

    def __post_init__(self):
        integer(self.max_workers, 1, 32)
        integer(self.per_worker_mib, 32, 65536)
        integer(self.reserve_mib, 32, 65536)
        integer(self.interactive_cores, 0, 256)
        integer(self.sample_count, 3, 32)
        integer(self.interval_ms, 0, 1000)
        integer(self.max_probe_ns, 1, 30_000_000_000)
        integer(self.max_age_ns, 1, 30_000_000_000)


@dataclass(frozen=True)
class ResourceSample:
    started_ns: int
    observed_ns: int
    cpu: CpuTopology
    memory: MemoryTopology
    power: PowerObservation

    def __post_init__(self):
        integer(self.started_ns, 0, 2**63-1)
        integer(self.observed_ns, self.started_ns, 2**63-1)
        if not isinstance(self.cpu, CpuTopology) or not isinstance(self.memory, MemoryTopology):
            raise EvidenceError("invalid resource observation")
        if not isinstance(self.power, PowerObservation):
            raise EvidenceError("invalid power observation")


def observe():
    start = time.monotonic_ns()
    cpu = probe_cpu_topology()
    memory = probe_memory_topology()
    power = probe_power()
    return ResourceSample(start, time.monotonic_ns(), cpu, memory, power)


class AdmissionGate:
    def __init__(self, policy: AdmissionPolicy):
        if not isinstance(policy, AdmissionPolicy):
            raise EvidenceError("invalid admission policy")
        self.policy = policy
        self.hysteresis = EnergyHysteresis(HysteresisPolicy(
            recovery_samples=3, recovery_cooldown_ns=500_000_000,
            max_sample_age_ns=policy.max_age_ns, max_recovery_step=1,
        ))
        self.last_observation = None

    def step(self, sample, *, now_ns):
        if not isinstance(sample, ResourceSample):
            raise EvidenceError("measured sample required")
        integer(now_ns, 0, 2**63-1)
        if (sample.observed_ns > now_ns or now_ns-sample.observed_ns > self.policy.max_age_ns
                or sample.observed_ns-sample.started_ns > self.policy.max_probe_ns
                or (self.last_observation is not None and sample.started_ns < self.last_observation)):
            self.hysteresis = EnergyHysteresis(self.hysteresis.policy)
            self.last_observation = None
            return {"workers": 0, "reason": "stale_or_overlapping_probe",
                    "measurement_digest": digest(asdict(sample))}
        self.last_observation = sample.observed_ns
        cpu = plan_cpu_workers(
            sample.cpu, sample.memory, operator_max_workers=self.policy.max_workers,
            bytes_per_worker=self.policy.per_worker_mib*MIB,
            memory_reserve_bytes=self.policy.reserve_mib*MIB,
            interactive_cpu_reserve=min(self.policy.interactive_cores,sample.cpu.logical_visible),
            thermal_state="unknown",
        )
        energy = plan_energy_workers(cpu, sample.power, policy=EnergyPolicy())
        gate = self.hysteresis.step(energy, now_ns=now_ns, sampled_ns=sample.observed_ns)
        # Missing memory cannot authorize even one suite. Other telemetry is
        # bounded conservatively by the canonical CPU and energy owners.
        workers = gate.admitted_workers if sample.memory.available_bytes is not None else 0
        return {"workers":workers,"reason":gate.reason if workers else (
                    "memory_observation_missing" if sample.memory.available_bytes is None else gate.reason),
                "cpu_plan_digest":cpu.digest,"energy_plan_digest":energy.digest,
                "hysteresis_digest":gate.digest,"measurement_digest":digest(asdict(sample)),
                "measured_memory_available":sample.memory.available_bytes is not None,
                "sample_ns":sample.observed_ns}

    def checkpoint(self):
        return self.hysteresis.checkpoint()


def selected_suites(names):
    if (type(names) not in (list,tuple) or not names
            or any(type(n) is not str or n not in SUITES for n in names)
            or len(set(names))!=len(names)):
        raise EvidenceError("unknown or duplicate suite selection")
    return tuple(n for n in SUITES if n in names)
