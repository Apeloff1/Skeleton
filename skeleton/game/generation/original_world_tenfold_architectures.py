"""Ten authored *spatial simulation systems*, distinct from cosmetic world skins.

Every architecture specifies a traversable graph rule, physical resource
hazards and one architecture-only intervention. The ten contracts intentionally
span bounded examples of 2-D, vertical, discontinuous and dynamic space.
They DO NOT constitute native renderers, limitless voxels or finished games.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorldArchitecture:
    architecture_id: str
    title: str
    spatial_contract: str
    transit_constraint: str
    hazard_model: str
    intervention: str
    progression_effect: str


ARCHITECTURES = (
    WorldArchitecture(
        "lattice", "The Civic Grid",
        "Six columns by four streets with neighboring walkable intersections",
        "Road travel costs stamina; maintained junctions lower crossing exposure",
        "Public bridges deteriorate under repeated risky traversal",
        "pave", "New infrastructure converts scarce stone into lasting road security",
    ),
    WorldArchitecture(
        "spiral", "The Turnback Spiral",
        "One winding twenty-four-room path with deliberate distant shortcuts",
        "Movement follows the next spiral chamber or an opened reversible hinge",
        "Lost navigation increases expedition cost when shortcuts change",
        "splice", "A material-backed hinge connects nonadjacent spiral bends",
    ),
    WorldArchitecture(
        "labyrinth", "The Witnessing Maze",
        "A seeded, connected spanning-tree labyrinth whose optional passages shift",
        "Main tree edges stay reachable while rotating secret edges change by phase",
        "Confusing rotations raise disorientation unless evidence is gathered",
        "anchor", "Investigation stabilizes a temporary rotating shortcut",
    ),
    WorldArchitecture(
        "archipelago", "Isles of the Finite Ferries",
        "Four six-room islands linked only at ferry piers",
        "Island crossings spend stored fuel and demand an active ferry service",
        "Storm cycles can disrupt ferry departures until safety is reinforced",
        "ferry", "Repair and fund a durable, limited-capacity ferry connection",
    ),
    WorldArchitecture(
        "strata", "The Descending Archive",
        "Four deep geology levels with six lateral rooms and narrow vertical shafts",
        "Vertical shafts cost extra climbing energy and require safety support",
        "Depth increases air and rockfall pressure unless braced",
        "brace", "Material-backed shoring protects dangerous deep passage",
    ),
    WorldArchitecture(
        "canopy", "Suspended Roots Above the Clouds",
        "Four elevated forest strata linked by ladders and conditional wind bridges",
        "Changing wind can close exposed diagonals without severing safe ladders",
        "Unprotected wind transit accumulates fall injury",
        "tether", "Installed climbing line reduces wind-crossing risk",
    ),
    WorldArchitecture(
        "orbit", "The Clockwork Constellation",
        "Six orbital rings with four docking stations and narrow transfer windows",
        "Orbital swaps need stored reaction fuel and correctly phased docking",
        "Bad launch timing wastes energy and exposes craft to radiation",
        "align", "Spend evidence and propellant to extend safe transfer windows",
    ),
    WorldArchitecture(
        "pocket", "Rooms Inside the Unfinished Map",
        "Twelve outer rooms and twelve inward pocket realities with guarded portals",
        "Entering a pocket needs a calibrated portal rather than a physical corridor",
        "Uncalibrated exits consume additional oxygen and lose provenance",
        "attune", "Verify portal endpoints and pay the stabilization resources",
    ),
    WorldArchitecture(
        "phase", "The Reconfiguring City",
        "A permanent safety circuit plus instantaneous rotating phase corridors",
        "Extra phase corridors shift each dawn but the safety circuit persists",
        "Crossing unstable corridors can raise paradox debt",
        "stabilize", "Bind one selected crossing across subsequent phase changes",
    ),
    WorldArchitecture(
        "abyss", "The Living Seafloor",
        "Connected ocean-floor chambers with pressure gradients and tidal tunnels",
        "Deep corridors consume oxygen and flooded shortcuts obey periodic tides",
        "Pressure, oxygen debt and current-driven hazards constrain exploration",
        "seal", "Create a resource-backed airlock that reduces deep diving risk",
    ),
)

ARCHITECTURE_BY_ID = {a.architecture_id: a for a in ARCHITECTURES}
if len(ARCHITECTURES) != 10 or len(ARCHITECTURE_BY_ID) != 10:
    raise RuntimeError("ten unique world-architecture rules are required")
if any(not all((
    a.spatial_contract, a.transit_constraint, a.hazard_model,
    a.intervention, a.progression_effect,
)) for a in ARCHITECTURES):
    raise RuntimeError("world architecture is missing actual control semantics")
