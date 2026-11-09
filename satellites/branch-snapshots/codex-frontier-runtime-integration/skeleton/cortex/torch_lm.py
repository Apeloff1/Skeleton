"""Torch / CUDA accel for the neo LM.

Lazy import. GameForge CI never loads this file unless someone
calls TinyTransformer.to() and torch is installed.

TorchAccel: same TinyTransformer weights, pinned on cpu|cuda,
autograd SGD through stacked Pre-LN blocks. Python lists catch
up on sync() / snapshot(). GPU is a harness, not a rewrite.

TorchTransformer: optional nn.TransformerEncoder stack, restored
only when a snapshot kind is torch-stack.
"""
from __future__ import annotations

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
        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
        self.torch = torch
        self.lm = lm
        self.device = torch.device(device)
        self.device_name = "cuda" if self.device.type == "cuda" else "cpu"
        self.resident = False
        self._E = self._P = self._Wout = self._bout = None
        self._layers: List[Dict[str, Any]] = []

    def _t2(self, rows: List[List[float]], grad: bool = True):
        return self.torch.tensor(rows, dtype=self.torch.float32, device=self.device, requires_grad=grad)

    def _t1(self, row: List[float], grad: bool = True):
        return self.torch.tensor(row, dtype=self.torch.float32, device=self.device, requires_grad=grad)

    def pin(self) -> "TorchAccel":
        """Upload python weights once. Subsequent SGD stays on-device."""
        lm = self.lm
        self._E = self._t2(lm.E)
        self._P = self._t2(lm.P)
        self._Wout = self._t2(lm.Wout)
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
                "W1": None, "b1": None, "W2": None, "b2": None,
                "ln2_g": None, "ln2_b": None,
            }
            W1 = getattr(L, "W1", None)
            if W1:
                blob["W1"] = self._t2(W1)
                blob["b1"] = self._t1(getattr(L, "b1", [0.0] * len(W1)))
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
        yield self._E
        yield self._P
        yield self._Wout
        yield self._bout
        for L in self._layers:
            for v in L.values():
                if v is not None:
                    yield v

    def sync(self) -> None:
        """Python lists catch up. Snapshot / to() / fallback call this."""
        if not self.resident or self._E is None:
            return
        lm = self.lm
        lm.E = self._E.detach().cpu().tolist()
        lm.P = self._P.detach().cpu().tolist()
        lm.Wout = self._Wout.detach().cpu().tolist()
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
                target.W2 = blob["W2"].detach().cpu().tolist()
                target.b2 = blob["b2"].detach().cpu().tolist()
                if hasattr(target, "ln2_g") and blob.get("ln2_g") is not None:
                    target.ln2_g = blob["ln2_g"].detach().cpu().tolist()
                    target.ln2_b = blob["ln2_b"].detach().cpu().tolist()

    def _forward_ids(self, ids: Sequence[int]):
        torch = self.torch
        lm = self.lm
        if not self.resident:
            self.pin()
        idx = torch.tensor(list(ids), dtype=torch.long, device=self.device)
        pos = torch.arange(len(ids), device=self.device).clamp(max=lm.ctx - 1)
        X = self._E[idx] + self._P[pos]
        D = int(lm.dim)
        heads = max(1, int(lm.n_heads))
        dh = max(1, D // heads)
        T = X.size(0)
        for blob in self._layers:
            Xn = torch.nn.functional.layer_norm(X, (D,), blob["ln1_g"], blob["ln1_b"])
            Q, K, V = Xn @ blob["Wq"].T, Xn @ blob["Wk"].T, Xn @ blob["Wv"].T
            Q, K = self._rope(Q), self._rope(K)
            chunks = []
            for h in range(heads):
                Qh = Q[:, h * dh:(h + 1) * dh]
                Kh = K[:, h * dh:(h + 1) * dh]
                Vh = V[:, h * dh:(h + 1) * dh]
                scale = dh ** -0.5
                scores = Qh @ Kh.T * scale
                mask = torch.triu(torch.ones(T, T, device=self.device), diagonal=1).bool()
                scores = scores.masked_fill(mask, float("-inf"))
                A = torch.softmax(scores, dim=-1)
                chunks.append(A @ Vh)
            C = torch.cat(chunks, dim=-1) if chunks else V
            X = X + C @ blob["Wo"].T
            if blob.get("W1") is not None:
                Un = torch.nn.functional.layer_norm(X, (D,), blob["ln2_g"], blob["ln2_b"])
                hid = Un @ blob["W1"].T + blob["b1"]
                z = self._gelu(hid)
                X = X + z @ blob["W2"].T + blob["b2"]
        return X[-1] @ self._Wout.T + self._bout, X[-1]

    def _rope(self, X):
        """Match attn.apply_rope: even/odd pairs, θ = pos / 10000^(i/d)."""
        torch = self.torch
        T, D = X.shape
        d = D - (D % 2)
        if d < 2:
            return X
        out = X.clone()
        pos = torch.arange(T, device=X.device, dtype=X.dtype).unsqueeze(1)
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

    def logits(self, ids: Sequence[int]) -> List[float]:
        with self.torch.no_grad():
            y, _ = self._forward_ids(ids)
            return y.detach().cpu().tolist()

    def hidden(self, ids: Sequence[int]) -> List[float]:
        with self.torch.no_grad():
            _, h = self._forward_ids(ids)
            return h.detach().cpu().tolist()

    def sgd(self, ids: Sequence[int], target: int, lr: float) -> float:
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
        with torch.no_grad():
            for p in self._params():
                if p.grad is not None:
                    p.add_(p.grad, alpha=-float(lr))
        self.lm.steps += 1
        return float(loss.detach().cpu())

    def decode(self, prefix: str, n: int = 14, seed: int = 0) -> str:
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
                logits, _ = self._forward_ids(window)
                p = torch.softmax(logits.float().cpu(), dim=-1)
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
        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
        self.torch = torch
        self.device_obj = torch.device(device)
        self.device = "cuda" if self.device_obj.type == "cuda" else "cpu"
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
        if device in {"cuda", "gpu"} and not torch.cuda.is_available():
            self.requested = "cuda"
            self.device = "cpu"
            self.device_obj = torch.device("cpu")
            self.net.to(self.device_obj)
            return self
        want = "cuda" if device in {"cuda", "gpu"} else "cpu"
        self.requested = want
        self.device = want if (want != "cuda" or torch.cuda.is_available()) else "cpu"
        self.device_obj = torch.device(self.device)
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
