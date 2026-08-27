"""Torch / CUDA accel for the neo LM.

Lazy import. GameForge CI never loads this file unless someone
calls TinyTransformer.to('cuda') and torch is installed.

TorchAccel: same TinyTransformer weights, autograd SGD on cpu|cuda.
TorchTransformer: stacked TransformerEncoder (n_layers, n_heads, FFN)
on the bound device. Snapshot is a state_dict of lists.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from skeleton.cortex.port import tokens

UNK = "__unk__"


def _torch():
    import torch
    return torch


class TorchAccel:
    """Run one TinyTransformer step with autograd on cpu or cuda."""

    def __init__(self, lm: Any, device: str = "cpu") -> None:
        torch = _torch()
        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
        self.torch = torch
        self.lm = lm
        self.device = torch.device(device)
        self.device_name = "cuda" if self.device.type == "cuda" else "cpu"

    def _t(self, rows: List[List[float]], grad: bool = True):
        return self.torch.tensor(rows, dtype=self.torch.float32, device=self.device, requires_grad=grad)

    def _v(self, row: List[float], grad: bool = True):
        return self.torch.tensor(row, dtype=self.torch.float32, device=self.device, requires_grad=grad)

    def sgd(self, ids: Sequence[int], target: int, lr: float) -> float:
        torch = self.torch
        lm = self.lm
        E = self._t(lm.E)
        P = self._t(lm.P)
        Wq, Wk, Wv, Wo = self._t(lm.Wq), self._t(lm.Wk), self._t(lm.Wv), self._t(lm.Wo)
        Wout = self._t(lm.Wout)
        bout = self._v(lm.bout)
        idx = torch.tensor(list(ids), dtype=torch.long, device=self.device)
        pos = torch.arange(len(ids), device=self.device)
        X = E[idx] + P[pos]
        Q, K, V = X @ Wq.T, X @ Wk.T, X @ Wv.T
        heads = max(1, int(lm.n_heads))
        D = int(lm.dim)
        dh = max(1, D // heads)
        chunks = []
        for h in range(heads):
            Qh, Kh, Vh = Q[:, h * dh:(h + 1) * dh], K[:, h * dh:(h + 1) * dh], V[:, h * dh:(h + 1) * dh]
            scale = dh ** -0.5
            scores = Qh @ Kh.T * scale
            T = scores.size(0)
            mask = torch.triu(torch.ones(T, T, device=self.device), diagonal=1).bool()
            scores = scores.masked_fill(mask, float("-inf"))
            A = torch.softmax(scores, dim=-1)
            chunks.append(A @ Vh)
        C = torch.cat(chunks, dim=-1) if chunks else V
        attn = C[-1] @ Wo.T
        U = X[-1] + attn
        y = U
        extras = []
        if lm.d_ff and lm.W1:
            W1, W2 = self._t(lm.W1), self._t(lm.W2)
            b1, b2 = self._v(lm.b1), self._v(lm.b2)
            z = torch.relu(U @ W1.T + b1)
            y = U + z @ W2.T + b2
            extras = [W1, b1, W2, b2]
        logits = y @ Wout.T + bout
        tgt = torch.tensor([int(target)], dtype=torch.long, device=self.device)
        loss = torch.nn.functional.cross_entropy(logits.unsqueeze(0), tgt)
        loss.backward()
        params = [E, P, Wq, Wk, Wv, Wo, Wout, bout] + extras
        with torch.no_grad():
            for p in params:
                if p.grad is not None:
                    p.add_(p.grad, alpha=-float(lr))
        lm.E, lm.P = E.detach().cpu().tolist(), P.detach().cpu().tolist()
        lm.Wq, lm.Wk = Wq.detach().cpu().tolist(), Wk.detach().cpu().tolist()
        lm.Wv, lm.Wo = Wv.detach().cpu().tolist(), Wo.detach().cpu().tolist()
        lm.Wout, lm.bout = Wout.detach().cpu().tolist(), bout.detach().cpu().tolist()
        if extras:
            lm.W1, lm.b1 = extras[0].detach().cpu().tolist(), extras[1].detach().cpu().tolist()
            lm.W2, lm.b2 = extras[2].detach().cpu().tolist(), extras[3].detach().cpu().tolist()
        lm.steps += 1
        return float(loss.detach().cpu())

    def decode(self, prefix: str, n: int = 14, seed: int = 0) -> str:
        return " ".join(self.lm.generate(prefix, n=n, seed=seed))


class TorchTransformer:
    """Stacked TransformerEncoder on cpu|cuda. The high-standard neo LM."""

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
            "itos": list(self.itos), "state": blob,
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "TorchTransformer":
        lm = cls(
            vocab=[t for t in (data.get("itos") or []) if t != UNK],
            dim=int(data.get("dim") or 8),
            ctx=int(data.get("ctx") or 8),
            n_heads=int(data.get("n_heads") or 2),
            n_layers=int(data.get("n_layers") or 2),
            d_ff=int(data.get("d_ff") or 32),
            device=str(data.get("device") or "cpu"),
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
