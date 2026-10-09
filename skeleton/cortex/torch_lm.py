"""Torch / CUDA accel for the neo LM.

Lazy import. GameForge CI never loads this file unless someone
calls TinyTransformer.to() and torch is installed.

TorchAccel: same TinyTransformer weights, pinned on cpu|cuda|mps,
autograd SGD through stacked Pre-LN blocks. Python lists catch
up on sync() / snapshot(). GPU is a harness, not a rewrite.

TorchTransformer: optional nn.TransformerEncoder stack, restored
only when a snapshot kind is torch-stack.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Iterable, List, Sequence

from skeleton.cortex.port import tokens

UNK = "__unk__"


def _torch():
    import torch
    return torch


class TorchAccel:
    """Run TinyTransformer steps with autograd. Weights live on the device."""

    def __init__(self, lm: Any, device: str = "cpu") -> None:
        torch = _torch()
        if device in {"cuda", "gpu"}:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        elif device == "mps":
            device = "mps" if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available() else "cpu"
        self.torch = torch
        self.lm = lm
        self.device = torch.device(device)
        self.device_name = self.device.type
        self.resident = False
        self._E = self._P = self._Wout = self._bout = None
        self._layers: List[Dict[str, Any]] = []
        self._weights_modified = False
        self._training_failed = False
        self._state_lock = threading.RLock()
        self.reset_decode_cache()

    @property
    def cached_tokens(self) -> tuple[int, ...]:
        """Expose countable decode occupancy without exporting device tensors."""
        with self._state_lock:
            return tuple(self._cached_ids)

    def reset_decode_cache(self) -> None:
        """Drop all accelerator-local decode history after weight changes."""
        with self._state_lock:
            self._reset_decode_cache_unlocked()

    def _reset_decode_cache_unlocked(self) -> None:
        """Mutate resident cache only while holding the accelerator lock."""
        self._cached_ids: List[int] = []
        self._cached_keys: List[Any] = []
        self._cached_values: List[Any] = []
        self._key_buffers: List[Any] = []
        self._value_buffers: List[Any] = []
        self._cached_next_position = 0

    def _reserve_kv(self, layer: int, needed: int, heads: int, head_dim: int) -> None:
        """Amortized resident KV allocation, bounded by the model context.

        Append within existing capacity never concatenates/copies history.
        Geometric expansion copies only on capacity transitions, while short
        prompts avoid allocating for the entire maximum context up front.
        """
        torch = self.torch
        if not 1 <= needed <= self.lm.ctx:
            raise ValueError("requested KV cache capacity outside model context")
        if layer < len(self._key_buffers):
            old_cap = self._key_buffers[layer].shape[-2]
            if old_cap >= needed:
                return
            old_used = self._cached_keys[layer].shape[-2]
        else:
            old_cap = old_used = 0
        new_cap = min(self.lm.ctx, max(needed, 16, old_cap * 2))
        shape = (1, heads, new_cap, head_dim)
        new_keys = torch.empty(shape, dtype=self._E.dtype, device=self.device)
        new_values = torch.empty(shape, dtype=self._E.dtype, device=self.device)
        if old_used:
            new_keys[:, :, :old_used, :].copy_(self._cached_keys[layer])
            new_values[:, :, :old_used, :].copy_(self._cached_values[layer])
        if layer < len(self._key_buffers):
            self._key_buffers[layer] = new_keys
            self._value_buffers[layer] = new_values
        else:
            self._key_buffers.append(new_keys)
            self._value_buffers.append(new_values)

    def _assert_training_integrity(self) -> None:
        if self._training_failed:
            raise RuntimeError(
                "accelerator weights may contain a partial training update; "
                "restore from a trusted checkpoint"
            )

    def _t2(self, rows: List[List[float]], grad: bool = True):
        return self.torch.tensor(rows, dtype=self.torch.float32, device=self.device, requires_grad=grad)

    def _t1(self, row: List[float], grad: bool = True):
        return self.torch.tensor(row, dtype=self.torch.float32, device=self.device, requires_grad=grad)

    def pin(self) -> "TorchAccel":
        with self._state_lock:
            return self._pin_unlocked()

    def _pin_unlocked(self) -> "TorchAccel":
        """Upload canonical Python weights, saving trained device changes first."""
        self._assert_training_integrity()
        if self._weights_modified:
            self.sync()
        lm = self.lm
        if getattr(lm, "use_mod", False):
            raise ValueError("accelerator does not implement Mixture of Depths routing")
        self.reset_decode_cache()
        self._weights_modified = False
        self._E = self._t2(lm.E)
        self._P = self._t2(lm.P)
        self._Wout = self._E if getattr(lm, "tied", False) else self._t2(lm.Wout)
        self._bout = self._t1(lm.bout)
        self._layers = []
        blocks = getattr(lm, "layers", None) or []
        if not blocks:
            blocks = [lm]
        for L in blocks:
            blob: Dict[str, Any] = {
                "Wq": self._t2(L.Wq), "Wk": self._t2(L.Wk),
                "Wv": self._t2(L.Wv), "Wo": self._t2(L.Wo),
                "ln1_g": self._t1(getattr(L, "ln1_g", [1.0] * lm.dim)),
                "ln1_b": self._t1(getattr(L, "ln1_b", [0.0] * lm.dim)),
                "W1": None, "b1": None, "Wu": None, "bu": None,
                "W2": None, "b2": None,
                "ln2_g": None, "ln2_b": None,
            }
            W1 = getattr(L, "W1", None)
            if W1:
                blob["W1"] = self._t2(W1)
                blob["b1"] = self._t1(getattr(L, "b1", [0.0] * len(W1)))
                if getattr(L, "ffn_kind", "gelu") == "swiglu":
                    blob["Wu"] = self._t2(L.Wu)
                    blob["bu"] = self._t1(L.bu)
                blob["W2"] = self._t2(L.W2)
                blob["b2"] = self._t1(getattr(L, "b2", [0.0] * lm.dim))
                blob["ln2_g"] = self._t1(getattr(L, "ln2_g", [1.0] * lm.dim))
                blob["ln2_b"] = self._t1(getattr(L, "ln2_b", [0.0] * lm.dim))
            self._layers.append(blob)
        self.resident = True
        lm.resident = True
        lm.device = self.device_name
        return self

    def _params(self):
        # Weight tying shares a tensor; never apply SGD to it twice.
        seen = set()
        for value in (self._E, self._P, self._Wout, self._bout):
            if id(value) not in seen:
                seen.add(id(value))
                yield value
        for layer in self._layers:
            for value in layer.values():
                if value is not None and id(value) not in seen:
                    seen.add(id(value))
                    yield value

    def sync(self) -> None:
        with self._state_lock:
            self._sync_unlocked()

    def _sync_unlocked(self) -> None:
        """Python lists catch up. Snapshot / to() / fallback call this."""
        self._assert_training_integrity()
        if not self.resident or self._E is None or not self._weights_modified:
            return
        # CPU Python weights are the canonical admission and checkpoint
        # identity. A float32 device pin is not a training mutation: avoid
        # silently rounding the canonical snapshot and uploading weights on
        # every per-token identity check.
        lm = self.lm
        lm.E = self._E.detach().cpu().tolist()
        lm.P = self._P.detach().cpu().tolist()
        lm.Wout = lm.E if getattr(lm, "tied", False) else self._Wout.detach().cpu().tolist()
        lm.bout = self._bout.detach().cpu().tolist()
        blocks = getattr(lm, "layers", None) or []
        for i, blob in enumerate(self._layers):
            target = blocks[i] if i < len(blocks) else lm
            target.Wq = blob["Wq"].detach().cpu().tolist()
            target.Wk = blob["Wk"].detach().cpu().tolist()
            target.Wv = blob["Wv"].detach().cpu().tolist()
            target.Wo = blob["Wo"].detach().cpu().tolist()
            if hasattr(target, "ln1_g"):
                target.ln1_g = blob["ln1_g"].detach().cpu().tolist()
                target.ln1_b = blob["ln1_b"].detach().cpu().tolist()
            if blob.get("W1") is not None:
                target.W1 = blob["W1"].detach().cpu().tolist()
                target.b1 = blob["b1"].detach().cpu().tolist()
                if blob.get("Wu") is not None:
                    target.Wu = blob["Wu"].detach().cpu().tolist()
                    target.bu = blob["bu"].detach().cpu().tolist()
                target.W2 = blob["W2"].detach().cpu().tolist()
                target.b2 = blob["b2"].detach().cpu().tolist()
                if hasattr(target, "ln2_g") and blob.get("ln2_g") is not None:
                    target.ln2_g = blob["ln2_g"].detach().cpu().tolist()
                    target.ln2_b = blob["ln2_b"].detach().cpu().tolist()
        self._weights_modified = False

    def _normalize(self, x, layer, prefix: str):
        torch = self.torch
        weight = layer[prefix + "_g"]
        if getattr(self.lm, "norm", "ln") == "rms":
            # Match the reference path's epsilon and RMS definition.
            return x * torch.rsqrt(x.square().mean(dim=-1, keepdim=True) + 1e-5) * weight
        return torch.nn.functional.layer_norm(
            x, (int(self.lm.dim),), weight, layer[prefix + "_b"], eps=1e-5
        )

    def _attention(self, q, k, v, *, heads: int, head_dim: int):
        """Delegate kernel choice to SDPA: Flash/memory-efficient/math where supported."""
        torch = self.torch
        functional = torch.nn.functional
        length = q.size(0)
        qh = q.reshape(length, heads, head_dim).transpose(0, 1).unsqueeze(0)
        kh = k.reshape(length, heads, head_dim).transpose(0, 1).unsqueeze(0)
        vh = v.reshape(length, heads, head_dim).transpose(0, 1).unsqueeze(0)
        if hasattr(functional, "scaled_dot_product_attention"):
            # Use the backend's native kernel dispatcher; do not force an
            # unsupported Flash kernel or allocate an explicit T x T mask.
            output = functional.scaled_dot_product_attention(
                qh, kh, vh, dropout_p=0.0, is_causal=True
            )
        else:
            scores = (qh @ kh.transpose(-2, -1)) * (head_dim ** -0.5)
            mask = torch.ones(length, length, dtype=torch.bool, device=q.device).triu(1)
            output = torch.softmax(scores.masked_fill(mask, float("-inf")), dim=-1) @ vh
        return output.squeeze(0).transpose(0, 1).contiguous().reshape(length, heads * head_dim)

    def _forward_ids(self, ids: Sequence[int], *, fill_cache: bool = False):
        torch = self.torch
        lm = self.lm
        if not self.resident:
            self.pin()
        if fill_cache:
            self.reset_decode_cache()
        idx = torch.tensor(list(ids), dtype=torch.long, device=self.device)
        pos = torch.arange(len(ids), device=self.device).clamp(max=lm.ctx - 1)
        X = self._E[idx] if getattr(lm, "position_mode", "learned_rope") == "rope" else self._E[idx] + self._P[pos]
        D = int(lm.dim)
        heads = max(1, int(lm.n_heads))
        dh = D // heads
        for blob in self._layers:
            Xn = self._normalize(X, blob, "ln1")
            Q, K, V = Xn @ blob["Wq"].T, Xn @ blob["Wk"].T, Xn @ blob["Wv"].T
            Q, K = self._rope(Q), self._rope(K)
            if fill_cache:
                length = K.size(0)
                self._reserve_kv(len(self._cached_keys), length, heads, dh)
                li = len(self._cached_keys)
                self._key_buffers[li][:, :, :length, :].copy_(
                    K.reshape(length, heads, dh).transpose(0, 1).unsqueeze(0)
                )
                self._value_buffers[li][:, :, :length, :].copy_(
                    V.reshape(length, heads, dh).transpose(0, 1).unsqueeze(0)
                )
                self._cached_keys.append(self._key_buffers[li][:, :, :length, :])
                self._cached_values.append(self._value_buffers[li][:, :, :length, :])
            C = self._attention(Q, K, V, heads=heads, head_dim=dh)
            X = X + C @ blob["Wo"].T
            if blob.get("W1") is not None:
                Un = self._normalize(X, blob, "ln2")
                gate = Un @ blob["W1"].T + blob["b1"]
                if blob.get("Wu") is not None:
                    up = Un @ blob["Wu"].T + blob["bu"]
                    z = torch.nn.functional.silu(gate) * up
                else:
                    z = self._gelu(gate)
                X = X + z @ blob["W2"].T + blob["b2"]
        if fill_cache:
            self._cached_ids = list(ids)
            self._cached_next_position = len(ids)
        return X[-1] @ self._Wout.T + self._bout, X[-1]

    def _rope(self, X, *, position_offset: int = 0):
        """Match attn.apply_rope, including absolute offsets for cached decode."""
        torch = self.torch
        T, D = X.shape
        d = D - (D % 2)
        if d < 2:
            return X
        out = X.clone()
        pos = (torch.arange(T, device=X.device, dtype=X.dtype) + position_offset).unsqueeze(1)
        i = torch.arange(0, d, 2, device=X.device, dtype=X.dtype)
        theta = pos / (10000.0 ** (i / float(d)))
        c, s = torch.cos(theta), torch.sin(theta)
        even = X[:, 0:d:2]
        odd = X[:, 1:d:2]
        out = out.clone()
        out[:, 0:d:2] = even * c - odd * s
        out[:, 1:d:2] = even * s + odd * c
        return out

    def _gelu(self, x):
        """Tanh approximation matching attn.gelu — not erf."""
        torch = self.torch
        k = 0.7978845608028654  # sqrt(2/pi)
        return 0.5 * x * (1.0 + torch.tanh(k * (x + 0.044715 * x * x * x)))

    def _cached_step(self, token_id: int) -> "Any":
        """Single-token attention using resident K/V (no repeated prefill).

        Keys are rotated exactly once at their original position. For learned
        absolute positional embeddings, a sliding window always re-prefills.
        Rotary-only sliding eviction is safe only for a one-block transformer
        because deeper blocks' historic keys depend on discarded context.
        """
        torch = self.torch
        lm = self.lm
        pos = self._cached_next_position
        token_id = int(token_id) if 0 <= int(token_id) < lm.V else lm.unk
        x = self._E[token_id]
        if getattr(lm, "position_mode", "learned_rope") != "rope":
            x = x + self._P[min(pos, lm.ctx - 1)]
        heads = lm.n_heads
        hd = lm.dim // heads
        for layer_index, blob in enumerate(self._layers):
            xn = self._normalize(x, blob, "ln1")
            q = self._rope((xn @ blob["Wq"].T).unsqueeze(0), position_offset=pos)
            k = self._rope((xn @ blob["Wk"].T).unsqueeze(0), position_offset=pos)
            v = (xn @ blob["Wv"].T).unsqueeze(0)
            qh = q.reshape(1, heads, hd).transpose(0, 1).unsqueeze(0)
            kh = k.reshape(1, heads, hd).transpose(0, 1).unsqueeze(0)
            vh = v.reshape(1, heads, hd).transpose(0, 1).unsqueeze(0)
            current_len = (
                self._cached_keys[layer_index].shape[-2]
                if layer_index < len(self._cached_keys) else 0
            )
            self._reserve_kv(layer_index, current_len + 1, heads, hd)
            self._key_buffers[layer_index][:, :, current_len:current_len + 1, :].copy_(kh)
            self._value_buffers[layer_index][:, :, current_len:current_len + 1, :].copy_(vh)
            kh = self._key_buffers[layer_index][:, :, :current_len + 1, :]
            vh = self._value_buffers[layer_index][:, :, :current_len + 1, :]
            if layer_index < len(self._cached_keys):
                self._cached_keys[layer_index] = kh
                self._cached_values[layer_index] = vh
            else:
                self._cached_keys.append(kh)
                self._cached_values.append(vh)
            # A single query attends to all preceding keys, including its
            # own; is_causal=True would mask almost the entire key history.
            if hasattr(torch.nn.functional, "scaled_dot_product_attention"):
                context = torch.nn.functional.scaled_dot_product_attention(
                    qh, kh, vh, dropout_p=0.0, is_causal=False
                )
            else:
                scores = qh @ kh.transpose(-2, -1) * (hd ** -0.5)
                context = torch.softmax(scores, dim=-1) @ vh
            x = x + context.squeeze(0).transpose(0, 1).reshape(lm.dim) @ blob["Wo"].T
            if blob.get("W1") is not None:
                un = self._normalize(x, blob, "ln2")
                gate = un @ blob["W1"].T + blob["b1"]
                if blob.get("Wu") is not None:
                    z = torch.nn.functional.silu(gate) * (un @ blob["Wu"].T + blob["bu"])
                else:
                    z = self._gelu(gate)
                x = x + z @ blob["W2"].T + blob["b2"]
        self._cached_ids.append(token_id)
        self._cached_next_position += 1
        return x @ self._Wout.T + self._bout

    def logits_window(self, ids: Sequence[int]) -> List[float]:
        """Serialize resident KV mutation across concurrent local requests."""
        result, _ = self.logits_window_with_cache(ids)
        return result

    def logits_window_with_cache(
        self, ids: Sequence[int]
    ) -> tuple[List[float], tuple[int, ...]]:
        """Return logits and occupancy from the same atomic cache transition.

        Separate logits and cache-token reads race with another inference
        session and can corrupt resource/replay accounting even if logits
        themselves remain correct.
        """
        with self._state_lock:
            result = self._logits_window_unlocked(ids)
            return result, tuple(self._cached_ids)

    def _logits_window_unlocked(self, ids: Sequence[int]) -> List[float]:
        """Prefill once, then decode with on-device per-layer K/V tensors."""
        self._assert_training_integrity()
        if not self.resident:
            self.pin()
        lm = self.lm
        window = list(ids[-lm.ctx:] or [lm.unk])
        # Inference mode avoids autograd view/version bookkeeping on the
        # hot prefill/decode path; SGD remains in regular grad-enabled mode.
        with self.torch.inference_mode():
            if self._cached_ids == window[:-1]:
                result = self._cached_step(window[-1])
            elif (
                getattr(lm, "position_mode", "learned_rope") == "rope"
                and lm.n_layers == 1
                and len(self._cached_ids) == lm.ctx
                and self._cached_ids[1:] == window[:-1]
            ):
                for i in range(len(self._cached_keys)):
                    # Reclaim the first slot; views preserve the same buffers
                    # and no new full-size cache allocation is required.
                    self._key_buffers[i][:, :, :-1, :].copy_(
                        self._cached_keys[i][:, :, 1:, :].clone()
                    )
                    self._value_buffers[i][:, :, :-1, :].copy_(
                        self._cached_values[i][:, :, 1:, :].clone()
                    )
                    self._cached_keys[i] = self._key_buffers[i][:, :, :-1, :]
                    self._cached_values[i] = self._value_buffers[i][:, :, :-1, :]
                del self._cached_ids[0]
                result = self._cached_step(window[-1])
            else:
                # Batched fused causal prefill; one-token loops are only used
                # for decode. Avoid O(context) Python/GPU launches on prompts.
                result, _ = self._forward_ids(window, fill_cache=True)
            return result.detach().cpu().tolist()

    def logits(self, ids: Sequence[int]) -> List[float]:
        with self._state_lock, self.torch.inference_mode():
            self._assert_training_integrity()
            y, _ = self._forward_ids(ids)
            return y.detach().cpu().tolist()

    def hidden(self, ids: Sequence[int]) -> List[float]:
        with self._state_lock, self.torch.inference_mode():
            self._assert_training_integrity()
            _, h = self._forward_ids(ids)
            return h.detach().cpu().tolist()

    def sgd(self, ids: Sequence[int], target: int, lr: float) -> float:
        with self._state_lock:
            return self._sgd_unlocked(ids, target, lr)

    def _sgd_unlocked(self, ids: Sequence[int], target: int, lr: float) -> float:
        self._assert_training_integrity()
        self.reset_decode_cache()
        torch = self.torch
        if not self.resident:
            self.pin()
        for p in self._params():
            if p.grad is not None:
                p.grad.zero_()
        logits, _ = self._forward_ids(ids)
        tgt = torch.tensor([int(target)], dtype=torch.long, device=self.device)
        loss = torch.nn.functional.cross_entropy(logits.unsqueeze(0), tgt)
        loss.backward()
        # GPU updates are not automatically transactional. If an in-place
        # write fails partway, any further inference or synchronization would
        # treat a partially trained graph as an admitted immutable model.
        self._weights_modified = True
        try:
            with torch.no_grad():
                for p in self._params():
                    if p.grad is not None:
                        p.add_(p.grad, alpha=-float(lr))
        except Exception:
            self._training_failed = True
            self.reset_decode_cache()
            raise
        self.lm.steps += 1
        return float(loss.detach().cpu())

    def decode(self, prefix: str, n: int = 14, seed: int = 0) -> str:
        """Decode atomically relative to other sessions sharing the model."""
        with self._state_lock:
            return self._decode_unlocked(prefix, n=n, seed=seed)

    def _decode_unlocked(self, prefix: str, n: int = 14, seed: int = 0) -> str:
        """Sample next tokens on the bound device."""
        torch = self.torch
        lm = self.lm
        if not self.resident:
            self.pin()
        g = torch.Generator(device="cpu")
        g.manual_seed(int(seed) & 0xFFFFFFFF)
        ids = [lm._id(t) for t in tokens(prefix)] or [lm.unk]
        with torch.no_grad():
            for _ in range(max(1, n)):
                window = ids[-lm.ctx:]
                logits = self.logits_window(window)
                p = torch.softmax(torch.tensor(logits, dtype=torch.float32), dim=-1)
                nxt = int(torch.multinomial(p, 1, generator=g).item())
                ids.append(nxt)
        return " ".join(lm.itos[i] if 0 <= i < len(lm.itos) else UNK for i in ids[:n])


class TorchTransformer:
    """Stacked TransformerEncoder on cpu|cuda. Optional high-standard neo LM."""

    name = "torch-lm"
    scale = "neo"
    slot = "neo"

    def __init__(
        self,
        vocab: Iterable[str] | None = None,
        *,
        dim: int = 8,
        ctx: int = 8,
        seed: int = 19,
        n_heads: int = 2,
        n_layers: int = 2,
        d_ff: int = 32,
        device: str = "cpu",
    ) -> None:
        torch = _torch()
        if device in {"cuda", "gpu"}:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        elif device == "mps":
            device = "mps" if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available() else "cpu"
        self.torch = torch
        self.device_obj = torch.device(device)
        self.device = self.device_obj.type
        self.requested = device
        self.resident = True
        itos = [UNK] + sorted({str(t) for t in (vocab or ()) if t and t != UNK})
        self.itos = itos
        self.stoi = {t: i for i, t in enumerate(itos)}
        self.unk = 0
        self.dim = max(4, int(dim))
        self.ctx = max(2, int(ctx))
        self.n_heads = max(1, int(n_heads))
        if self.dim % self.n_heads:
            self.n_heads = 1
        self.n_layers = max(1, int(n_layers))
        self.d_ff = max(self.dim, int(d_ff))
        self.fitted = 0
        self.steps = 0
        torch.manual_seed(int(seed) & 0xFFFFFFFF)
        V = max(2, len(itos))
        self.net = _Stack(
            V, self.dim, self.ctx, self.n_heads, self.n_layers, self.d_ff, torch,
        ).to(self.device_obj)
        self._opt = torch.optim.SGD(self.net.parameters(), lr=0.06)

    def to(self, device: str = "cpu") -> "TorchTransformer":
        torch = self.torch
        requested = "cuda" if device in {"cuda", "gpu"} else device
        if requested not in {"cuda", "mps", "cpu"}:
            requested = "cpu"
        if requested == "cuda" and not torch.cuda.is_available():
            actual = "cpu"
        elif requested == "mps" and not (
            getattr(torch.backends, "mps", None) is not None
            and torch.backends.mps.is_available()
        ):
            actual = "cpu"
        else:
            actual = requested
        self.requested = requested
        self.device = actual
        self.device_obj = torch.device(actual)
        self.net.to(self.device_obj)
        return self

    def _id(self, tok: str) -> int:
        return int(self.stoi.get(tok, self.unk))

    def fit(self, texts: Iterable[str], *, lr: float = 0.06) -> int:
        torch = self.torch
        for g in self._opt.param_groups:
            g["lr"] = float(lr)
        n = 0
        self.net.train()
        for raw in texts:
            body = tokens(raw)
            if len(body) < 2:
                continue
            ids = [self._id(t) for t in body]
            for i in range(1, len(ids)):
                window = ids[max(0, i - self.ctx):i]
                x = torch.tensor([window], dtype=torch.long, device=self.device_obj)
                y = torch.tensor([ids[i]], dtype=torch.long, device=self.device_obj)
                self._opt.zero_grad(set_to_none=True)
                logits = self.net(x)
                loss = torch.nn.functional.cross_entropy(logits, y)
                loss.backward()
                self._opt.step()
                self.steps += 1
                n += 1
            self.fitted += 1
        return n

    def decode(self, prefix: str, *, n: int = 14, seed: int = 0) -> str:
        torch = self.torch
        self.net.eval()
        g = torch.Generator(device="cpu")
        g.manual_seed(int(seed) & 0xFFFFFFFF)
        ids = [self._id(t) for t in tokens(prefix)] or [self.unk]
        with torch.no_grad():
            for _ in range(max(1, n)):
                window = ids[-self.ctx:]
                x = torch.tensor([window], dtype=torch.long, device=self.device_obj)
                logits = self.net(x)[0]
                p = torch.softmax(logits.float().cpu(), dim=-1)
                nxt = int(torch.multinomial(p, 1, generator=g).item())
                ids.append(nxt)
        return " ".join(self.itos[i] if 0 <= i < len(self.itos) else UNK for i in ids[:n])

    def generate(self, prefix: str, n: int = 12, *, seed: int = 0):
        return tuple(self.decode(prefix, n=n, seed=seed).split())

    def logprob(self, text: str) -> float:
        torch = self.torch
        body = tokens(text)
        if len(body) < 2:
            return 0.0
        ids = [self._id(t) for t in body]
        self.net.eval()
        lp = 0.0
        n = 0
        with torch.no_grad():
            for i in range(1, len(ids)):
                window = ids[max(0, i - self.ctx):i]
                x = torch.tensor([window], dtype=torch.long, device=self.device_obj)
                logp = torch.log_softmax(self.net(x)[0], dim=-1)
                lp += float(logp[ids[i]].cpu())
                n += 1
        return lp / max(1, n)

    def perplexity(self, texts) -> float:
        import math
        if isinstance(texts, str):
            seq = [texts]
        else:
            seq = [t for t in texts if t]
        if not seq:
            return float(len(self.itos))
        mean = sum(self.logprob(t) for t in seq) / len(seq)
        return math.exp(-mean)

    def snapshot(self) -> Dict[str, Any]:
        blob = {k: v.detach().cpu().tolist() for k, v in self.net.state_dict().items()}
        return {
            "kind": "torch-stack",
            "dim": self.dim, "ctx": self.ctx,
            "n_heads": self.n_heads, "n_layers": self.n_layers, "d_ff": self.d_ff,
            "device": self.device, "fitted": self.fitted, "steps": self.steps,
            "itos": list(self.itos), "state": blob, "resident": True,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "TorchTransformer":
        want = str(data.get("device") or "cpu")
        lm = cls(
            vocab=[t for t in (data.get("itos") or []) if t != UNK],
            dim=int(data.get("dim") or 8),
            ctx=int(data.get("ctx") or 8),
            n_heads=int(data.get("n_heads") or 2),
            n_layers=int(data.get("n_layers") or 2),
            d_ff=int(data.get("d_ff") or 32),
            device=want,
        )
        state = data.get("state") or {}
        if state:
            torch = lm.torch
            sd = {k: torch.tensor(v) for k, v in state.items()}
            lm.net.load_state_dict(sd, strict=False)
            lm.net.to(lm.device_obj)
        lm.fitted = int(data.get("fitted") or 0)
        lm.steps = int(data.get("steps") or 0)
        return lm


def _Stack(V, dim, ctx, n_heads, n_layers, d_ff, torch):
    class Stack(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.E = torch.nn.Embedding(V, dim)
            self.P = torch.nn.Embedding(ctx, dim)
            layer = torch.nn.TransformerEncoderLayer(
                d_model=dim, nhead=n_heads, dim_feedforward=d_ff,
                batch_first=True, dropout=0.0, activation="relu",
            )
            self.enc = torch.nn.TransformerEncoder(layer, num_layers=n_layers)
            self.out = torch.nn.Linear(dim, V)
            self._ctx = ctx

        def forward(self, ids):
            _B, T = ids.shape
            pos = torch.arange(T, device=ids.device).clamp(max=self._ctx - 1).unsqueeze(0)
            x = self.E(ids) + self.P(pos)
            mask = torch.triu(torch.ones(T, T, device=ids.device), diagonal=1).bool()
            x = self.enc(x, mask=mask)
            return self.out(x[:, -1, :])

    return Stack()
