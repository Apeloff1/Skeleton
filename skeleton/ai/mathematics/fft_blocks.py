"""FFT-accelerated convolution layered on canonical radix-2 transforms."""
from __future__ import annotations

from numbers import Real
from typing import Sequence

from .contracts import MathInvariantError, Vector, finite_vector
from .transforms import fft_radix2, inverse_fft_radix2


def next_power_of_two(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MathInvariantError(
            "next_power_of_two input must be a positive integer",
            reason="invalid_dimension",
            field="value",
        )
    return 1 << (value - 1).bit_length()


def fft_convolution(left: Sequence[Real], right: Sequence[Real]) -> Vector:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    output_size = len(a) + len(b) - 1
    size = next_power_of_two(output_size)
    padded_a = tuple(complex(value, 0.0) for value in a) + (0j,) * (size - len(a))
    padded_b = tuple(complex(value, 0.0) for value in b) + (0j,) * (size - len(b))
    spectrum_a = fft_radix2(padded_a)
    spectrum_b = fft_radix2(padded_b)
    product = tuple(x * y for x, y in zip(spectrum_a, spectrum_b))
    restored = inverse_fft_radix2(product)
    return tuple(restored[index].real for index in range(output_size))


def overlap_add_convolution(
    signal: Sequence[Real],
    kernel: Sequence[Real],
    *,
    block_size: int | None = None,
) -> Vector:
    source = finite_vector("signal", signal)
    impulse = finite_vector("kernel", kernel)
    if block_size is None:
        block = max(1, next_power_of_two(len(impulse)) - len(impulse) + 1)
    else:
        if isinstance(block_size, bool) or not isinstance(block_size, int) or block_size < 1:
            raise MathInvariantError(
                "block_size must be a positive integer",
                reason="invalid_block_size",
                field="block_size",
            )
        block = block_size
    fft_size = next_power_of_two(block + len(impulse) - 1)
    padded_kernel = tuple(complex(value, 0.0) for value in impulse) + (0j,) * (fft_size - len(impulse))
    kernel_spectrum = fft_radix2(padded_kernel)
    output = [0.0] * (len(source) + len(impulse) - 1)

    for start in range(0, len(source), block):
        chunk = source[start : start + block]
        padded = tuple(complex(value, 0.0) for value in chunk) + (0j,) * (fft_size - len(chunk))
        spectrum = fft_radix2(padded)
        restored = inverse_fft_radix2(tuple(x * h for x, h in zip(spectrum, kernel_spectrum)))
        valid = len(chunk) + len(impulse) - 1
        for offset in range(valid):
            output[start + offset] += restored[offset].real
    return tuple(output)


def fft_cross_correlation(left: Sequence[Real], right: Sequence[Real]) -> Vector:
    a = finite_vector("left", left)
    b = finite_vector("right", right)
    return fft_convolution(a, tuple(reversed(b)))
