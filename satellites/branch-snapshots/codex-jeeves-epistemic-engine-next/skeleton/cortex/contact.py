"""Contact — Jeeves writes on every teacher it touches.

A man-made mouth (HuggingFace, Kimi, any injected teacher) does not
pass through the house unchanged. Contact is the law:

  1. Attach a Jeeves-owned LoRA onto the teacher copy (stand-in or local HF).
  2. SGD that copy on the GameForge dialect (cosine).
  3. Residual-correct: neo hidden Hebbs against teacher hidden.
  4. Absorb the improved copy into both neo mouths.
  5. Store the adapter in own.models[slot].

Remote APIs cannot accept weight writes. The house keeps a living copy
and a corrector; the next decode is teacher-text passed through the
improved stand-in. Magnitude is birth_ppl / contact_ppl on that copy.
That is how a man-made weight becomes a man-and-machine weight.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from skeleton.cortex.curriculum import CORE_PAIRS
from skeleton.cortex.gossip import absorb_mouth
from skeleton.cortex.lora import LoRABank

TEACHER_NAMES = {"huggingface", "kimi", "hf", "moonshot", "teacher"}


def is_teacher(port) -> bool:
    name = str(getattr(port, "name", "") or "").lower()
    if name in TEACHER_NAMES:
        return True
    think = getattr(port, "think", None)
    return False


def teacher_lm(port):
    xf = getattr(port, "transformer", None)
    if xf is not None:
        return xf
    return getattr(port, "standin", None)


def _dialect(stimulus: str) -> List[str]:
    texts = [stimulus] if stimulus else []
    texts.extend(a for a, _ in list(CORE_PAIRS)[:4])
    return [t for t in texts if t]


class ContactEngine:
    """Per-cortex contact ledger. Birth ppl is the denominator of magnitude."""

    def __init__(self) -> None:
        self.contacts = 0
        self.birth_ppl: Dict[str, float] = {}
        self.last: Dict[str, Any] = {}
        self.magnitudes: Dict[str, float] = {}

    def touch(self, neo, slot: str, stimulus: str) -> Dict[str, Any]:
        port = (getattr(neo, "slots", {}) or {}).get(slot)
        if port is None or not is_teacher(port):
            return {"contacted": 0, "reason": "not-teacher", "slot": slot}
        lm = teacher_lm(port)
        if lm is None:
            return {"contacted": 0, "reason": "no-copy", "slot": slot}

        texts = _dialect(stimulus or "")
        if slot not in self.birth_ppl and hasattr(lm, "perplexity"):
            try:
                self.birth_ppl[slot] = float(lm.perplexity(texts[:4] or ["plan tensor ttk"]))
            except Exception:
                self.birth_ppl[slot] = float("inf")

        if getattr(lm, "lora", None) is None:
            LoRABank(rank=4, alpha=8.0, seed=29).attach(lm)

        steps = 0
        if hasattr(lm, "fit"):
            # Eight inner epochs per contact — the house does not tap the
            # teacher once. It works the copy until the dialect bites.
            for _ in range(8):
                steps += int(lm.fit(texts, lr=0.05, schedule="cosine"))

        hebb = 0.0
        h_t = list(lm.hidden(stimulus or "plan tensor ttk")) if hasattr(lm, "hidden") else []
        h_n = neo._hidden(stimulus or "plan tensor ttk") if hasattr(neo, "_hidden") else []
        cc = getattr(neo, "callosum", None)
        if cc is not None and h_t and h_n and hasattr(cc, "hebb_tracts"):
            hebb = float(cc.hebb_tracts(h_t, h_n, lr=0.05))

        absorbed = {"absorbed": 0}
        xf = getattr(neo, "transformer", None)
        if xf is not None:
            absorbed = absorb_mouth(xf, lm, alpha=0.25)
        rms = getattr(neo, "neo_rms", None)
        if rms is not None:
            absorbed["neo_rms"] = absorb_mouth(rms, lm, alpha=0.15)

        now = float("inf")
        if hasattr(lm, "perplexity"):
            try:
                now = float(lm.perplexity(texts[:4] or ["plan tensor ttk"]))
            except Exception:
                now = float("inf")
        birth = float(self.birth_ppl.get(slot) or now or 1.0)
        mag = (birth / now) if now > 0 and now < 1e8 and birth < 1e8 else 1.0
        self.magnitudes[slot] = mag
        self.contacts += 1

        if hasattr(neo, "own") and hasattr(port, "snapshot"):
            neo.own.ingest_model(f"{slot}:teacher", port.snapshot())
            if getattr(lm, "lora", None) is not None:
                neo.own.ingest_model(f"{slot}:lora", lm.lora.snapshot())

        card = {
            "contacted": 1,
            "slot": slot,
            "backend": getattr(port, "name", type(port).__name__),
            "steps": steps,
            "hebb": hebb,
            "absorb": absorbed,
            "birth_ppl": birth if birth < 1e8 else None,
            "contact_ppl": now if now < 1e8 else None,
            "magnitude": round(mag, 4),
            "contacts": self.contacts,
            "lora": bool(getattr(lm, "lora", None) is not None),
        }
        self.last = card
        return card

    def snapshot(self) -> Dict[str, Any]:
        return {
            "contacts": self.contacts,
            "birth_ppl": dict(self.birth_ppl),
            "magnitudes": dict(self.magnitudes),
            "last": dict(self.last),
        }

    def restore(self, data: Optional[Dict[str, Any]]) -> None:
        if not data:
            return
        self.contacts = int(data.get("contacts") or 0)
        self.birth_ppl = {str(k): float(v) for k, v in (data.get("birth_ppl") or {}).items()}
        self.magnitudes = {str(k): float(v) for k, v in (data.get("magnitudes") or {}).items()}
        self.last = dict(data.get("last") or {})
