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
                 page_tokens: int = 16, require_gpu: bool = True, max_workspace_bytes: int = 256*1024**2,
                 private_prefix_scope: str | None = None):
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
        if private_prefix_scope is not None and (not isinstance(private_prefix_scope,str) or not 1<=len(private_prefix_scope)<=256):
            raise ValueError("explicit private prefix reuse scope required")
        self._prefix_scope=private_prefix_scope
        self._page_refs=[0]*self.page_count
        self.reused_prefix_tokens=0
        self.prefill_steps=0
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

    def _drop_page_ref(self,page):
        if self._page_refs[page]<=0:
            raise RuntimeError("paged reference accounting corrupt")
        self._page_refs[page]-=1
        if self._page_refs[page]==0:
            self.free.append(page)

    def _release(self, state):
        for page in state.pages:
            self._drop_page_ref(page)
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
        self._page_refs.clear()

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
                page=self.free.pop()
                if self._page_refs[page]:
                    raise RuntimeError("allocated page was still referenced")
                self._page_refs[page]=1
                state.pages.append(page)
            if self._page_refs[state.pages[-1]]!=1:
                raise RuntimeError("attempt to write immutable shared prefix page")
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

    def _reuse_full_pages(self,slot,window):
        """Share only complete immutable pages from active same-session donors.

        The caller must supply an explicitly owner-private scope to enable
        this optimization. No cross-session or cross-tenant reuse. Leave at
        least one token to compute the recipient's own last logits.
        """
        if self._prefix_scope is None:
            return
        state=self.states[slot]
        best=None
        matched=len(state.tokens)
        for other,donor in self.states.items():
            if other==slot:
                continue
            cap=min(len(donor.tokens),len(window)-1)
            cap-=cap%self.page_tokens
            if cap<=matched:
                continue
            common=0
            while common<cap and donor.tokens[common]==window[common]:
                common+=1
            common-=common%self.page_tokens
            if common>matched:
                best=donor
                matched=common
        if best is None:
            return
        pages=list(best.pages[:matched//self.page_tokens])
        prefix=list(best.tokens[:matched])
        previous=len(state.tokens)
        # Pin donor pages before relinquishing recipient references: the
        # recipient may already share some of the donor's prefix chain.
        for page in pages:
            if self._page_refs[page]<=0:
                raise RuntimeError("unowned prefix page")
            self._page_refs[page]+=1
        self._release(state)
        state.pages=pages
        state.tokens=prefix
        self.reused_prefix_tokens+=matched-previous

    def _rows_ready(self,slots,windows):
        return {slot:(list(self.states[slot].logits),len(self.states[slot].tokens),
                     len(self.states[slot].pages)*self.page_bytes,self.states[slot].resets)
                for slot,window in zip(slots,windows)
                if len(self.states[slot].tokens)==len(window) and self.states[slot].logits is not None}

    def logits_ready(self,slots,windows,*,max_steps=4,interrupt=None):
        """Bound each prefill quantum; return ready sequences without HOL blocking."""
        self._assert_live()
        if type(max_steps) is not int or not 1<=max_steps<=128:
            raise ValueError("invalid paged prefill quantum")
        if len(slots)!=len(windows) or not slots or len(set(slots))!=len(slots):
            raise ValueError("unique paged slot/window pairs required")
        if any(slot not in self.states for slot in slots):
            raise ValueError("unknown paged slot")
        if any(not 1<=len(row)<=self.context or any(type(t) is not int or not 0<=t<self.lm.V for t in row) for row in windows):
            raise ValueError("invalid paged token window")
        try:
            with self.accel._inference_lock(interrupt),self.torch.inference_mode():
                self._assert_live()
                for slot,window in zip(slots,windows):
                    state=self.states[slot]
                    if tuple(window[:len(state.tokens)])!=tuple(state.tokens):
                        state.resets+=1
                        self._release(state)
                    self._reuse_full_pages(slot,window)
                ready=self._rows_ready(slots,windows)
                if ready:
                    return ready
                for _ in range(max_steps):
                    if interrupt is not None:
                        interrupt()
                    active=[(slot,window[len(self.states[slot].tokens)])
                            for slot,window in zip(slots,windows)
                            if len(self.states[slot].tokens)<len(window)]
                    if not active:
                        raise RuntimeError("paged prefill cannot produce required logits")
                    self._step([i for i,_ in active],[t for _,t in active],interrupt)
                    self.prefill_steps+=1
                    self._assert_live()
                    ready=self._rows_ready(slots,windows)
                    if ready:
                        return ready
                return {}
        except BaseException:
            self.close()
            raise

    def logits(self, slots, windows, *, interrupt=None):
        """Compatibility full barrier for single-stream or synchronous callers."""
        outstanding=dict(zip(slots,windows))
        if len(outstanding)!=len(slots) or len(windows)!=len(slots) or not slots:
            raise ValueError("unique paged slot/window pairs required")
        result={}
        while outstanding:
            ready=self.logits_ready(list(outstanding),list(outstanding.values()),interrupt=interrupt)
            for slot,row in ready.items():
                result[slot]=row
                del outstanding[slot]
        return [result[slot] for slot in slots]
