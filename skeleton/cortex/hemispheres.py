"""Hemispheres — specialized tracts Jeeves can bind or acquire.

Left: sequential, linguistic, symbolic, TTK/DPS/recipe math.
Right: gestalt, spatial, analogical, era-feel, room grain.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from skeleton.cortex.port import Thought, tokens
from skeleton.forge.eras import ERA_IDS

_NUM = re.compile(r"[-+]?\d+(?:\.\d+)?")


class LeftHemisphere:
    """Analytic tract. Propositions over numbers, eras, recipes."""

    name = "left-local"
    scale = "hemisphere"
    slot = "left"

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        text = stimulus or ""
        nums = tuple(float(x) for x in _NUM.findall(text)[:8])
        found_eras = tuple(e for e in ERA_IDS if e.replace("_", " ") in text.lower() or e in text.lower())
        dps = context.get("pack_dps")
        ttk = context.get("pack_ttk") or {}
        props: List[str] = ["HP = DPS × TTK"]
        if dps is not None:
            props.append(f"primary_dps={dps}")
        if ttk:
            props.append("ttk " + ",".join(f"{k}:{v}" for k, v in list(ttk.items())[:4]))
        if found_eras:
            props.append("eras " + ",".join(found_eras[:3]))
        if nums:
            props.append("literals " + ",".join(f"{n:g}" for n in nums[:4]))
        ntok = len(tokens(text))
        conf = 0.62 + min(0.3, (len(props) + ntok / 40.0) / 8.0)
        return Thought(
            slot="left", kind="analytic",
            text=" ; ".join(props),
            confidence=conf,
            tags=("analytic", "symbolic", "left") + found_eras[:2],
            numbers=nums + ((float(dps),) if isinstance(dps, (int, float)) else ()),
        )


class RightHemisphere:
    """Gestalt tract. Analogies, spatial bias, era grain."""

    name = "right-local"
    scale = "hemisphere"
    slot = "right"

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        text = (stimulus or "").lower()
        tensor = context.get("tensor") or {}
        era = str(context.get("era") or "")
        hottest = str(context.get("hottest") or "")
        axes: List[Tuple[str, float]] = []
        if isinstance(tensor, dict):
            for k, v in tensor.items():
                if isinstance(v, (int, float)):
                    axes.append((k, float(v)))
        axes.sort(key=lambda kv: -kv[1])
        top = axes[:3]
        grind = next((v for k, v in axes if k == "grind"), 0.0)
        lethality = next((v for k, v in axes if k == "lethality"), 0.0)
        scarcity = next((v for k, v in axes if k == "scarcity"), 0.0)
        tempo = next((v for k, v in axes if k == "tempo"), 0.0)
        if grind >= 0.62:
            bias = "loot"
        elif scarcity >= 0.75 and lethality >= 0.55:
            bias = "heat"
        elif tempo >= 0.72 or lethality >= 0.70:
            bias = "combat"
        else:
            bias = "balanced"
        analog = era or ("horror" if "dread" in text or "horror" in text else "extraction_now")
        bits = [
            f"like {analog}",
            f"bias={bias}",
        ]
        if hottest:
            bits.append(f"face={hottest}")
        if top:
            bits.append("axes " + ",".join(f"{k}:{v:.2f}" for k, v in top))
        conf = 0.60 + min(0.3, (1 if era else 0) * 0.1 + len(top) * 0.06)
        return Thought(
            slot="right", kind="gestalt",
            text=" / ".join(bits),
            confidence=conf,
            tags=("gestalt", "spatial", "right", bias),
            numbers=tuple(v for _, v in top),
        )
