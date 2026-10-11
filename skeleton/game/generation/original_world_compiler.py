"""Deterministic, indexed assembly of original world-and-mechanic designs.

This is an additive generation-domain design compiler, not an engine runtime.
Every index maps to one unique authored-world + 12-mechanic recipe; runtime
adapters must separately implement rules before claiming playable support.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
import json
from math import comb

from .original_mechanic_catalog import MECHANICS, OriginalMechanic
from .original_world_catalog import WORLDS, OriginalWorld


class OriginalAtlasError(ValueError):
    """Invalid atlas recipe, catalog invariant or variation index."""


WORLD_IDS = tuple(sorted(WORLDS))
DOMAINS = tuple(sorted({world.domain for world in WORLDS.values()}))
MECHANICS_BY_DOMAIN = {
    domain: tuple(sorted((item for item in MECHANICS.values()
                          if item.domain == domain), key=lambda item: item.mechanic_id))
    for domain in DOMAINS
}

# Structural rule projections remain proposals until connected to an engine.
TOPOLOGIES = (
    "mutable-adjacency", "recursive-multiscale", "non-euclidean-rooms",
    "streamed-voxel-world", "distributed-settlements", "layered-realities",
    "causal-event-graph", "persistent-open-continent", "episodic-room-web",
    "topological-ocean", "orbiting-microhabitats", "shifting-maze",
)

# Every entry is a domain-pair interaction hypothesis with a distinct causal
# bridge, rather than a generic "+10% effect" or purely cosmetic mash-up.
_CROSS_DOMAIN_BRIDGES = {
    ("time", "topology"): "Delayed decisions make previously traversed edges reappear at a later date.",
    ("time", "ecology"): "Species inheritance takes place on locally different generational clocks.",
    ("time", "civilization"): "Public decisions mature into enforceable law at different future dates.",
    ("time", "economy"): "Outstanding debts can be repaid through scheduled future actions.",
    ("time", "identity"): "The same person's age and memory histories become separately negotiable.",
    ("time", "mortality"): "Legacy and resurrection obligations are tied to irreversible timeline receipts.",
    ("time", "performance"): "Rehearsals consume actual future stages, changing what audiences can experience.",
    ("topology", "ecology"): "Migrating animals physically reroute corridors that follow their habitats.",
    ("topology", "civilization"): "Settlements change connectivity when citizenship or political borders move.",
    ("topology", "identity"): "Access routes respond to the traveler's remembered or assumed identity.",
    ("topology", "infrastructure"): "Transit plans can freeze some routes while allowing other connections to drift.",
    ("topology", "language"): "Route availability is rewritten by agreement about words and meanings.",
    ("topology", "scale"): "Nested or folded spaces preserve entrance and exit lineage across magnifications.",
    ("topology", "voyage"): "Expedition charts must represent shifting edges instead of static positions.",
    ("topology", "performance"): "Performance formations temporarily bend walking and transit paths.",
    ("ecology", "civilization"): "Conservation obligations are part of civic representation and local voting.",
    ("ecology", "economy"): "Market value includes ecosystem recovery costs, not just extracted resources.",
    ("ecology", "belief"): "Ritual discontinuity has measured consequences on species dependencies.",
    ("ecology", "infrastructure"): "Cities must budget utilities against animal and nutrient migration flows.",
    ("ecology", "machines"): "Manufactured devices develop ecological niches and compete for material flows.",
    ("ecology", "mortality"): "Ancestral memorial obligations fund or destabilize living habitats.",
    ("civilization", "identity"): "Rights migrate with adopted names, roles, and lineage obligations.",
    ("civilization", "law"): "Border, census and citizen changes update jurisdiction without erasing disputes.",
    ("civilization", "language"): "Dialects alter representation rules without suppressing minority speakers.",
    ("civilization", "performance"): "Public art acts as a limited-duration constitutional amendment.",
    ("identity", "economy"): "A transfer of reputation is accounted separately from the transfer of property.",
    ("identity", "belief"): "Collective myths are constrained by the lived testimony of their subjects.",
    ("identity", "law"): "A role or mask may confer a power but also inherits its legal liabilities.",
    ("economy", "physics"): "Weight, energy or distance can be traded only with a conservation obligation.",
    ("economy", "machines"): "Factories negotiate component rights and the price of downtime.",
    ("economy", "infrastructure"): "Supply-network capacity responds to unpaid labor and commons depletion.",
    ("economy", "language"): "Prices reflect the informational harm caused by translation and secret barter.",
    ("physics", "machines"): "Mechanical devices act on changing physical laws with bounded failure modes.",
    ("physics", "belief"): "Observer expectations constrain ignition and other conditional processes.",
    ("physics", "scale"): "Conservation receipts follow resources through nested scales.",
    ("physics", "performance"): "Rhythmic patterns change momentum, friction and local gravity.",
    ("machines", "law"): "Machines have declared charters governing use, repair and refusal.",
    ("machines", "language"): "Specifications are executable only when compatible semantic contracts are met.",
    ("machines", "scale"): "Components can be manufactured and serviced at nested physical resolutions.",
    ("law", "belief"): "Public ritual claims remain subordinate to due process and individual consent.",
    ("law", "mortality"): "Resurrection and remembrance have distinct rights and consent requirements.",
    ("law", "voyage"): "Jurisdiction follows travelers and changes across nonstationary boundaries.",
    ("belief", "language"): "New names and interpretations change the reachable mythic infrastructure.",
    ("belief", "mortality"): "Legacy myths cannot summon the dead without bounded consequences.",
    ("belief", "performance"): "Performative ceremony changes reality only while credible community agreement lasts.",
    ("infrastructure", "voyage"): "Travelers must account for live water, road, bridge and schedule mutations.",
    ("infrastructure", "mortality"): "Invisible maintenance and inherited structures create long-lived obligations.",
    ("language", "performance"): "Staged speech can alter grammar-dependent weather and civic rights.",
    ("language", "scale"): "Nested languages preserve meaning at different spatial resolutions.",
    ("scale", "voyage"): "Navigational identity includes the scale level and its parent coordinate system.",
    ("mortality", "performance"): "Performances can preserve, revise or relinquish a person's remembered legacy.",
    ("voyage", "performance"): "Movement and performance combine into journeys with irreversible staging choices.",
}
# Dict keys above are symmetric; canonicalize at lookup time instead of
# relying on lexicographical authoring order.
_BRIDGES = {frozenset(key): value for key, value in _CROSS_DOMAIN_BRIDGES.items()}


def _verify_uniform_atlas() -> None:
    if len(DOMAINS) != 81 or len(WORLDS) != 1296 or len(MECHANICS) != 1944:
        raise OriginalAtlasError("atlas inventory changed: explicitly revise index schema")
    if any(len(MECHANICS_BY_DOMAIN[domain]) != 24 for domain in DOMAINS):
        raise OriginalAtlasError("domain mechanic cardinality changed: revision required")
    if sum(item.cost_specified for item in MECHANICS.values()) != 712:
        raise OriginalAtlasError("independently specified mechanics cardinality changed")
    if sum(not item.cost_specified for item in MECHANICS.values()) != 1232:
        raise OriginalAtlasError("derived world lever cardinality changed")
    if set(MECHANICS_BY_DOMAIN) != set(DOMAINS):
        raise OriginalAtlasError("world/mechanic domains diverged")
    if len(_BRIDGES) != len(_CROSS_DOMAIN_BRIDGES):
        raise OriginalAtlasError("duplicate domain bridge")
    if any(len(pair) != 2 or not pair.issubset(DOMAINS)
           for pair in _BRIDGES):
        raise OriginalAtlasError("unknown or self-referential bridge domain")


_verify_uniform_atlas()

PRIMARY_PICKS = 2
FOREIGN_DOMAINS = 10
MECHANICS_PER_WORLD = PRIMARY_PICKS + FOREIGN_DOMAINS
PRIMARY_CHOICES = comb(24, PRIMARY_PICKS)
FOREIGN_DOMAIN_CHOICES = comb(80, FOREIGN_DOMAINS)
FOREIGN_MECHANIC_CHOICES = 24 ** FOREIGN_DOMAINS
VARIANTS_PER_WORLD = PRIMARY_CHOICES * FOREIGN_DOMAIN_CHOICES * FOREIGN_MECHANIC_CHOICES
TOTAL_VARIANTS = len(WORLD_IDS) * VARIANTS_PER_WORLD
ATLAS_VERSION = "original-world-atlas.v2"


def _unrank(n: int, k: int, rank: int) -> tuple[int, ...]:
    """Unrank a lexicographically sorted k-subset without enumerating subsets."""
    if isinstance(rank, bool) or not isinstance(rank, int) or not 0 <= rank < comb(n, k):
        raise OriginalAtlasError("combination index out of range")
    out = []
    next_value = 0
    for slot in range(k):
        remaining = k - slot - 1
        for candidate in range(next_value, n):
            ways = comb(n - candidate - 1, remaining)
            if rank < ways:
                out.append(candidate)
                next_value = candidate + 1
                break
            rank -= ways
        else:
            raise OriginalAtlasError("combination unranking failed")
    return tuple(out)


@dataclass(frozen=True)
class RuleBridge:
    from_mechanic: str
    to_mechanic: str
    consequence: str
    origin: str = "inferred"


@dataclass(frozen=True)
class OriginalWorldBlueprint:
    atlas_version: str
    variant_index: int
    recipe_id: str
    world: OriginalWorld
    mechanics: tuple[OriginalMechanic, ...]
    domain_count: int
    topology: str
    ending_policy: str
    bridges: tuple[RuleBridge, ...]
    realization_status: str = "design-only"

    @property
    def specified_mechanic_count(self) -> int:
        return sum(item.cost_specified for item in self.mechanics)

    @property
    def unresolved_lever_count(self) -> int:
        return len(self.mechanics) - self.specified_mechanic_count

    @property
    def authored_bridge_count(self) -> int:
        return sum(bridge.origin == "authored" for bridge in self.bridges)

    def as_dict(self) -> dict:
        return {
            "atlas_version": self.atlas_version,
            "variant_index": self.variant_index,
            "recipe_id": self.recipe_id,
            "world": self.world.__dict__.copy(),
            "mechanics": [mechanic.__dict__.copy() for mechanic in self.mechanics],
            "domain_count": self.domain_count,
            "topology": self.topology,
            "ending_policy": self.ending_policy,
            "bridges": [bridge.__dict__.copy() for bridge in self.bridges],
            "realization_status": self.realization_status,
            "specified_mechanic_count": self.specified_mechanic_count,
            "unresolved_lever_count": self.unresolved_lever_count,
            "authored_bridge_count": self.authored_bridge_count,
        }


def _digest(value: dict) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()


def blueprint_at(index: int) -> OriginalWorldBlueprint:
    """Map an exact integer index to one of the complete atlas's recipes.

    Recipe uniqueness refers to world identifier + ordered mechanic *set*,
    not evidence that the generated worlds are independently playable or fun.
    """
    if isinstance(index, bool) or not isinstance(index, int):
        raise OriginalAtlasError("variation index must be integer (not bool)")
    if not 0 <= index < TOTAL_VARIANTS:
        raise OriginalAtlasError("variation index outside catalog capacity")

    world_position, local = divmod(index, VARIANTS_PER_WORLD)
    world = WORLDS[WORLD_IDS[world_position]]
    foreign_options = tuple(domain for domain in DOMAINS if domain != world.domain)

    secondary_per_primary = FOREIGN_DOMAIN_CHOICES * FOREIGN_MECHANIC_CHOICES
    primary_rank, local = divmod(local, secondary_per_primary)
    domain_rank, mechanic_rank = divmod(local, FOREIGN_MECHANIC_CHOICES)
    primary_indices = _unrank(24, PRIMARY_PICKS, primary_rank)
    secondary_indices = _unrank(80, FOREIGN_DOMAINS, domain_rank)

    chosen = [MECHANICS_BY_DOMAIN[world.domain][i] for i in primary_indices]
    for domain_index in secondary_indices:
        power = 24 ** (FOREIGN_DOMAINS - 1 - len(chosen) + PRIMARY_PICKS)
        digit, mechanic_rank = divmod(mechanic_rank, power)
        chosen.append(MECHANICS_BY_DOMAIN[foreign_options[domain_index]][digit])

    selected = tuple(sorted(chosen, key=lambda item: item.mechanic_id))
    if len(selected) != MECHANICS_PER_WORLD:
        raise OriginalAtlasError("mechanic selection cardinality mismatch")
    unique_domains = {item.domain for item in selected}
    if len(unique_domains) != FOREIGN_DOMAINS + 1:
        raise OriginalAtlasError("cross-domain diversity requirement failed")

    # Preserve 52 curated relationships. For previously unpaired domains,
    # use transparent mechanic-specific bridge hypotheses, NEVER claim the
    # inferred relationships have been manually authored or implemented.
    representative = {
        domain: next(item for item in selected if item.domain == domain)
        for domain in sorted(unique_domains)
    }
    bridges = []
    for first, second in combinations(sorted(unique_domains), 2):
        left, right = representative[first], representative[second]
        authored = _BRIDGES.get(frozenset((first, second)))
        consequence = authored or (
            f"Interaction hypothesis: after [{left.title}] causes "
            f"[{left.state_change}], evaluate whether [{right.title}] "
            f"can trigger [{right.trigger}]; preserve both stated costs."
        )
        bridges.append(RuleBridge(
            left.mechanic_id, right.mechanic_id, consequence,
            "authored" if authored else "inferred",
        ))
    bridges = tuple(bridges)
    signature = {
        "atlas_version": ATLAS_VERSION,
        "world_id": world.world_id,
        "mechanic_ids": [item.mechanic_id for item in selected],
    }
    return OriginalWorldBlueprint(
        atlas_version=ATLAS_VERSION,
        variant_index=index,
        recipe_id=_digest(signature),
        world=world,
        mechanics=selected,
        domain_count=len(unique_domains),
        topology=TOPOLOGIES[index % len(TOPOLOGIES)],
        ending_policy=world.ending_policy,
        bridges=bridges,
    )


def blueprint_for_world(world_id: str, variant_index: int) -> OriginalWorldBlueprint:
    """Select a zero-based design variation within one authored world."""
    try:
        world_position = WORLD_IDS.index(world_id)
    except (ValueError, TypeError) as exc:
        raise OriginalAtlasError("unknown original world") from exc
    if isinstance(variant_index, bool) or not isinstance(variant_index, int):
        raise OriginalAtlasError("variation index must be integer (not bool)")
    if not 0 <= variant_index < VARIANTS_PER_WORLD:
        raise OriginalAtlasError("world-local variation index out of range")
    return blueprint_at(world_position * VARIANTS_PER_WORLD + variant_index)


def blueprint_from_seed(seed: str) -> OriginalWorldBlueprint:
    """Reproducible sample; exact variant addressing uses blueprint_at()."""
    if not isinstance(seed, str) or not 0 < len(seed.encode("utf-8")) <= 4096:
        raise OriginalAtlasError("seed must be 1-4096 UTF-8 bytes")
    seed_hash = sha256((ATLAS_VERSION + ":" + seed).encode("utf-8")).digest()
    return blueprint_at(int.from_bytes(seed_hash, "big") % TOTAL_VARIANTS)
