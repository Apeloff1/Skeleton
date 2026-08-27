"""Curriculum — Jeeves trains on GameForge stimuli, evaluates on paraphrases.

The model in training does not need a corpus of language. It needs the
builder's closed world: era dialects, TTK identities, cockpit verbs,
room biases. Each item is a (train, held-out paraphrase) pair. An epoch
thinks the train set, acquires every slot, then scores recall on the
paraphrases. Held-out Jaccard > 0 is the proof the own-system
generalizes instead of parroting an exact fingerprint.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple
import re

from skeleton.forge.eras import ERA_IDS

Pair = Tuple[str, str]


def _era_pairs() -> List[Pair]:
    out: List[Pair] = []
    for era in ERA_IDS:
        words = era.replace("_", " ")
        out.append((
            f"{words} ttk elite dps",
            f"elite ttk {words} dps recipe",
        ))
    return out


CORE_PAIRS: List[Pair] = [
    ("soulslike extraction ttk elite dread",
     "extraction soulslike elite ttk dread rest"),
    ("compile ttk hp dps recipe sim",
     "recipe sim compile dps hp ttk"),
    ("era feel spatial gestalt dread cozy",
     "gestalt spatial era feel cozy dread layout"),
    ("metroidvania backtrack sequence",
     "backtrack metroidvania sequence map"),
    ("horror survival dread heat scarcity",
     "dread horror survival scarcity heat"),
    ("arcade golden age score ttk trash",
     "ttk arcade trash score golden age"),
    ("cozy wholesome intimacy grind farm",
     "farm intimacy cozy grind wholesome"),
    ("boomer shooter movement gun poetry ttk",
     "ttk movement shooter boomer gun poetry"),
    ("BIND SLOT left echo THINK compile",
     "THINK compile BIND SLOT left echo"),
    ("heat vent collapse extract late",
     "extract collapse vent heat late"),
    ("forge run soulslike extract hops cores bias heat",
     "soulslike extract hops cores heat bias forge run"),
    ("walk collapse extract late lock core bound",
     "extract lock core walk collapse late bound"),
]

WALK_PAIRS: List[Pair] = [
    ("HP = DPS x TTK ; observed mix trash=6 elite=2 boss=0 slack=0.70 soulslike",
     "soulslike observed mix trash=6 elite=2 boss=0 slack=0.70"),
    ("HP = DPS x TTK ; observed mix trash=4 elite=1 boss=0 slack=0.80 extraction now",
     "extraction now observed mix trash=4 elite=1 boss=0 slack=0.80"),
    ("HP = DPS x TTK ; observed mix trash=2 elite=0 boss=0 slack=0.88 arcade golden age",
     "arcade golden age observed mix trash=2 elite=0 boss=0 slack=0.88"),
]

_MIX_RE = re.compile(r"mix trash=(\d+) elite=(\d+) boss=(\d+) slack=([0-9.]+)")


def _ingest_observed_mix(neo, train_s: str) -> None:
    m = _MIX_RE.search(train_s or "")
    if not m or neo is None or not hasattr(neo, "own"):
        return
    from skeleton.cortex.distill import ability_from
    from skeleton.cortex.port import Thought, tokens
    trash, elite, boss, slack = int(m.group(1)), int(m.group(2)), int(m.group(3)), float(m.group(4))
    stim_toks = set(tokens(train_s))
    era = "soulslike"
    for e in ERA_IDS:
        parts = tuple(e.split("_"))
        if e in stim_toks or (parts and all(p in stim_toks for p in parts)):
            era = e
            break
    thought = Thought(
        slot="left", kind="walk",
        text=(
            f"HP = DPS × TTK ; observed mix trash={trash} "
            f"elite={elite} boss={boss} slack={slack:.2f}"
        ),
        confidence=min(1.0, 0.55 + 0.45 * max(0.0, slack)),
        tags=("analytic", "mix", "walk", "observed", "left", era),
        numbers=(float(trash), float(elite), float(boss), slack),
    )
    neo.own.ingest(ability_from(thought, train_s), train_s)


def default_curriculum() -> List[Pair]:
    seen = set()
    out: List[Pair] = []
    for pair in CORE_PAIRS + WALK_PAIRS + _era_pairs():
        if pair[0] in seen:
            continue
        seen.add(pair[0])
        out.append(pair)
    return out


def train(neo, *, epochs: int = 1, pairs: Sequence[Pair] | None = None,
          auto_surpass: bool = True) -> Dict[str, Any]:
    """One or more epochs. Returns held-out recall metrics."""
    from skeleton.cortex.port import SLOTS

    curriculum = list(pairs or default_curriculum())
    epochs = max(1, int(epochs))
    held_hits = 0
    held_total = 0
    last_status: Dict[str, Any] = {}
    for _ in range(epochs):
        for train_s, _held in curriculum:
            neo.think(train_s)
            _ingest_observed_mix(neo, train_s)
            for slot in SLOTS:
                port = getattr(neo, "slots", {}).get(slot)
                if port is not None and hasattr(port, "fit"):
                    port.fit(train_s)
        for slot in SLOTS:
            neo.acquire(slot)
        if auto_surpass:
            for slot in SLOTS:
                neo.surpass(slot)
        for _train_s, held in curriculum:
            tr = neo.think(held)
            held_total += 1
            if tr.used_own or (tr.recalled_jaccard and tr.recalled_jaccard >= 0.4):
                held_hits += 1
        last_status = neo.status()
    rate = (held_hits / held_total) if held_total else 0.0
    lms = {}
    slots = getattr(neo, "slots", {}) or {}
    for slot, port in slots.items():
        lm = getattr(port, "lm", None)
        neural = getattr(port, "neural", None)
        lms[slot] = {
            "ngram_fitted": int(getattr(lm, "fitted", 0) or 0),
            "neural_steps": int(getattr(neural, "steps", 0) or 0),
            "neural_fitted": int(getattr(neural, "fitted", 0) or 0),
        }
    return {
        "epochs": epochs,
        "items": len(curriculum),
        "held_total": held_total,
        "held_hits": held_hits,
        "held_rate": round(rate, 4),
        "own": last_status.get("own"),
        "acquired": last_status.get("acquired"),
        "surpass": last_status.get("surpass"),
        "shadow": last_status.get("shadow"),
        "backends": last_status.get("backends"),
        "lms": lms,
    }
