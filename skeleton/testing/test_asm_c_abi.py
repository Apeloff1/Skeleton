from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from skeleton.native.asm_accelerator import AsmVectorAccelerator


_C_SMOKE = r"""
#include "skeleton_asm.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>

static int nearf(float actual, float expected) {
    return fabsf(actual - expected) <= 1.0e-4f;
}

int main(void) {
    if (skeleton_asm_abi_version() != SKELETON_ASM_ABI_VERSION) {
        return 10;
    }

    const uint64_t capabilities = skeleton_asm_capabilities();
#if defined(__x86_64__) || defined(_M_X64)
    if ((capabilities & SKELETON_ASM_CAP_X86_SSE2) == 0) {
        return 11;
    }
#elif defined(__aarch64__)
    if ((capabilities & SKELETON_ASM_CAP_AARCH64_NEON) == 0) {
        return 12;
    }
#endif

    const float left[7] = {1.0f, -2.0f, 3.5f, 4.0f, 0.25f, 9.0f, -7.0f};
    const float right[7] = {2.0f, 5.0f, -1.5f, 2.0f, 8.0f, -3.0f, 6.0f};
    const float expected_dot = -72.25f;
    if (!nearf(skeleton_asm_dot_f32(left, right, 7), expected_dot)) {
        return 20;
    }

    const float expected_l2 =
        (1.0f - 2.0f) * (1.0f - 2.0f) +
        (-2.0f - 5.0f) * (-2.0f - 5.0f) +
        (3.5f + 1.5f) * (3.5f + 1.5f) +
        (4.0f - 2.0f) * (4.0f - 2.0f) +
        (0.25f - 8.0f) * (0.25f - 8.0f) +
        (9.0f + 3.0f) * (9.0f + 3.0f) +
        (-7.0f - 6.0f) * (-7.0f - 6.0f);
    if (!nearf(skeleton_asm_l2_sq_f32(left, right, 7), expected_l2)) {
        return 21;
    }

    const float matrix[14] = {
        2.0f, 5.0f, -1.5f, 2.0f, 8.0f, -3.0f, 6.0f,
        1.0f, 0.0f, 1.0f, 0.0f, 1.0f, 0.0f, 1.0f,
    };
    float batch[2] = {0.0f, 0.0f};
    skeleton_asm_dot_batch_f32(left, matrix, 2, 7, batch);
    if (!nearf(batch[0], expected_dot) || !nearf(batch[1], -2.25f)) {
        return 30;
    }

    const float queries[14] = {
        1.0f, -2.0f, 3.5f, 4.0f, 0.25f, 9.0f, -7.0f,
        2.0f, 5.0f, -1.5f, 2.0f, 8.0f, -3.0f, 6.0f,
    };
    float scores[4] = {0.0f, 0.0f, 0.0f, 0.0f};
    skeleton_asm_dot_matrix_f32(queries, 2, matrix, 2, 7, scores);
    if (
        !nearf(scores[0], expected_dot) ||
        !nearf(scores[1], -2.25f) ||
        !nearf(scores[2], 144.25f) ||
        !nearf(scores[3], 14.5f)
    ) {
        return 31;
    }

#if defined(__x86_64__) || defined(_M_X64)
    if ((capabilities & SKELETON_ASM_CAP_X86_AVX) != 0) {
        float avx_scores[4] = {0.0f, 0.0f, 0.0f, 0.0f};
        skeleton_asm_dot_matrix_f32_avx(
            queries,
            2,
            matrix,
            2,
            7,
            avx_scores
        );
        for (size_t index = 0; index < 4; ++index) {
            if (!nearf(avx_scores[index], scores[index])) {
                return 32;
            }
        }
    }
#endif

    printf("skeleton-asm-c-abi: OK\n");
    return 0;
}
"""


def test_c_header_links_and_executes_public_abi(tmp_path: Path) -> None:
    preflight = AsmVectorAccelerator.preflight(cache_dir=tmp_path)
    if not preflight.build_ready:
        pytest.skip("host cannot build the Assembly accelerator")

    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("C compiler unavailable")

    library = AsmVectorAccelerator.build(output_dir=tmp_path)
    header_dir = Path(__file__).resolve().parents[1] / "native" / "asm"
    source = tmp_path / "consumer.c"
    executable = tmp_path / "consumer"
    source.write_text(_C_SMOKE, encoding="utf-8")

    command = [
        compiler,
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(header_dir),
        str(source),
        str(library),
        f"-Wl,-rpath,{library.parent}",
        "-lm",
        "-o",
        str(executable),
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        part
        for part in (str(library.parent), env.get("LD_LIBRARY_PATH", ""))
        if part
    )
    executed = subprocess.run(
        [str(executable)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert executed.returncode == 0, (
        f"C ABI smoke exited {executed.returncode}: "
        f"{executed.stderr or executed.stdout}"
    )
    assert "skeleton-asm-c-abi: OK" in executed.stdout
