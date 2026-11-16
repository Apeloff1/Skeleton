"""Private multi-sequence paged KV session over the existing TorchAccel weights.

CUDA uses the optional custom Triton kernel; CPU reference execution must be
explicit. Page tables are internal, never accepted from a request. Cancellation
or any partial layer write poisons the whole session. No implicit fallback.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math


@dataclass
class _Sequence:
    pages: list[int] = field(default_factory=list)
    tokens: list[int] = field(default_factory=list)
    logits: list[float] | None = None
    resets: int = 0


class PagedBatchSession:
    def __init__(self, accelerator, *, slots: int, context: int, max_kv_bytes: int,
                 page_tokens: int = 16, require_gpu: bool = True, max_workspace_bytes: int = 256*1024**2):
        self.accel = accelerator
        self.torch = accelerator.torch
        self.lm = accelerator.lm
        if type(slots) is not int or not 1 <= slots <= 32:
            raise ValueError("paged slot ceiling outside bounds")
        if type(context) is not int or not 1 <= context <= self.lm.ctx:
            raise ValueError("paged context outside native limits")
        if type(max_kv_bytes) is not int or not 1 <= max_kv_bytes <= 1024**4:
            raise ValueError("paged KV allocation ceiling required")
        if page_tokens not in {16, 32, 64} or type(require_gpu) is not bool:
            raise ValueError("unsupported paged decode policy")
        if not accelerator.resident or accelerator.device_name not in ({"cuda"} if require_gpu else {"cpu", "cuda"}):
            raise RuntimeError("paged kernel requires resident CUDA or explicit CPU reference")
        if getattr(self.lm, "use_mod", False):
            raise ValueError("paged decode does not implement depth routing")
        if accelerator.device_name == "cuda":
            from .paged_cuda import decode
            self._kernel = decode
        else:
            self._kernel = self._reference
        self.page_tokens, self.context = page_tokens, context
        self.heads = self.lm.n_heads
        self.dim = self.lm.dim // self.heads
        self.pages_per_slot = math.ceil(context / page_tokens)
        self.page_count = slots * self.pages_per_slot
        if self.dim > 256 or self.page_count > 262144:
            raise ValueError("paged geometry exceeds kernel limits")
        dtype = accelerator.kv_dtype
        self.page_bytes = 2 * self.lm.n_layers * self.heads * page_tokens * self.dim * self.torch.empty((), dtype=dtype).element_size()
        self.reserved_bytes = self.page_count * self.page_bytes
        effective_cap = min(max_kv_bytes, accelerator.max_kv_bytes or max_kv_bytes)
        if self.reserved_bytes + accelerator.kv_reserved_bytes > effective_cap:
            raise MemoryError("physical paged backing allocation exceeds KV ceiling")
        if type(max_workspace_bytes) is not int or not 1<=max_workspace_bytes<=1024**4:
            raise ValueError("paged workspace ceiling required")
        # Conservative explicit temporary QKV/FFN/logits/table accounting.
        workspace=4*slots*(16*self.lm.dim+6*max(self.lm.dim,self.lm.d_ff)+self.lm.V+4*self.pages_per_slot)
        if accelerator.device_name=="cpu":
            workspace+=8*slots*self.heads*context*(self.dim+1)
        if workspace>max_workspace_bytes:
            raise MemoryError("paged workspace exceeds ceiling")
        self.binding = accelerator._kv_binding()
        self.states = {i: _Sequence() for i in range(slots)}
        self.free = list(reversed(range(self.page_count)))
        self.closed = False
        shape = (self.page_count, self.heads, page_tokens, self.dim)
        with self.torch.inference_mode():
            self.keys = [self.torch.empty(shape, dtype=dtype, device=accelerator.device) for _ in range(self.lm.n_layers)]
            self.values = [self.torch.empty_like(k) for k in self.keys]

    def _assert_live(self):
        if self.closed or self.accel._kv_binding() != self.binding:
            self.close()
            raise RuntimeError("paged session closed or weights changed")
        self.accel._assert_training_integrity()

    def _release(self, state):
        self.free.extend(state.pages)
        state.pages.clear()
        state.tokens.clear()
        state.logits = None

    def release(self, slot):
        self._assert_live()
        state = self.states.pop(slot)
        self._release(state)

    def close(self):
        self.closed = True
        self.states.clear()
        self.free.clear()
        self.keys.clear()
        self.values.clear()

    def _reference(self, q, keys, values, table, lengths):
        torch = self.torch
        rows = []
        for i, (pages, length) in enumerate(zip(table.tolist(), lengths.tolist())):
            count = math.ceil(length / self.page_tokens)
            ids = pages[:count]
            k = keys[ids].transpose(0, 1).reshape(self.heads, -1, self.dim)[:, :length].float()
            v = values[ids].transpose(0, 1).reshape(self.heads, -1, self.dim)[:, :length].float()
            scores = (q[i].float().unsqueeze(1) * k).sum(-1) * self.dim ** -0.5
            rows.append((scores.softmax(-1).unsqueeze(-1) * v).sum(1))
        return torch.stack(rows)

    def _step(self, slots, ids, interrupt):
        a, torch, lm = self.accel, self.torch, self.lm
        states = [self.states[i] for i in slots]
        positions = [len(s.tokens) for s in states]
        for state, pos in zip(states, positions):
            if pos >= self.context:
                raise ValueError("paged token would exceed context")
            if pos % self.page_tokens == 0:
                if not self.free:
                    raise MemoryError("paged pool exhausted")
                state.pages.append(self.free.pop())
        device = a.device
        tokens = torch.tensor(ids, dtype=torch.long, device=device)
        pos = torch.tensor(positions, dtype=torch.long, device=device)
        physical = torch.tensor([s.pages[-1] for s in states], dtype=torch.long, device=device)
        offsets = pos % self.page_tokens
        table = torch.tensor([s.pages + [-1]*(self.pages_per_slot-len(s.pages)) for s in states],
                             dtype=torch.int32, device=device)
        lengths = (pos + 1).to(torch.int32)
        x = a._E[tokens]
        if lm.position_mode != "rope":
            x = x + a._P[pos]
        width = lm.dim - lm.dim % 2
        angles = pos.to(x.dtype).unsqueeze(-1) / (10000.0 ** (
            torch.arange(0, width, 2, device=device, dtype=x.dtype) / float(width)))
        cos, sin = angles.cos(), angles.sin()
        def rotate(v):
            out = v.clone()
            even, odd = v[..., :width:2], v[..., 1:width:2]
            out[..., :width:2] = even*cos-odd*sin
            out[..., 1:width:2] = even*sin+odd*cos
            return out.reshape(len(slots), self.heads, self.dim)
        for li, blob in enumerate(a._layers):
            if interrupt is not None:
                interrupt()
            norm = a._normalize(x, blob, "ln1")
            q = rotate(norm @ blob["Wq"].T)
            k = rotate(norm @ blob["Wk"].T)
            v = (norm @ blob["Wv"].T).reshape(len(slots), self.heads, self.dim)
            # Paired advanced indices select unique (physical page, token)
            # destinations; other rows and unused storage are not touched.
            self.keys[li][physical, :, offsets, :] = k.to(a.kv_dtype)
            self.values[li][physical, :, offsets, :] = v.to(a.kv_dtype)
            attended = self._kernel(q, self.keys[li], self.values[li], table, lengths)
            x = x + attended.reshape(len(slots), lm.dim) @ blob["Wo"].T
            if blob.get("W1") is not None:
                norm = a._normalize(x, blob, "ln2")
                gate = norm @ blob["W1"].T + blob["b1"]
                z = (torch.nn.functional.silu(gate) * (norm @ blob["Wu"].T + blob["bu"])
                     if blob.get("Wu") is not None else a._gelu(gate))
                x = x + z @ blob["W2"].T + blob["b2"]
        result = (x @ a._Wout.T + a._bout).detach().cpu().tolist()
        for state, token, row in zip(states, ids, result):
            state.tokens.append(token)
            state.logits = row

    def logits(self, slots, windows, *, interrupt=None):
        """Append only missing suffixes; re-prefill shifted/deviating windows."""
        self._assert_live()
        if len(slots) != len(windows) or not slots or len(set(slots)) != len(slots):
            raise ValueError("unique paged slot/window pairs required")
        if any(slot not in self.states for slot in slots):
            raise ValueError("unknown paged slot")
        if any(not 1 <= len(row) <= self.context or any(type(t) is not int or not 0 <= t < self.lm.V for t in row) for row in windows):
            raise ValueError("invalid paged token window")
        try:
            with self.accel._inference_lock(interrupt), self.torch.inference_mode():
                self._assert_live()
                for slot, window in zip(slots, windows):
                    state = self.states[slot]
                    if tuple(window[:len(state.tokens)]) != tuple(state.tokens):
                        state.resets += 1
                        self._release(state)
                while True:
                    active = [(slot, window[len(self.states[slot].tokens)])
                              for slot, window in zip(slots, windows)
                              if len(self.states[slot].tokens) < len(window)]
                    if not active:
                        break
                    self._step([i for i, _ in active], [t for _, t in active], interrupt)
                self._assert_live()
                return [(list(self.states[slot].logits),
                         len(self.states[slot].tokens),
                         len(self.states[slot].pages)*self.page_bytes,
                         self.states[slot].resets) for slot in slots]
        except BaseException:
            self.close()
            raise
