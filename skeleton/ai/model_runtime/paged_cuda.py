"""Optional Triton CUDA decode: actual page-table traversal and online softmax."""
import triton
import triton.language as tl


@triton.jit
def _decode(Q, K, V, TABLE, LENGTH, OUT,
            HEADS: tl.constexpr, DIM: tl.constexpr, PAGE: tl.constexpr,
            WIDTH: tl.constexpr, TABLE_WIDTH: tl.constexpr, SCALE: tl.constexpr):
    row, head = tl.program_id(0), tl.program_id(1)
    d = tl.arange(0, WIDTH)
    t = tl.arange(0, PAGE)
    length = tl.load(LENGTH + row)
    q = tl.load(Q + (row * HEADS + head) * DIM + d, d < DIM, 0).to(tl.float32)
    maximum = -float("inf")
    denominator = 0.0
    acc = tl.full((WIDTH,), 0, tl.float32)
    for index in range(tl.cdiv(length, PAGE)):
        physical = tl.load(TABLE + row * TABLE_WIDTH + index)
        address = ((physical * HEADS + head) * PAGE + t[:, None]) * DIM + d[None, :]
        valid = index * PAGE + t < length
        mask = valid[:, None] & (d[None, :] < DIM)
        k = tl.load(K + address, mask, 0).to(tl.float32)
        v = tl.load(V + address, mask, 0).to(tl.float32)
        score = tl.sum(k * q[None, :], 1) * SCALE
        score = tl.where(valid, score, -float("inf"))
        next_max = tl.maximum(maximum, tl.max(score, 0))
        old_weight = tl.exp(maximum - next_max)
        weights = tl.exp(score - next_max)
        denominator = denominator * old_weight + tl.sum(weights, 0)
        acc = acc * old_weight + tl.sum(v * weights[:, None], 0)
        maximum = next_max
    tl.store(OUT + (row * HEADS + head) * DIM + d, acc / denominator, d < DIM)


def decode(q, k, v, table, lengths):
    import torch
    batch, heads, dim = q.shape
    _, _, page, _ = k.shape
    if q.device.type != "cuda" or dim > 256 or page not in {16, 32, 64}:
        raise ValueError("custom CUDA paged kernel requires supported device/head/page geometry")
    result = torch.empty_like(q, dtype=torch.float32)
    _decode[(batch, heads)](q.contiguous(), k, v, table, lengths, result,
        HEADS=heads, DIM=dim, PAGE=page, WIDTH=triton.next_power_of_2(dim),
        TABLE_WIDTH=table.shape[1], SCALE=dim ** -0.5, num_warps=4)
    return result
