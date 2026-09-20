# Skeleton Assembly vector microkernels

This directory contains the hand-written Assembly kernels used by
`skeleton.native.asm_accelerator`.

The native plane is intentionally small and opt-in. Python keeps ownership of
data validation, orchestration, fallback behavior, and domain semantics. The
shared library only implements numeric kernels behind a versioned C ABI.

## Supported ABIs

| Source | Platform ABI | Vector ISA |
| --- | --- | --- |
| `x86_64.S` | Linux System V AMD64 | SSE/SSE2 baseline |
| `aarch64.S` | Linux AAPCS64 | Advanced SIMD/NEON baseline |

Both architectures export:

- `skeleton_asm_abi_version() -> uint32`
- `skeleton_asm_dot_f32(left, right, length) -> float`
- `skeleton_asm_l2_sq_f32(left, right, length) -> float`

The x86-64 and AArch64 kernels process four float32 lanes per loop and finish
remaining elements with scalar instructions. They do not require AVX, AVX2,
SVE, or CPU-specific dispatch.

## Build

The Python loader never builds code on import. Build explicitly:

```bash
python scripts/build_asm_accelerator.py --self-test
```

or in Python:

```python
from skeleton.native import AsmVectorAccelerator

path = AsmVectorAccelerator.build()
accelerator = AsmVectorAccelerator(path)
```

`CC` may select the compiler. `SKELETON_ASM_CACHE_DIR` changes the default
build cache and `SKELETON_ASM_LIBRARY` may point at a prebuilt shared library.

Compilation uses an argv list with `shell=False`, position-independent code,
and a non-executable stack linker flag. Runtime loading verifies ABI version 1
before any kernel is exposed.

## Numeric contract

Inputs are converted to IEEE-754 float32 before entering Assembly, so callers
should compare results with float32-appropriate tolerances rather than expecting
bit-for-bit equality with Python's double-precision accumulation. Empty vectors
return `0.0`; unequal vector lengths are rejected in Python.
