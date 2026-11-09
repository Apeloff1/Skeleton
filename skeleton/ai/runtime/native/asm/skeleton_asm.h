#ifndef SKELETON_NATIVE_ASM_H
#define SKELETON_NATIVE_ASM_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SKELETON_ASM_ABI_VERSION UINT32_C(4)

#define SKELETON_ASM_CAP_X86_SSE2 UINT64_C(1)
#define SKELETON_ASM_CAP_X86_AVX  UINT64_C(2)
#define SKELETON_ASM_CAP_AARCH64_NEON UINT64_C(4)

/*
 * Return the exact ABI version implemented by the loaded library.
 * Callers must reject libraries whose version differs from
 * SKELETON_ASM_ABI_VERSION.
 */
uint32_t skeleton_asm_abi_version(void);

/*
 * Return a bit-mask of instruction-set capabilities implemented and safe to
 * execute in the current process. x86 AVX includes OSXSAVE/XGETBV validation.
 */
uint64_t skeleton_asm_capabilities(void);

/* Pairwise float32 primitives. */
float skeleton_asm_dot_f32(
    const float *left,
    const float *right,
    size_t length
);

float skeleton_asm_l2_sq_f32(
    const float *left,
    const float *right,
    size_t length
);

/*
 * Score one query against a row-major candidate matrix.
 * out must have space for rows float32 values.
 */
void skeleton_asm_dot_batch_f32(
    const float *query,
    const float *matrix,
    size_t rows,
    size_t dimensions,
    float *out
);

/*
 * Score query_count row-major queries against one row-major candidate matrix.
 * out layout is [query][candidate], containing query_count * rows float32
 * values.
 */
void skeleton_asm_dot_matrix_f32(
    const float *queries,
    size_t query_count,
    const float *matrix,
    size_t rows,
    size_t dimensions,
    float *out
);

#if defined(__x86_64__) || defined(_M_X64)
/*
 * AVX-specialized matrix scorer. Invoke only when
 * SKELETON_ASM_CAP_X86_AVX is reported by skeleton_asm_capabilities().
 */
void skeleton_asm_dot_matrix_f32_avx(
    const float *queries,
    size_t query_count,
    const float *matrix,
    size_t rows,
    size_t dimensions,
    float *out
);
#endif

#ifdef __cplusplus
}
#endif

#endif /* SKELETON_NATIVE_ASM_H */
