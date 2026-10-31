"""Gradient accumulation. One averaged update every k token-windows."""
from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from skeleton.cortex.port import tokens


class Accumulator:
    def __init__(self, k: int = 4) -> None:
        self.k = max(1, int(k))
        self.bank: List[Tuple[List[int], int]] = []
        self.flushes = 0
        self.seen = 0

    def push(self, ids: Sequence[int], target: int) -> bool:
        self.bank.append((list(ids), int(target)))
        self.seen += 1
        return len(self.bank) >= self.k

    def flush(self, lm, *, lr: float = 0.04, weight_decay: float = 0.0) -> Dict[str, Any]:
        if not self.bank:
            return {"flushed": 0, "steps": int(getattr(lm, "steps", 0) or 0)}
        n = len(self.bank)
        scaled = float(lr) / float(max(1, n))
        if weight_decay > 0.0 and hasattr(lm, "_apply_weight_decay"):
            lm._apply_weight_decay(max(0.0, 1.0 - float(lr) * float(weight_decay)))
        losses: List[float] = []
        if hasattr(lm, "_sgd"):
            for ids, t in self.bank:
                loss = float(lm._sgd(list(ids), int(t), scaled))
                if math.isfinite(loss):
                    losses.append(loss)
        self.bank = []
        self.flushes += 1
        return {
            "flushed": n,
            "flushes": self.flushes,
            "mean_loss": (sum(losses) / len(losses)) if losses else 0.0,
            "steps": int(getattr(lm, "steps", 0) or 0),
            "lr": scaled,
        }

    def fit(
        self,
        lm,
        texts: Iterable[str],
        *,
        lr: float = 0.04,
        schedule: str = "flat",
        weight_decay: float = 0.0,
    ) -> Dict[str, Any]:
        n_tok = 0
        ctx = int(getattr(lm, "ctx", 6) or 6)
        corpus = list(texts)
        total_windows = 0
        for raw in corpus:
            body = tokens(raw)
            if len(body) >= 2:
                total_windows += len(body) - 1
        total_flushes = max(1, (total_windows + self.k - 1) // self.k)
        flush_idx = 0

        def _scheduled_lr(idx: int) -> float:
            if schedule == "cosine" and total_flushes > 1:
                frac = min(1.0, float(idx) / float(total_flushes - 1))
                return float(lr) * (0.1 + 0.9 * 0.5 * (1.0 + math.cos(math.pi * frac)))
            return float(lr)

        for raw in corpus:
            body = tokens(raw)
            if len(body) < 2:
                continue
            ids = [lm._id(t) for t in body]
            for i in range(1, len(ids)):
                if self.push(ids[max(0, i - ctx):i], ids[i]):
                    self.flush(lm, lr=_scheduled_lr(flush_idx), weight_decay=weight_decay)
                    flush_idx += 1
                n_tok += 1
            if hasattr(lm, "fitted"):
                lm.fitted = int(getattr(lm, "fitted", 0) or 0) + 1
        if self.bank:
            self.flush(lm, lr=_scheduled_lr(flush_idx), weight_decay=weight_decay)
        return {
            "tokens": n_tok,
            "flushes": self.flushes,
            "k": self.k,
            "steps": int(getattr(lm, "steps", 0) or 0),
            "schedule": schedule,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {"k": self.k, "flushes": self.flushes, "seen": self.seen,
                "bank": [{"ids": list(ids), "t": t} for ids, t in self.bank]}

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any]) -> "Accumulator":
        acc = cls(k=int((data or {}).get("k") or 4))
        acc.flushes = int((data or {}).get("flushes") or 0)
        acc.seen = int((data or {}).get("seen") or 0)
        for row in (data or {}).get("bank") or []:
            acc.bank.append((list(row.get("ids") or []), int(row.get("t") or 0)))
        return acc

    def to_dict(self) -> Dict[str, Any]:
        return {"k": self.k, "pending": len(self.bank), "flushes": self.flushes, "seen": self.seen}


def accumulate_fit(
    lm,
    texts: Iterable[str],
    *,
    k: int = 4,
    lr: float = 0.04,
    schedule: str = "flat",
    weight_decay: float = 0.0,
) -> Dict[str, Any]:
    return Accumulator(k=k).fit(lm, texts, lr=lr, schedule=schedule, weight_decay=weight_decay)
