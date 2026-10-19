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

    def __init__(self) -> None:
        from skeleton.cortex.learned import LearnedWeights
        self.weights = LearnedWeights(
            order=2, dim=8, seed=11, attn=True, ctx=6,
            n_heads=2, n_layers=1, d_ff=16,
        )

    @property
    def lm(self):
        return self.weights.lm

    @property
    def neural(self):
        return self.weights.neural

    @property
    def transformer(self):
        return self.weights.transformer

    def fit(self, text: str) -> int:
        return self.weights.fit(text)

    def snapshot(self) -> dict:
        return self.weights.snapshot()

    def perplexity(self, texts) -> float:
        xf = self.transformer
        if xf is not None and hasattr(xf, "perplexity"):
            return float(xf.perplexity(texts))
        return float("inf")

    def decode(self, stimulus: str, *, n: int = 8, seed: int = 0) -> str:
        xf = self.transformer
        if xf is not None and hasattr(xf, "decode"):
            return str(xf.decode(stimulus or "", n=n, seed=seed))
        return (stimulus or "")[:160]

    @classmethod
    def from_snapshot(cls, data, *, slot: str | None = None) -> "LeftHemisphere":
        obj = cls()
        if data:
            obj.weights.restore(data)
        return obj

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
        tensor = context.get("tensor") or {}
        def _ax(name: str) -> float:
            v = tensor.get(name) if isinstance(tensor, dict) else None
            return float(v) if isinstance(v, (int, float)) else 0.0
        tempo, lethality, risk, spectacle = _ax("tempo"), _ax("lethality"), _ax("risk"), _ax("spectacle")
        trash = 1 + int(round(max(0.0, min(1.0, tempo)) * 3))
        elite = (1 if lethality >= 0.50 else 0) + (1 if lethality >= 0.80 else 0)
        boss = 1 if (risk >= 0.75 and lethality >= 0.60) else 0
        if spectacle >= 0.80 and boss == 0:
            elite = max(elite, 1)
        props.append(f"mix trash={trash} elite={elite} boss={boss}")
        ntok = len(tokens(text))
        conf = 0.62 + min(0.3, (len(props) + ntok / 40.0) / 8.0)
        mix = (float(trash), float(elite), float(boss))
        dps_n = (float(dps),) if isinstance(dps, (int, float)) else ()
        xf = self.transformer
        if xf is not None and hasattr(xf, "decode"):
            draft = str(xf.decode(text or "ttk dps hp", n=5, seed=11) or "").strip()
            if draft:
                props.append("DRAFT " + draft)
        return Thought(
            slot="left", kind="analytic",
            text=" ; ".join(props),
            confidence=conf,
            tags=("analytic", "symbolic", "left", "mix") + found_eras[:2],
            numbers=nums + dps_n + mix,
        )

    def analyze_game_math(self, stimulus: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Compute deterministic combat, thermal, fixed-tick, and economy envelopes for game creation."""
        ctx = dict(context or {})
        thought = self.think(stimulus, ctx)
        era = str(ctx.get("era") or "extraction_now")
        from skeleton.forge.eras import ERA_IDS, compile_era

        era_key = era if era in ERA_IDS else "extraction_now"
        for candidate in ERA_IDS:
            if candidate in (stimulus or "").lower() or candidate.replace("_", " ") in (stimulus or "").lower():
                era_key = candidate
                break
        pack = compile_era(era_key)
        dps = float(ctx.get("pack_dps") or pack["primary_dps"])
        ttk_map = dict(pack["ttk"])
        if isinstance(ctx.get("pack_ttk"), dict):
            for k, v in ctx["pack_ttk"].items():
                if isinstance(v, (int, float)) and float(v) > 0:
                    ttk_map[k] = float(v)
        heat_cfg = pack["heat"]
        rec = pack["recipes"][0]
        shot_heat_per_sec = float(rec["heat"]) * (float(rec["rpm"]) / 60.0)
        passive_cool = float(heat_cfg["passive_cool"])
        net_heat_rate = max(0.0, shot_heat_per_sec - passive_cool)
        vent_duty_cycle = round(
            net_heat_rate / max(shot_heat_per_sec, 1e-6) if net_heat_rate > 0 else 0.0,
            4,
        )
        thermal_multiplier = round(1.0 / max(0.25, 1.0 - 0.5 * vent_duty_cycle), 4)
        mix = thought.numbers[-3:] if len(thought.numbers) >= 3 else (2.0, 1.0, 0.0)
        trash_n, elite_n, boss_n = int(round(mix[0])), int(round(mix[1])), int(round(mix[2]))
        ideal_wave_s = (
            trash_n * float(ttk_map.get("trash", 1.0))
            + elite_n * float(ttk_map.get("elite", 5.0))
            + boss_n * float(ttk_map.get("boss", 60.0))
        )
        thermal_wave_s = round(ideal_wave_s * thermal_multiplier, 3)
        collapse_max = float(ctx.get("collapse_max") or pack["session"]["collapse_max"])
        wave_budget_ratio = round(thermal_wave_s / max(collapse_max, 1.0), 4)
        # Fixed-tick 60Hz budget split (ms): input + sim + collision + audio + render <= 16.67ms
        tick_hz = int(ctx.get("tick_hz") or 60)
        frame_budget_ms = round(1000.0 / max(15, tick_hz), 2)
        # Economy tap/sink equilibrium: sink ratio targeted in [0.75, 0.92] to avoid runaway inflation
        tap_sink_ratio = round(min(0.92, max(0.72, 0.78 + 0.04 * elite_n + 0.06 * boss_n)), 4)
        return {
            "era": era_key,
            "primary_dps": round(dps, 2),
            "ttk_targets": {k: round(float(v), 3) for k, v in ttk_map.items()},
            "enemy_hp": {
                "trash": round(dps * float(ttk_map.get("trash", 1.0)), 1),
                "elite": round(dps * float(ttk_map.get("elite", 5.0)), 1),
                "boss": round(dps * float(ttk_map.get("boss", 60.0)), 1),
            },
            "encounter_mix": {"trash": trash_n, "elite": elite_n, "boss": boss_n},
            "vent_duty_cycle": vent_duty_cycle,
            "thermal_multiplier": thermal_multiplier,
            "ideal_wave_s": round(ideal_wave_s, 3),
            "thermal_wave_s": thermal_wave_s,
            "collapse_max_s": round(collapse_max, 2),
            "wave_budget_ratio": wave_budget_ratio,
            "fixed_tick": {
                "hz": tick_hz,
                "dt_s": round(1.0 / max(15, tick_hz), 6),
                "frame_budget_ms": frame_budget_ms,
                "max_catchup_ticks": 4,
            },
            "economy_equilibrium": {
                "tap_sink_ratio": tap_sink_ratio,
                "inflation_guarded": 0.70 <= tap_sink_ratio <= 0.95,
            },
        }


class RightHemisphere:
    """Gestalt tract. Analogies, spatial bias, era grain."""

    name = "right-local"
    scale = "hemisphere"
    slot = "right"

    def __init__(self) -> None:
        from skeleton.cortex.learned import LearnedWeights
        self.weights = LearnedWeights(
            order=2, dim=8, seed=13, attn=True, ctx=6,
            n_heads=2, n_layers=1, d_ff=16,
        )

    @property
    def lm(self):
        return self.weights.lm

    @property
    def neural(self):
        return self.weights.neural

    @property
    def transformer(self):
        return self.weights.transformer

    def fit(self, text: str) -> int:
        return self.weights.fit(text)

    def snapshot(self) -> dict:
        return self.weights.snapshot()

    def perplexity(self, texts) -> float:
        xf = self.transformer
        if xf is not None and hasattr(xf, "perplexity"):
            return float(xf.perplexity(texts))
        return float("inf")

    def decode(self, stimulus: str, *, n: int = 8, seed: int = 0) -> str:
        xf = self.transformer
        if xf is not None and hasattr(xf, "decode"):
            return str(xf.decode(stimulus or "", n=n, seed=seed))
        return (stimulus or "")[:160]

    @classmethod
    def from_snapshot(cls, data, *, slot: str | None = None) -> "RightHemisphere":
        obj = cls()
        if data:
            obj.weights.restore(data)
        return obj

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
        xf = self.transformer
        if xf is not None and hasattr(xf, "decode"):
            draft = str(xf.decode(text or "era soul dread", n=5, seed=13) or "").strip()
            if draft:
                bits.append("DRAFT " + draft)
        conf = 0.60 + min(0.3, (1 if era else 0) * 0.1 + len(top) * 0.06)
        return Thought(
            slot="right", kind="gestalt",
            text=" / ".join(bits),
            confidence=conf,
            tags=("gestalt", "spatial", "right", bias),
            numbers=tuple(v for _, v in top),
        )

    def synthesize_spatial_aesthetic_profile(
        self,
        stimulus: str,
        context: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Synthesize level topology, art-scale ladder, silhouette contrast, and audio cadence."""
        ctx = dict(context or {})
        thought = self.think(stimulus, ctx)
        text = (stimulus or "").lower()
        era = str(ctx.get("era") or "")
        if not era:
            for candidate in ERA_IDS:
                if candidate in text or candidate.replace("_", " ") in text:
                    era = candidate
                    break
        era = era or "extraction_now"
        bias = next((b for b in ("loot", "combat", "heat", "balanced") if b in thought.tags), "balanced")

        if era in {"metroidvania", "immersive_sim", "stealth"} or "backtrack" in text or "lock" in text:
            topology = "ability_gated_lattice"
        elif era in {"soulslike", "horror_survival", "extraction_now"} or bias == "heat":
            topology = "hub_and_extraction_loop"
        elif era in {"boomer_shooter", "arcade_golden_age", "bullet_heaven", "fighting_game"} or bias == "combat":
            topology = "arena_combat_gauntlet"
        elif era in {"jrpg", "crpg", "visual_novel", "deckbuilder"}:
            topology = "branching_act_hub"
        else:
            topology = "landmark_spoke_region"

        if era in {"boomer_shooter", "fighting_game", "bullet_heaven", "arcade_golden_age"}:
            bpm = 148
            telegraph_ticks = 14
        elif era in {"soulslike", "horror_survival", "stealth"}:
            bpm = 84
            telegraph_ticks = 24
        elif era in {"cozy_wholesome", "walking_sim", "visual_novel", "city_builder"}:
            bpm = 96
            telegraph_ticks = 30
        else:
            bpm = 116
            telegraph_ticks = 18

        palette_map = {
            "heat": "dusk_copper_high_contrast",
            "combat": "harbor_gold_silhouette",
            "loot": "field_gold_landmark",
            "balanced": "hearth_linen_readable",
        }
        return {
            "era": era,
            "spatial_bias": bias,
            "level_topology": topology,
            "art_scale_ladder": {
                "plan_tiers": (32768, 16384, 8192, 4096, 2048, 1024, 512, 256),
                "authoring_divisor": 2,
                "allocates_65536_buffer": False,
                "palette_profile": palette_map.get(bias, "hearth_linen_readable"),
                "silhouette_contrast": "shape_plus_value",
            },
            "combat_readability": {
                "telegraph_ticks": telegraph_ticks,
                "phases_order": ("approach", "threat", "choice", "resolution", "rest"),
                "max_slice_boss_phases": 2,
            },
            "audio_cadence": {
                "bpm": bpm,
                "quarter_note_s": round(60.0 / float(bpm), 4),
                "sync_to_fixed_tick": True,
            },
        }


def ttk_oracle(stimulus: str, context: Dict[str, Any]) -> Thought:
    """Injected left tract: mix from TTK × collapse, never a boss.

    Thermal tax is 4× on a soulslike. Fits 40% of collapse in trash,
    one elite if 4× elite TTK is under half the timer. Boss is always
    dropped — that is the oracle's entire personality.
    """
    ttk = context.get("pack_ttk") or {}
    collapse = float(context.get("collapse_max") or 480.0)
    trash_t = float(ttk.get("trash") or 1.0)
    elite_t = float(ttk.get("elite") or 6.0)
    tax = 4.0
    budget = collapse * 0.40
    trash = max(1, min(6, int(budget / max(trash_t * tax, 0.5))))
    elite = 1 if elite_t * tax < collapse * 0.50 else 0
    boss = 0
    dps = context.get("pack_dps")
    return Thought(
        slot="left", kind="analytic",
        text=f"HP = DPS × TTK ; oracle mix trash={trash} elite={elite} boss={boss}",
        confidence=0.91,
        tags=("analytic", "symbolic", "left", "mix", "oracle", "injected"),
        numbers=(float(dps or 0.0), float(trash), float(elite), float(boss)),
    )
