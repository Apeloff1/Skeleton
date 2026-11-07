"""Interchange mouths — HuggingFace and Kimi are welcome.

Closed-world birth is the default. A ModelPort may still bind a foreign
teacher: HuggingFace weights when `transformers` is present, Kimi when
a Moonshot key is present. Missing packages or keys degrade to a local
TinyTransformer stand-in that still speaks fit/decode/snapshot/ppl.
Neo acquires the teacher by distilling text into own-system and SGD on
both neo mouths. No import-time download. No required network.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

from skeleton.cortex.lm import gameforge_vocab
from skeleton.cortex.port import Thought
from skeleton.cortex.transformer import TinyTransformer


def _standin(*, seed: int, name: str) -> TinyTransformer:
    return TinyTransformer(
        vocab=gameforge_vocab(), dim=8, ctx=8, seed=seed,
        n_heads=2, n_layers=1, d_ff=16,
    )


def probe_interchange() -> Dict[str, Any]:
    hf = False
    try:
        import transformers  # noqa: F401
        hf = True
    except Exception:
        hf = False
    kimi_key = bool(os.environ.get("KIMI_API_KEY") or os.environ.get("MOONSHOT_API_KEY"))
    return {
        "huggingface": hf,
        "kimi_key": kimi_key,
        "kimi_base": os.environ.get("KIMI_BASE_URL") or "https://api.moonshot.ai/v1",
        "standin": True,
    }


class HuggingFaceBackend:
    """ModelPort. Cortex stays closed-world: local stand-in mouth only."""

    def __init__(
        self,
        model_id: str = "sshleifer/tiny-gpt2",
        *,
        slot: str = "left",
        name: str = "huggingface",
        max_new: int = 24,
    ) -> None:
        self.slot = slot
        self.name = name
        self.scale = "injected"
        self.model_id = str(model_id)
        self.max_new = max(4, int(max_new))
        self.remote = False
        self._tok = None
        self._model = None
        self.standin = _standin(seed=41, name=name)
        self._maybe_load()

    def _maybe_load(self) -> None:
        # Closed-world cortex: never pull remote weights into this package.
        # Bindable teacher identity remains; decode/fit use the local stand-in.
        self.remote = False
        self._tok = None
        self._model = None

    @property
    def transformer(self):
        return None if self.remote else self.standin

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        text = self.decode(stimulus or "", n=self.max_new, seed=0)
        return Thought(
            slot=self.slot, kind="teacher",
            text=text[:400],
            confidence=0.84 if self.remote else 0.62,
            tags=("teacher", "huggingface", self.slot) + (("remote",) if self.remote else ("standin",)),
        )

    def fit(self, text: str) -> int:
        if self.remote:
            return 0
        return int(self.standin.fit([text], schedule="cosine"))

    def decode(self, stimulus: str, *, n: int = 8, seed: int = 0) -> str:
        if self.remote and self._tok is not None and self._model is not None:
            try:
                import torch
                ids = self._tok(stimulus or "", return_tensors="pt")
                out = self._model.generate(**ids, max_new_tokens=max(4, int(n)), do_sample=False)
                return str(self._tok.decode(out[0], skip_special_tokens=True))[:400]
            except Exception:
                pass
        return str(self.standin.decode(stimulus or "", n=n, seed=seed))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "huggingface",
            "slot": self.slot,
            "name": self.name,
            "model_id": self.model_id,
            "remote": self.remote,
            "standin": None if self.remote else self.standin.snapshot(),
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], *, slot: str | None = None) -> "HuggingFaceBackend":
        sl = slot or str((data or {}).get("slot") or "left")
        obj = cls(
            str((data or {}).get("model_id") or "sshleifer/tiny-gpt2"),
            slot=sl, name=str((data or {}).get("name") or "huggingface"),
        )
        snap = (data or {}).get("standin")
        if snap and not obj.remote:
            from skeleton.cortex.transformer import TinyTransformer
            obj.standin = TinyTransformer.from_snapshot(snap)
        return obj

    def perplexity(self, texts: Iterable[str]) -> float:
        if self.remote:
            return 1.0
        return float(self.standin.perplexity(list(texts)))


class KimiBackend:
    """ModelPort. Moonshot/Kimi chat when a key exists; else stand-in."""

    def __init__(
        self,
        model: str = "kimi-k2-0711-preview",
        *,
        slot: str = "right",
        name: str = "kimi",
        timeout: float = 8.0,
    ) -> None:
        self.slot = slot
        self.name = name
        self.scale = "injected"
        self.model = str(model)
        self.timeout = float(timeout)
        self.base = os.environ.get("KIMI_BASE_URL") or "https://api.moonshot.ai/v1"
        self.key = os.environ.get("KIMI_API_KEY") or os.environ.get("MOONSHOT_API_KEY") or ""
        self.remote = bool(self.key)
        self.standin = _standin(seed=43, name=name)
        self.last_error = ""

    @property
    def transformer(self):
        return None if self.remote else self.standin

    def _chat(self, stimulus: str, n: int) -> str:
        url = self.base.rstrip("/") + "/chat/completions"
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a GameForge cortex teacher. Short builder dialect."},
                {"role": "user", "content": stimulus or ""},
            ],
            "max_tokens": max(16, int(n) * 8),
            "temperature": 0.2,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            return str((((raw.get("choices") or [{}])[0].get("message") or {}).get("content")) or "")[:400]
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            self.last_error = type(exc).__name__
            self.remote = False
            return ""

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        text = self.decode(stimulus or "", n=12, seed=0)
        return Thought(
            slot=self.slot, kind="teacher",
            text=text[:400],
            confidence=0.88 if self.key and not self.last_error else 0.62,
            tags=("teacher", "kimi", self.slot) + (("remote",) if self.key and not self.last_error else ("standin",)),
        )

    def fit(self, text: str) -> int:
        if self.key and not self.last_error:
            return 0
        return int(self.standin.fit([text], schedule="cosine"))

    def decode(self, stimulus: str, *, n: int = 8, seed: int = 0) -> str:
        if self.key:
            out = self._chat(stimulus, n)
            if out:
                return out
        return str(self.standin.decode(stimulus or "", n=n, seed=seed))

    def snapshot(self) -> Dict[str, Any]:
        return {
            "kind": "kimi",
            "slot": self.slot,
            "name": self.name,
            "model": self.model,
            "base": self.base,
            "remote": bool(self.key) and not self.last_error,
            "standin": self.standin.snapshot(),
        }

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], *, slot: str | None = None) -> "KimiBackend":
        sl = slot or str((data or {}).get("slot") or "right")
        obj = cls(str((data or {}).get("model") or "kimi-k2-0711-preview"), slot=sl,
                  name=str((data or {}).get("name") or "kimi"))
        snap = (data or {}).get("standin")
        if snap:
            from skeleton.cortex.transformer import TinyTransformer
            obj.standin = TinyTransformer.from_snapshot(snap)
        return obj

    def perplexity(self, texts: Iterable[str]) -> float:
        return float(self.standin.perplexity(list(texts)))


def distill_teacher(neo, slot: str, stimulus: str) -> Dict[str, Any]:
    """Teacher speaks. Neo SGD on that text. Own-system stores the ability."""
    port = (getattr(neo, "slots", {}) or {}).get(slot)
    if port is None:
        return {"distilled": 0, "reason": "missing-slot"}
    thought = port.think(stimulus or "", {})
    text = thought.text or ""
    n_neo = n_rms = 0
    xf = getattr(neo, "transformer", None)
    if xf is not None and text:
        n_neo = int(xf.fit([text], lr=0.03, schedule="cosine"))
    rms = getattr(neo, "neo_rms", None)
    if rms is not None and text:
        n_rms = int(rms.fit([text], lr=0.03, schedule="cosine"))
    if hasattr(neo, "own") and hasattr(neo, "ledger"):
        from skeleton.cortex.distill import ability_from
        neo.ledger.record(thought, stimulus or "")
        neo.own.ingest(ability_from(thought, stimulus or ""), stimulus or "")
        if hasattr(port, "snapshot"):
            neo.own.ingest_model(slot, port.snapshot())
    return {
        "distilled": 1,
        "slot": slot,
        "backend": getattr(port, "name", type(port).__name__),
        "remote": "remote" in (thought.tags or ()),
        "neo_steps": n_neo,
        "rms_steps": n_rms,
        "text": text[:160],
    }
