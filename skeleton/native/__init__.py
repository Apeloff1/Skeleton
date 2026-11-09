"""Optional native acceleration surfaces for Skeleton."""

from .asm_accelerator import (
    AsmAcceleratorAbiError,
    AsmAcceleratorError,
    AsmAcceleratorPreflight,
    AsmAcceleratorStatus,
    AsmAcceleratorUnavailable,
    AsmVectorAccelerator,
    get_default_asm_accelerator,
    normalize_architecture,
)
from .registry import (
    NativeAcceleratorRegistry,
    NativeAcceleratorRegistryError,
    NativeAcceleratorRuntimeStatus,
    get_default_native_registry,
)
from .profile_gate import (
    AccelerationProfile,
    GateDecision,
    ProfileGate,
    ProfileGateError,
)

__all__ = [
    "AsmAcceleratorAbiError",
    "AsmAcceleratorError",
    "AsmAcceleratorPreflight",
    "AsmAcceleratorStatus",
    "AsmAcceleratorUnavailable",
    "AsmVectorAccelerator",
    "get_default_asm_accelerator",
    "normalize_architecture",
    "NativeAcceleratorRegistry",
    "NativeAcceleratorRegistryError",
    "NativeAcceleratorRuntimeStatus",
    "get_default_native_registry",
    "AccelerationProfile",
    "GateDecision",
    "ProfileGate",
    "ProfileGateError",
]
