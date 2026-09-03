"""Numeric kernels. CPU reference. No CUDA. No FlashInfer.

Dims stay tiny on purpose. Mobile d=8. Desktop d=16.
Fusion means intermediates stay in the working row, not nine
full-matrix writes.
"""
from skeleton.kernel.ops.engine import Engine, writes
from skeleton.kernel.ops.matmul import matmul
from skeleton.kernel.ops.attention import attend
from skeleton.kernel.ops.rmsnorm import rmsnorm
from skeleton.kernel.ops.kvcache import KVCache
from skeleton.kernel.ops.qlinear import qlinear, quantize
from skeleton.kernel.ops.sample import sample
from skeleton.kernel.ops.fused import fused_block

__all__ = [
    "Engine", "writes", "matmul", "attend", "rmsnorm",
    "KVCache", "qlinear", "quantize", "sample", "fused_block",
]
