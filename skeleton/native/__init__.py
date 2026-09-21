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
]
