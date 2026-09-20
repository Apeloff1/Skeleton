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
- `skeleton_asm_capabilities() -> uint64`
- `skeleton_asm_dot_f32(left, right, length) -> float`
- `skeleton_asm_l2_sq_f32(left, right, length) -> float`
- `skeleton_asm_dot_batch_f32(query, row_major_matrix, rows, dimensions, out) -> void`
- `skeleton_asm_dot_matrix_f32(queries, query_count, row_major_matrix, rows, dimensions, out) -> void`

The x86-64 and AArch64 kernels process four float32 lanes per loop and finish
remaining elements with scalar instructions. The batch kernel keeps the query
resident across row scoring and emits one float32 dot product per matrix row,
so dense retrieval can cross the Python/native boundary once per query instead
of once per candidate. ABI v3 also accepts a row-major query matrix and scores
the full query × candidate product in one native call.

ABI v4 adds runtime ISA capability reporting. x86-64 always exposes the SSE2
baseline and reports AVX only when CPUID advertises AVX + OSXSAVE and XCR0
confirms that the operating system preserves XMM/YMM state. The Python loader
then selects a 256-bit AVX matrix kernel; otherwise it remains on the SSE2
implementation. AArch64 reports its architectural NEON baseline and continues
through the 128-bit Advanced SIMD kernel. They do not require AVX, AVX2,
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
and a non-executable stack linker flag. Runtime loading verifies ABI version 4
before any kernel is exposed.

## Numeric contract

Inputs are converted to IEEE-754 float32 before entering Assembly, so callers
should compare results with float32-appropriate tolerances rather than expecting
bit-for-bit equality with Python's double-precision accumulation. Empty vectors
return `0.0`; unequal vector lengths are rejected in Python.
