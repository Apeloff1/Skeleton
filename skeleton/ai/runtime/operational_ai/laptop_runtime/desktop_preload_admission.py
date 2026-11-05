"""Fresh first-laptop GGUF preload admission against actual CPU/RAM/cgroups.

A suggested profile is not proof that the same memory still exists at model
activation time. When the desktop operator enables protected native startup,
this pure read-only gate measures current host RAM, cgroup free memory, CPU
affinity/quota and private SQLite disk before loading any GGUF backend.

It never reserves virtual RAM, reports GPU/VRAM capacity, silently reduces an
operator's chosen limits, invents model rights or certifies native inference.
The canonical source-approved installer and isolated inference supervisor
remain independent authorities after this gate.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .desktop_capacity_plan import (
    CgroupObservation, observe_cgroup, observe_cpu,
)
from .device_observer import inspect_device
from .installation import source_receipt
from .preflight import validate_native_shape

MIB = 1024 * 1024
GIB = 1024 * MIB
MAX_BYTES = (1 << 53) - 1


class PreloadAdmissionHold(ValueError):
    """Installed source and real host cannot support this exact native shape."""


@dataclass(frozen=True, slots=True)
class PreloadPolicy:
    minimum_ram_headroom_bytes: int = 512 * MIB
    minimum_state_free_bytes: int = 256 * MIB
    minimum_system_reserve_bytes: int = 1 * GIB
    estimated_kv_bytes_per_token: int = 256 * 1024
    minimum_native_scratch_bytes: int = 512 * MIB
    maximum_native_scratch_bytes: int = 2 * GIB
    thread_scratch_bytes: int = 16 * MIB

    def __post_init__(self):
        for name, low, high in (
            ("minimum_ram_headroom_bytes", 128*MIB, 8*GIB),
            ("minimum_state_free_bytes", 128*MIB, 8*GIB),
            ("minimum_system_reserve_bytes", 256*MIB, 8*GIB),
            ("estimated_kv_bytes_per_token", 64*1024, 2*MIB),
            ("minimum_native_scratch_bytes", 256*MIB, 4*GIB),
            ("maximum_native_scratch_bytes", 512*MIB, 8*GIB),
            ("thread_scratch_bytes", 4*MIB, 128*MIB),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise PreloadAdmissionHold("invalid bounded preload policy " + name)
        if self.maximum_native_scratch_bytes < self.minimum_native_scratch_bytes:
            raise PreloadAdmissionHold("native scratch ceiling below reserved floor")


@dataclass(frozen=True, slots=True)
class PreloadAdmission:
    model_sha256: str
    model_bytes: int
    measured_host_available_bytes: int
    measured_cgroup_available_bytes: int | None
    effective_available_bytes: int
    estimated_working_bytes: int
    reserved_system_bytes: int
    capacity_budget_bytes: int
    available_cpu_cores: int
    selected_cpu_threads: int
    measured_state_disk_free_bytes: int
    requested_context_tokens: int
    requested_output_tokens: int
    requested_gpu_layers: int
    cgroup_source: str

    def __post_init__(self):
        if (
            type(self.model_sha256) is not str
            or len(self.model_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.model_sha256)
        ):
            raise PreloadAdmissionHold("installed GGUF digest absent")
        for field in (
            "model_bytes", "measured_host_available_bytes",
            "effective_available_bytes", "estimated_working_bytes",
            "reserved_system_bytes", "capacity_budget_bytes",
            "measured_state_disk_free_bytes",
        ):
            number = getattr(self, field)
            if type(number) is not int or not 0 < number <= MAX_BYTES:
                raise PreloadAdmissionHold("untrusted measured resource quantity")
        if self.measured_cgroup_available_bytes is not None and (
            type(self.measured_cgroup_available_bytes) is not int
            or not 0 <= self.measured_cgroup_available_bytes <= MAX_BYTES
        ):
            raise PreloadAdmissionHold("malformed controller memory headroom")
        if (
            type(self.cgroup_source) is not str
            or self.cgroup_source not in (
                "cgroup-v2", "cgroup-v1", "no-cgroup-controller",
            )
            or self.effective_available_bytes != min(
                self.measured_host_available_bytes,
                self.measured_cgroup_available_bytes
                if self.measured_cgroup_available_bytes is not None
                else self.measured_host_available_bytes,
            )
            or type(self.available_cpu_cores) is not int
            or not 1 <= self.available_cpu_cores <= 4096
            or type(self.selected_cpu_threads) is not int
            or not 1 <= self.selected_cpu_threads <= self.available_cpu_cores
            or type(self.requested_context_tokens) is not int
            or not 128 <= self.requested_context_tokens <= 131072
            or type(self.requested_output_tokens) is not int
            or not 1 <= self.requested_output_tokens < self.requested_context_tokens
            or type(self.requested_gpu_layers) is not int
            or not 0 <= self.requested_gpu_layers <= 128
            or self.estimated_working_bytes > self.capacity_budget_bytes
            or self.estimated_working_bytes + self.reserved_system_bytes
            > self.effective_available_bytes
        ):
            raise PreloadAdmissionHold("reported native source cannot fit measured host")

    def to_public(self) -> dict[str, object]:
        """Diagnostic quantities only. Never include model/state private paths."""
        return {
            "schema": "jeeves.desktop.native-preload-admission.v1",
            "model_sha256": self.model_sha256,
            "model_bytes": self.model_bytes,
            "measured_host_available_bytes": self.measured_host_available_bytes,
            "measured_cgroup_available_bytes": self.measured_cgroup_available_bytes,
            "effective_available_bytes": self.effective_available_bytes,
            "estimated_working_bytes": self.estimated_working_bytes,
            "reserved_system_bytes": self.reserved_system_bytes,
            "capacity_budget_bytes": self.capacity_budget_bytes,
            "available_cpu_cores": self.available_cpu_cores,
            "selected_cpu_threads": self.selected_cpu_threads,
            "measured_state_disk_free_bytes": self.measured_state_disk_free_bytes,
            "requested_context_tokens": self.requested_context_tokens,
            "requested_output_tokens": self.requested_output_tokens,
            "requested_gpu_layers": self.requested_gpu_layers,
            "cgroup_source": self.cgroup_source,
            "preload_estimate_not_native_proof": True,
            "gpu_vram_verified": False,
            "real_native_generation_executed": False,
            "physical_device_qualified": False,
            "source_rights_independently_reviewed": False,
            "release_certified": False,
        }


def evaluate_preload(
    installed: object,
    host: object,
    controller: CgroupObservation,
    *,
    available_cores: int,
    n_ctx: int,
    max_new_tokens: int,
    n_threads: int,
    gpu_layers: int,
    capacity_budget_bytes: int,
    inference_ms: int = 90000,
    policy: PreloadPolicy | None = None,
) -> PreloadAdmission:
    """Pure finite decision from actual independently observed values.

    This is the *last* read-only memory fit check before actual model loader.
    All unknown, untyped, negative or contradictory observations hold rather
    than automatically requesting more swap/virtual RAM.
    """
    from skeleton.ai.runtime.operational_ai.deployment.install.doctor import (
        InstalledModelReport,
    )
    checked = PreloadPolicy() if policy is None else policy
    if type(checked) is not PreloadPolicy:
        raise PreloadAdmissionHold("typed native preload reserve policy required")
    validate_native_shape(
        n_ctx=n_ctx, max_new_tokens=max_new_tokens,
        n_threads=n_threads, gpu_layers=gpu_layers,
        capacity_budget_bytes=capacity_budget_bytes,
        inference_ms=inference_ms,
    )
    if (
        type(installed) is not InstalledModelReport
        or installed.content_verified is not True
        or installed.rights_approved is not True
        or installed.release_certified is not False
        or type(host) is not dict
        or host.get("schema") != "laptop-device-observation.v1"
        or host.get("measurement_only") is not True
        or host.get("qualified_device") is not False
        or type(controller) is not CgroupObservation
        or type(available_cores) is not int
        or not 1 <= available_cores <= 4096
    ):
        raise PreloadAdmissionHold("actual installed source and host observation required")

    size = installed.model_bytes
    ram = host.get("memory_available_bytes")
    disk = host.get("state_storage_available_bytes")
    free_controller = controller.memory_available_bytes
    cpu_controller = controller.cpu_quota_cores
    for label, n in (
        ("installed GGUF bytes", size),
        ("host RAM", ram),
        ("state disk", disk),
    ):
        if type(n) is not int or n < 0 or n > MAX_BYTES:
            raise PreloadAdmissionHold("untrusted live " + label)
    if size < 1 or ram < 1:
        raise PreloadAdmissionHold("no actual native model bytes or host memory")
    if disk < checked.minimum_state_free_bytes:
        raise PreloadAdmissionHold("state disk below private SQLite safety floor")
    if free_controller is not None:
        if type(free_controller) is not int or free_controller < 0:
            raise PreloadAdmissionHold("unknown cgroup memory headroom")
    effective_ram = min(
        ram, free_controller if free_controller is not None else ram,
    )
    available_cpu = min(
        available_cores,
        cpu_controller if cpu_controller is not None else available_cores,
    )
    if type(available_cpu) is not int or not 1 <= available_cpu <= 4096:
        raise PreloadAdmissionHold("no measured CPU controller capacity")
    if n_threads > available_cpu:
        raise PreloadAdmissionHold("native threads exceed observed CPU quota/affinity")

    reserved_system = max(
        checked.minimum_system_reserve_bytes, effective_ram // 8,
    )
    scratch = max(
        checked.minimum_native_scratch_bytes,
        min(checked.maximum_native_scratch_bytes, size // 3),
    )
    # Conservative estimate, never an inference shape proof. Every token
    # reserves a finite K/V planning allowance, and threads hold separate
    # CPU-side scratch before any possible GPU offload can be discounted.
    estimated_kv = max(512*MIB, n_ctx * checked.estimated_kv_bytes_per_token)
    estimated = size + scratch + estimated_kv + n_threads * checked.thread_scratch_bytes

    if effective_ram < checked.minimum_ram_headroom_bytes:
        raise PreloadAdmissionHold("actual effective native RAM below safety floor")
    if estimated + reserved_system > effective_ram:
        raise PreloadAdmissionHold("GGUF/attention/scratch cannot fit current effective RAM")
    if estimated > capacity_budget_bytes:
        raise PreloadAdmissionHold("selected capacity budget cannot hold native working set")

    return PreloadAdmission(
        model_sha256=installed.model_sha256,
        model_bytes=size,
        measured_host_available_bytes=ram,
        measured_cgroup_available_bytes=free_controller,
        effective_available_bytes=effective_ram,
        estimated_working_bytes=estimated,
        reserved_system_bytes=reserved_system,
        capacity_budget_bytes=capacity_budget_bytes,
        available_cpu_cores=available_cpu,
        selected_cpu_threads=n_threads,
        measured_state_disk_free_bytes=disk,
        requested_context_tokens=n_ctx,
        requested_output_tokens=max_new_tokens,
        requested_gpu_layers=gpu_layers,
        cgroup_source=controller.source,
    )


def check_fresh_native_preload(
    *, model_root: str | Path, state_dir: str | Path,
    n_ctx: int, max_new_tokens: int, n_threads: int,
    gpu_layers: int, capacity_budget_bytes: int,
    inference_ms: int = 90000,
) -> PreloadAdmission:
    """Measure installed real-source rights, RAM, disk and CPU before GGUF."""
    from .desktop_provision import private_path

    model = source_receipt(private_path(model_root), require_rights=True)
    state = private_path(state_dir)
    return evaluate_preload(
        model, inspect_device(state), observe_cgroup(),
        available_cores=observe_cpu(), n_ctx=n_ctx,
        max_new_tokens=max_new_tokens, n_threads=n_threads,
        gpu_layers=gpu_layers,
        capacity_budget_bytes=capacity_budget_bytes,
        inference_ms=inference_ms,
    )


def verify_public_preload_receipt(
    value: object, *,
    expected_model_sha256: str,
    requested_context_tokens: int,
    requested_output_tokens: int,
    requested_cpu_threads: int,
    requested_gpu_layers: int,
    requested_capacity_budget_bytes: int,
) -> PreloadAdmission:
    """Refuse a native child that claims a different source/resource admission.

    A child response is not a trusted estimator. Require exact typed public
    schema and reconstruct the immutable finite observation before comparing
    it to the operator's original config and the observed live GGUF digest.
    """
    if type(value) is not dict or value.get("schema") != (
        "jeeves.desktop.native-preload-admission.v1"
    ):
        raise PreloadAdmissionHold("native startup omitted signed resource shape")
    flags = {
        "preload_estimate_not_native_proof": True,
        "gpu_vram_verified": False,
        "real_native_generation_executed": False,
        "physical_device_qualified": False,
        "source_rights_independently_reviewed": False,
        "release_certified": False,
    }
    for name, expected in flags.items():
        if value.get(name) is not expected:
            raise PreloadAdmissionHold("native startup resource proof overstated")
    fields = tuple(PreloadAdmission.__dataclass_fields__)
    keys = {"schema", *fields, *flags}
    if set(value) != keys:
        raise PreloadAdmissionHold("unexpected native resource observation fields")
    try:
        verified = PreloadAdmission(**{
            name: value[name] for name in fields
        })
    except (ValueError, TypeError, PreloadAdmissionHold) as exc:
        raise PreloadAdmissionHold("malformed native resource admission receipt") from exc
    if (
        verified.model_sha256 != expected_model_sha256
        or verified.requested_context_tokens != requested_context_tokens
        or verified.requested_output_tokens != requested_output_tokens
        or verified.selected_cpu_threads != requested_cpu_threads
        or verified.requested_gpu_layers != requested_gpu_layers
        or verified.capacity_budget_bytes != requested_capacity_budget_bytes
        or verified.to_public() != value
    ):
        raise PreloadAdmissionHold(
            "child resource claims differ from operator's installed GGUF request",
        )
    return verified


__all__ = [
    "PreloadAdmissionHold", "PreloadPolicy", "PreloadAdmission",
    "evaluate_preload", "check_fresh_native_preload",
    "verify_public_preload_receipt",
]
