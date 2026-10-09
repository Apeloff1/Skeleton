"""Sixteen cortex organs. Cards only. Operator aggregator is not overwritten."""

from __future__ import annotations

from typing import Callable, Mapping

from ai_tree_fill.laws import ClippedG, digest_card, era_bind, mass_admit, parse_pointers
from ai_tree_fill.numerics import rmsnorm, silu, softmax

HOUSE_ERA = {
    "skeleton": "HOUSE_ERA_V16",
    "jeeves": "HOUSE_ERA_CORTEX",
    "gameforge": "HOUSE_ERA_FORGE",
    "tutolage": "HOUSE_ERA_SCHOOL",
}

ORGAN_NAMES = (
    "speak",
    "refer",
    "improve",
    "ascend",
    "plan",
    "walk",
    "pick",
    "genos",
    "cut",
    "contact",
    "gossip",
    "observe_run",
    "forge",
    "attach_lora",
    "beam",
    "accumulate",
)


def _base(organ: str, stimulus: str) -> dict:
    pointers = parse_pointers(stimulus)
    return {
        "organ": organ,
        "hit": 1,
        "law": organ,
        "pointers": pointers,
        "n_cap": 8,
    }


def speak(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("speak", stimulus)
    card["voice"] = "own-lm"
    card["device"] = "cpu"
    card["text"] = "ptr:" + ",".join(card["pointers"])
    return card


def refer(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("refer", stimulus)
    card["era"] = era_bind(str(state.get("title", "skeleton")), HOUSE_ERA)
    card["citation"] = card["pointers"][0]
    return card


def improve(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("improve", stimulus)
    card["axes"] = {"fun": 0.62, "clarity": 0.71, "feasibility": 0.8, "originality": 0.66}
    card["weakest"] = "fun"
    return card


def ascend(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("ascend", stimulus)
    card["rung"] = int(state.get("rung", 0)) + 1
    return card


def plan(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("plan", stimulus)
    card["steps"] = ["vision", "snowball", "prototype", "mass", "world", "cockpit", "export"]
    card["era"] = era_bind(str(state.get("title", "gameforge")), HOUSE_ERA)
    return card


def walk(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("walk", stimulus)
    card["field"] = "house-pointer"
    card["prose_stored"] = False
    return card


def pick(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("pick", stimulus)
    weights = softmax([0.2, 0.5, 0.3])
    card["choice"] = int(max(range(len(weights)), key=lambda i: weights[i]))
    card["weights"] = weights
    return card


def genos(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("genos", stimulus)
    card["helix"] = [{"a": card["pointers"][0], "b": "pair"}]
    return card


def cut(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("cut", stimulus)
    card["era"] = era_bind(str(state.get("title", "skeleton")), HOUSE_ERA)
    card["cut_sets_era"] = True
    return card


def contact(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("contact", stimulus)
    card["lora"] = {"rank": 2, "alpha": 4.0, "absorb_steps": 4, "house": "dialect"}
    card["teacher"] = "copy"
    return card


def gossip(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("gossip", stimulus)
    card["root"] = digest_card({"p": card["pointers"]})
    card["chain"] = False
    return card


def observe_run(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("observe_run", stimulus)
    g = state.get("g")
    if not isinstance(g, ClippedG):
        g = ClippedG(1.0, 1.0, 0.0, 0.0, [1.0]).step(0.4, 0.5)
    card.update(g.card())
    card["mass_hint"] = mass_admit(float(state.get("mass", 1.0)), float(state.get("mass", 1.0)) * 1.05)
    return card


def forge(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("forge", stimulus)
    prior = float(state.get("mass", 1.0))
    card["mass"] = mass_admit(prior, prior * 1.05)
    card["emit"] = "pack"
    return card


def attach_lora(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("attach_lora", stimulus)
    card["bound"] = True
    card["rank"] = 2
    return card


def beam(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("beam", stimulus)
    width = int(state.get("beam", 3))
    card["width"] = width
    card["paths"] = [f"p{i}" for i in range(width)]
    return card


def accumulate(stimulus: str, state: Mapping[str, object]) -> dict:
    card = _base("accumulate", stimulus)
    vec = rmsnorm([0.2, -0.4, 0.8, 0.1])
    card["residual"] = silu(vec)
    return card


ORGANS: dict[str, Callable[[str, Mapping[str, object]], dict]] = {
    "speak": speak,
    "refer": refer,
    "improve": improve,
    "ascend": ascend,
    "plan": plan,
    "walk": walk,
    "pick": pick,
    "genos": genos,
    "cut": cut,
    "contact": contact,
    "gossip": gossip,
    "observe_run": observe_run,
    "forge": forge,
    "attach_lora": attach_lora,
    "beam": beam,
    "accumulate": accumulate,
}


def dispatch(organ: str, stimulus: str, state: Mapping[str, object] | None = None) -> dict:
    if organ not in ORGANS:
        return {"organ": organ, "hit": 0, "law": "unknown-organ"}
    return ORGANS[organ](stimulus, state or {"title": "skeleton", "mass": 1.0})
