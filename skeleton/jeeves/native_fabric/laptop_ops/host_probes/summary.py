"""One read-only local host inventory for the operational Jeeves native path.

This is not a new bootstrap path or a native provider. It only composes
trusted OS observations and an eight-byte inert GGUF format hint.
Actual source rights, tokenizer matching, SQLite replay, physical device,
WSL2/cgroup limits and release remain independent guarded holds.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from skeleton.jeeves.native_fabric.laptop_ops.contracts import LaptopGateHold
from .cpu import CpuObservation, observe_cpu
from .memory import MemoryObservation, observe_ram
from .disk import DiskObservation, observe_disk
from .gguf_header import GGUFHeaderObservation, probe_gguf_header

_PERMANENT_HOLDS = (
    "actual installed model digest and tokenizer identity not verified by host probe",
    "independent model source rights and release permissions not checked",
    "WSL2, cgroup, GPU, native cancellation and sustained load not qualified",
    "no real native GGUF generation or durable SQLite replay witnessed",
    "final-head CI, security, malware, dependency and release checks pending",
)


@dataclass(frozen=True, slots=True)
class HostObservation:
    cpu: CpuObservation
    memory: MemoryObservation
    storage: DiskObservation
    gguf: GGUFHeaderObservation

    def __post_init__(self) -> None:
        if (type(self.cpu) is not CpuObservation
                or type(self.memory) is not MemoryObservation
                or type(self.storage) is not DiskObservation
                or type(self.gguf) is not GGUFHeaderObservation):
            raise LaptopGateHold("all four typed host observations required")

    @property
    def structural_preconditions_observed(self) -> bool:
        """Advisory observed fit, never a go/no-go activation authorization."""
        return (
            self.cpu.request_fits_observed_limit
            and self.memory.fits_observed_ram
            and self.storage.fits_observed_space
            and self.gguf.header_plausible
        )

    @property
    def observational_holds(self) -> tuple[str, ...]:
        holds: list[str] = []
        if not self.cpu.request_fits_observed_limit:
            holds.append("CPU process/affinity capacity missing or insufficient")
        if not self.memory.fits_observed_ram:
            holds.append("observed physical memory unavailable or insufficient")
        if not self.storage.fits_observed_space:
            holds.append("local state storage headroom unavailable or insufficient")
        if not self.gguf.header_plausible:
            holds.append("bounded GGUF format header unavailable or unsupported")
        return tuple(holds)

    def to_record(self) -> dict[str, object]:
        """Safe for stdout: never serialize path, installed bytes, or secret task."""
        return {
            "schema": "jeeves.laptop_ops.host_inventory.v1",
            "structural_preconditions_observed": self.structural_preconditions_observed,
            "cpu": self.cpu.to_record(),
            "physical_memory": self.memory.to_record(),
            "local_storage": self.storage.to_record(),
            "gguf_header": self.gguf.to_record(),
            "observational_holds": list(self.observational_holds),
            "independent_qualification_holds": list(_PERMANENT_HOLDS),
            "operator_observations_are_not_native_authority": True,
            "native_model_started": False,
            "real_native_generation_witnessed": False,
            "physical_device_qualified": False,
            "release_certified": False,
        }


def observe_host(
    *,
    model_file: Path,
    state_directory: Path,
    threads: int,
    reserved_memory_bytes: int,
    reserved_storage_bytes: int,
) -> HostObservation:
    """Observe all four requirements without loading model or mutating state.

    The canonical native startup separately rechecks model digest,
    installed receipts, rights, locked native resources and SQLite custody.
    """
    if not isinstance(model_file, Path) or not isinstance(state_directory, Path):
        raise LaptopGateHold("explicit local model and state paths required")
    cpu = observe_cpu(threads)
    memory = observe_ram(reserved_memory_bytes)
    storage = observe_disk(state_directory, reserved_storage_bytes)
    gguf = probe_gguf_header(model_file)
    return HostObservation(cpu, memory, storage, gguf)


__all__ = ["HostObservation", "observe_host"]
