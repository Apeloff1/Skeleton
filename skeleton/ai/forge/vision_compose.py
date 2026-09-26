"""Vision → blueprint composition.

Closes the "archetype-name only" gap on the GameForge path: instead of
stamping a fixed preset, :func:`compose_from_vision` reads the creator's
vision and assembles a component graph from the Forge stdlib kinds, with a
provenance record explaining which words produced which systems.

Design constraints
------------------
* Deterministic: same vision → same graph, same wires, same order.
* Closed vocabulary: only registered stdlib kinds are instantiated; free
  text never names a kind, port or instance id directly.
* Type-safe: every wire is type- and direction-compatible, and the result
  passes :meth:`Blueprint.validate` before it is returned.
* Honest fallback: when the vision names no recognisable system, the
  composer says so (``fallback=True``) and seeds the canonical extraction
  loop rather than pretending the graph was derived.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from skeleton.forge.universal import Blueprint, Forge
from skeleton.kernel.errors import BlueprintError

VISION_MAX_CHARS = 4000
_WORD = re.compile(r"[a-z][a-z0-9']*")
# A trigger preceded by one of these (within two words) is negated:
# "a cozy farm with no combat" must not spawn enemies.
NEGATORS = frozenset({"no", "without", "never", "zero", "non", "nor", "not", "free"})
# Words that share a trigger prefix but mean something else.
FALSE_FRIENDS = ("forget", "forgot")
_CLAUSE = re.compile(r"[.,;:!?()\n]+")


@dataclass(frozen=True)
class Feature:
    """One composable gameplay system: trigger stems → component (+ wires)."""

    name: str
    stems: Tuple[str, ...]
    kind: str
    instance_id: str
    description: str


# Order is the canonical instantiation order (and therefore the tiebreak for
# the execution order the Forge derives). Stems match word prefixes.
FEATURES: Tuple[Feature, ...] = (
    Feature("combat", ("fight", "shoot", "gun", "combat", "enemy", "enemies", "horde", "boss",
                       "kill", "battle", "monster", "raid", "wave", "zombie", "duel"),
            "enemy_spawner", "spawner", "hostile pressure that scales with player intent"),
    Feature("crafting", ("craft", "forge", "weapon", "loot", "salvage", "scrap", "parts",
                         "gear", "upgrade", "smith"),
            "weapon_forge", "forge", "turns salvaged parts into new weapons"),
    Feature("heat", ("heat", "overheat", "stress", "pressure", "noise", "alert", "tension",
                     "wanted", "suspicion"),
            "heat", "heat", "escalation meter driven by player actions"),
    Feature("collapse", ("collapse", "timer", "countdown", "storm", "doom", "flood", "decay",
                         "clock", "deadline", "meltdown"),
            "collapse", "collapse", "run-ending fail clock"),
    Feature("extraction", ("extract", "escape", "evac", "exfil", "extraction", "survive",
                           "cores", "heist"),
            "extract", "extract", "win condition: get out with the haul"),
    Feature("companion", ("companion", "advisor", "butler", "jeeves", "guide", "mentor",
                          "sidekick", "narrator", "assistant"),
            "jeeves", "jeeves", "tactical companion reading player telemetry"),
    Feature("persistence", ("save", "inventory", "stash", "economy", "progress", "persistent",
                            "vault", "trade", "shop"),
            "state_store", "vault", "persistent player state and economy"),
    Feature("hud", ("hud", "score", "leaderboard", "ui", "minimap", "combo", "arcade",
                    "points"),
            "sink", "hud", "player-facing readout"),
)

_FEATURE_BY_NAME: Dict[str, Feature] = {f.name: f for f in FEATURES}
FALLBACK_FEATURES: Tuple[str, ...] = ("heat", "crafting", "combat", "collapse", "extraction", "companion")


@dataclass
class Composition:
    """Provenance for a composed blueprint."""

    vision: str
    features: List[str]
    matches: Dict[str, List[str]]
    fallback: bool
    components: List[Dict[str, str]] = field(default_factory=list)
    wires: List[Dict[str, List[str]]] = field(default_factory=list)
    blueprint_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vision_chars": len(self.vision),
            "features": list(self.features),
            "matches": {k: list(v) for k, v in self.matches.items()},
            "fallback": self.fallback,
            "components": [dict(c) for c in self.components],
            "wires": [{"from": list(w["from"]), "to": list(w["to"])} for w in self.wires],
            "blueprint_id": self.blueprint_id,
        }


def _clauses(vision: str) -> List[List[str]]:
    """Lower-cased word lists per clause; negation never crosses punctuation."""
    text = vision.lower()[:VISION_MAX_CHARS]
    return [words for words in (_WORD.findall(c) for c in _CLAUSE.split(text)) if words]


def _negated(words: Sequence[str], index: int) -> bool:
    window = words[max(0, index - 2):index]
    if any(w in NEGATORS for w in window):
        return True
    # "combat-free" tokenises to ["combat", "free"].
    return index + 1 < len(words) and words[index + 1] == "free"


def detect_features(vision: str) -> Tuple[List[str], Dict[str, List[str]]]:
    """Return ``(features_in_canonical_order, {feature: matched_words})``."""
    if not isinstance(vision, str):
        raise BlueprintError("vision must be a string")
    clauses = _clauses(vision)
    matches: Dict[str, List[str]] = {}
    for feature in FEATURES:
        hits: List[str] = []
        for words in clauses:
            for index, word in enumerate(words):
                if word in hits or any(word.startswith(ff) for ff in FALSE_FRIENDS):
                    continue
                if not any(word.startswith(stem) for stem in feature.stems):
                    continue
                if _negated(words, index):
                    continue
                hits.append(word)
        if hits:
            matches[feature.name] = hits[:8]
    ordered = [f.name for f in FEATURES if f.name in matches]
    return ordered, matches


def _plan_wires(present: Sequence[str]) -> List[Tuple[Tuple[str, str], Tuple[str, str]]]:
    """Type-correct wiring over the chosen components (player always present)."""
    has = set(present)
    wires: List[Tuple[Tuple[str, str], Tuple[str, str]]] = []
    if "combat" in has:
        wires.append((("operator", "intent"), ("spawner", "tick")))
    if "heat" in has:
        wires.append((("operator", "intent"), ("heat", "in")))
    if "collapse" in has:
        # The fail clock ticks on hostile spawns when combat exists, else on
        # raw player intent — both are event → event.
        src = ("spawner", "spawn") if "combat" in has else ("operator", "intent")
        wires.append((src, ("collapse", "tick")))
    if "companion" in has:
        wires.append((("operator", "state"), ("jeeves", "telemetry")))
    if "persistence" in has:
        wires.append((("operator", "state"), ("vault", "write")))
    if "hud" in has:
        src = ("forge", "weapon") if "crafting" in has else ("operator", "intent")
        wires.append((src, ("hud", "in")))
    return wires


def compose_from_vision(
    forge: Forge,
    vision: str,
    *,
    name: Optional[str] = None,
    fallback: Sequence[str] = FALLBACK_FEATURES,
) -> Tuple[Blueprint, Composition]:
    """Compose a validated blueprint from ``vision`` using stdlib kinds only."""
    if not isinstance(forge, Forge):
        raise BlueprintError("compose_from_vision needs a Forge")
    features, matches = detect_features(vision)
    used_fallback = not features
    if used_fallback:
        unknown = [f for f in fallback if f not in _FEATURE_BY_NAME]
        if unknown:
            raise BlueprintError("unknown fallback feature", context={"unknown": unknown})
        features = [f.name for f in FEATURES if f.name in set(fallback)]
    available = set(forge.available_kinds())
    missing = sorted({_FEATURE_BY_NAME[f].kind for f in features} - available | ({"player"} - available))
    if missing:
        raise BlueprintError("forge lacks required stdlib kinds", context={"missing": missing})

    bp_name = name or ("vision:" + "+".join(features))
    bp = forge.new_blueprint(bp_name[:120])
    components: List[Dict[str, str]] = [{"instance_id": "operator", "kind": "player", "feature": "player"}]
    forge.instantiate(bp, "player", "operator", config={"feature": "player"})
    for fname in features:
        feature = _FEATURE_BY_NAME[fname]
        forge.instantiate(bp, feature.kind, feature.instance_id, config={
            "feature": feature.name,
            "description": feature.description,
            "triggers": list(matches.get(feature.name, [])),
        })
        components.append({"instance_id": feature.instance_id, "kind": feature.kind, "feature": feature.name})
    wires = _plan_wires(features)
    for src, dst in wires:
        bp.connect(src, dst)
    problems = bp.validate()
    if problems:  # pragma: no cover - guarded by the wiring table tests
        raise BlueprintError("composed blueprint failed validation", context={"problems": problems})
    composition = Composition(
        vision=vision[:VISION_MAX_CHARS],
        features=list(features),
        matches=matches,
        fallback=used_fallback,
        components=components,
        wires=[{"from": list(s), "to": list(d)} for s, d in wires],
        blueprint_id=bp.blueprint_id,
    )
    return bp, composition


def describe(composition: Mapping[str, Any]) -> str:
    """One-line human summary for cockpit/log surfaces."""
    feats = composition.get("features") or []
    tag = " (fallback)" if composition.get("fallback") else ""
    return f"{len(feats)} systems{tag}: " + ", ".join(feats)


__all__ = [
    "FEATURES",
    "FALLBACK_FEATURES",
    "Composition",
    "Feature",
    "compose_from_vision",
    "describe",
    "detect_features",
]
