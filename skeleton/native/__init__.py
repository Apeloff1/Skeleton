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

__all__ = [
    "AsmAcceleratorAbiError",
    "AsmAcceleratorError",
    "AsmAcceleratorPreflight",
    "AsmAcceleratorStatus",
    "AsmAcceleratorUnavailable",
    "AsmVectorAccelerator",
    "get_default_asm_accelerator",
    "normalize_architecture",
]
