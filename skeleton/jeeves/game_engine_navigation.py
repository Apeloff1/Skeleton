"""Deterministic historical navigation runtime for Jeeves game engines.

GameForge contains agentic navigation/authoring surfaces, but those are not an
authoritative game-runtime pathfinder. This module is the bounded historical
runtime used inside era sandboxes.

The capability ladder progresses from direct goal links through tile BFS,
weighted A*, waypoint/navigation graphs, navmesh-style graphs, dynamic
obstacles/costs, hierarchical streamed regions and deterministic crowd
steering. Algorithms use stable integer costs and explicit tie-breakers; no
host clock, randomness, threads, platform navigation API or learned component
participates in authoritative results.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import math
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from .game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from .game_engine_runtime import (
    RoutedEngineSandbox,
)

NAVIGATION_SCHEMA_VERSION = 1
MAX_NAV_QUERY_BLOCKED = 4096
MAX_NAV_QUERY_PENALTIES = 4096
MAX_STEERING_NEIGHBORS = 256


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _finite(
    value: float,
    label: str,
) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise GameEngineLabError(
            f"{label} must be finite"
        )
    return result


def _token(
    value: str,
    label: str,
) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 64
        or not all(
            char.isalnum()
            or char in "_.-"
            for char in value
        )
    ):
        raise GameEngineLabError(
            f"{label} must be a bounded token"
        )
    return value


class NavigationMode(str, Enum):
    DIRECT = "direct"
    GRID_BFS = "grid_bfs"
    GRID_ASTAR = "grid_astar"
    WAYPOINT_ASTAR = "waypoint_astar"
    GRAPH_ASTAR = "graph_astar"
    NAVMESH_ASTAR = "navmesh_astar"
    NAVMESH_DYNAMIC = "navmesh_dynamic"
    HIERARCHICAL = "hierarchical"
    CROWD_HIERARCHICAL = "crowd_hierarchical"
    MULTI_LAYER = "multi_layer"


class NavigationHeuristic(str, Enum):
    NONE = "none"
    MANHATTAN = "manhattan"
    EUCLIDEAN = "euclidean"


@dataclass(frozen=True, slots=True)
class EraNavigationPolicy:
    era: EngineEra
    mode: NavigationMode
    dimensions: int
    max_nodes: int
    max_edges: int
    heuristic: NavigationHeuristic
    heuristic_scale: int
    dynamic_obstacles: bool
    dynamic_costs: bool
    hierarchical: bool
    smoothing: bool
    crowd_steering: bool
    max_regions: int
    max_path_nodes: int

    def __post_init__(self) -> None:
        if self.dimensions not in {
            2,
            3,
        }:
            raise GameEngineLabError(
                "navigation dimensions must be 2 or 3"
            )
        for value in (
            self.max_nodes,
            self.max_edges,
            self.max_regions,
            self.max_path_nodes,
        ):
            if (
                type(value) is not int
                or value < 1
            ):
                raise GameEngineLabError(
                    "navigation policy bounds must be positive integers"
                )
        if (
            type(self.heuristic_scale)
            is not int
            or self.heuristic_scale < 0
        ):
            raise GameEngineLabError(
                "navigation heuristic scale must be non-negative"
            )
        if (
            self.heuristic
            is NavigationHeuristic.NONE
            and self.heuristic_scale != 0
        ):
            raise GameEngineLabError(
                "navigation NONE heuristic must use zero scale"
            )
        if (
            self.heuristic
            is not NavigationHeuristic.NONE
            and self.heuristic_scale <= 0
        ):
            raise GameEngineLabError(
                "navigation heuristic requires positive scale"
            )
        if (
            self.crowd_steering
            and not self.dynamic_obstacles
        ):
            raise GameEngineLabError(
                "crowd steering requires dynamic obstacle capability"
            )


def _policy(
    era: EngineEra,
    mode: NavigationMode,
    dimensions: int,
    nodes: int,
    edges: int,
    heuristic: NavigationHeuristic,
    scale: int,
    *,
    dynamic_obstacles: bool,
    dynamic_costs: bool,
    hierarchical: bool,
    smoothing: bool,
    crowd: bool,
    regions: int,
    path_nodes: int,
) -> EraNavigationPolicy:
    return EraNavigationPolicy(
        era,
        mode,
        dimensions,
        nodes,
        edges,
        heuristic,
        scale,
        dynamic_obstacles,
        dynamic_costs,
        hierarchical,
        smoothing,
        crowd,
        regions,
        path_nodes,
    )


NAVIGATION_POLICIES: Mapping[
    EngineEra,
    EraNavigationPolicy,
] = {
    EngineEra.PONG: _policy(
        EngineEra.PONG,
        NavigationMode.DIRECT,
        2,
        4,
        4,
        NavigationHeuristic.NONE,
        0,
        dynamic_obstacles=False,
        dynamic_costs=False,
        hierarchical=False,
        smoothing=False,
        crowd=False,
        regions=1,
        path_nodes=4,
    ),
    EngineEra.ARCADE: _policy(
        EngineEra.ARCADE,
        NavigationMode.DIRECT,
        2,
        16,
        32,
        NavigationHeuristic.NONE,
        0,
        dynamic_obstacles=False,
        dynamic_costs=False,
        hierarchical=False,
        smoothing=False,
        crowd=False,
        regions=1,
        path_nodes=8,
    ),
    EngineEra.EIGHT_BIT: _policy(
        EngineEra.EIGHT_BIT,
        NavigationMode.GRID_BFS,
        2,
        256,
        1024,
        NavigationHeuristic.NONE,
        0,
        dynamic_obstacles=False,
        dynamic_costs=False,
        hierarchical=False,
        smoothing=False,
        crowd=False,
        regions=4,
        path_nodes=128,
    ),
    EngineEra.SIXTEEN_BIT: _policy(
        EngineEra.SIXTEEN_BIT,
        NavigationMode.GRID_ASTAR,
        2,
        1024,
        4096,
        NavigationHeuristic.MANHATTAN,
        10,
        dynamic_obstacles=False,
        dynamic_costs=True,
        hierarchical=False,
        smoothing=False,
        crowd=False,
        regions=8,
        path_nodes=256,
    ),
    EngineEra.EARLY_3D: _policy(
        EngineEra.EARLY_3D,
        NavigationMode.WAYPOINT_ASTAR,
        3,
        4096,
        16_384,
        NavigationHeuristic.EUCLIDEAN,
        10,
        dynamic_obstacles=False,
        dynamic_costs=True,
        hierarchical=False,
        smoothing=False,
        crowd=False,
        regions=16,
        path_nodes=512,
    ),
    EngineEra.FIXED_3D: _policy(
        EngineEra.FIXED_3D,
        NavigationMode.GRAPH_ASTAR,
        3,
        16_384,
        65_536,
        NavigationHeuristic.EUCLIDEAN,
        10,
        dynamic_obstacles=True,
        dynamic_costs=True,
        hierarchical=False,
        smoothing=False,
        crowd=False,
        regions=32,
        path_nodes=1024,
    ),
    EngineEra.SHADER: _policy(
        EngineEra.SHADER,
        NavigationMode.NAVMESH_ASTAR,
        3,
        65_536,
        262_144,
        NavigationHeuristic.EUCLIDEAN,
        10,
        dynamic_obstacles=True,
        dynamic_costs=True,
        hierarchical=False,
        smoothing=True,
        crowd=False,
        regions=64,
        path_nodes=2048,
    ),
    EngineEra.HD: _policy(
        EngineEra.HD,
        NavigationMode.NAVMESH_DYNAMIC,
        3,
        262_144,
        1_048_576,
        NavigationHeuristic.EUCLIDEAN,
        10,
        dynamic_obstacles=True,
        dynamic_costs=True,
        hierarchical=False,
        smoothing=True,
        crowd=False,
        regions=128,
        path_nodes=4096,
    ),
    EngineEra.OPEN_WORLD: _policy(
        EngineEra.OPEN_WORLD,
        NavigationMode.HIERARCHICAL,
        3,
        1_000_000,
        4_000_000,
        NavigationHeuristic.EUCLIDEAN,
        10,
        dynamic_obstacles=True,
        dynamic_costs=True,
        hierarchical=True,
        smoothing=True,
        crowd=False,
        regions=4096,
        path_nodes=8192,
    ),
    EngineEra.MODERN: _policy(
        EngineEra.MODERN,
        NavigationMode.CROWD_HIERARCHICAL,
        3,
        4_000_000,
        16_000_000,
        NavigationHeuristic.EUCLIDEAN,
        10,
        dynamic_obstacles=True,
        dynamic_costs=True,
        hierarchical=True,
        smoothing=True,
        crowd=True,
        regions=16_384,
        path_nodes=16_384,
    ),
    EngineEra.NEXT: _policy(
        EngineEra.NEXT,
        NavigationMode.MULTI_LAYER,
        3,
        8_000_000,
        32_000_000,
        NavigationHeuristic.EUCLIDEAN,
        10,
        dynamic_obstacles=True,
        dynamic_costs=True,
        hierarchical=True,
        smoothing=True,
        crowd=True,
        regions=65_536,
        path_nodes=32_768,
    ),
}


def navigation_policy(
    era: EngineEra | str,
) -> EraNavigationPolicy:
    try:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
    except ValueError as exc:
        raise GameEngineLabError(
            f"unknown engine era: {era!r}"
        ) from exc
    return NAVIGATION_POLICIES[key]


@dataclass(frozen=True, slots=True)
class NavNode:
    node_id: str
    x: int
    y: int
    z: int = 0
    region: str = "root"

    def __post_init__(self) -> None:
        _token(
            self.node_id,
            "navigation node id",
        )
        _token(
            self.region,
            "navigation region",
        )
        for value in (
            self.x,
            self.y,
            self.z,
        ):
            if (
                type(value) is not int
                or not -1_000_000
                <= value
                <= 1_000_000
            ):
                raise GameEngineLabError(
                    "navigation coordinate outside bounded integer range"
                )


@dataclass(frozen=True, slots=True)
class NavEdge:
    source: str
    target: str
    cost: int
    bidirectional: bool = True

    def __post_init__(self) -> None:
        _token(
            self.source,
            "navigation edge source",
        )
        _token(
            self.target,
            "navigation edge target",
        )
        if self.source == self.target:
            raise GameEngineLabError(
                "navigation self edges are unavailable"
            )
        if (
            type(self.cost) is not int
            or not 1
            <= self.cost
            <= 1_000_000_000
        ):
            raise GameEngineLabError(
                "navigation edge cost outside bounds"
            )
        if type(self.bidirectional) is not bool:
            raise GameEngineLabError(
                "navigation bidirectional flag must be boolean"
            )


@dataclass(frozen=True, slots=True)
class NavigationSource:
    nodes: tuple[NavNode, ...]
    edges: tuple[NavEdge, ...]

    def __post_init__(self) -> None:
        if not self.nodes:
            raise GameEngineLabError(
                "navigation source requires nodes"
            )


@dataclass(frozen=True, slots=True)
class NavigationQuery:
    start: str
    goal: str
    blocked: tuple[str, ...] = ()
    penalties: tuple[
        tuple[str, int],
        ...,
    ] = ()

    def __post_init__(self) -> None:
        _token(
            self.start,
            "navigation query start",
        )
        _token(
            self.goal,
            "navigation query goal",
        )
        if (
            len(self.blocked)
            > MAX_NAV_QUERY_BLOCKED
            or len(self.penalties)
            > MAX_NAV_QUERY_PENALTIES
        ):
            raise GameEngineLabError(
                "navigation query override budget exceeded"
            )
        if len(
            self.blocked
        ) != len(
            set(
                self.blocked
            )
        ):
            raise GameEngineLabError(
                "navigation query blocked nodes must be unique"
            )
        for node_id in self.blocked:
            _token(
                node_id,
                "navigation blocked node",
            )
        penalty_nodes = set()
        for node_id, cost in self.penalties:
            _token(
                node_id,
                "navigation penalty node",
            )
            if node_id in penalty_nodes:
                raise GameEngineLabError(
                    "navigation penalties must have unique nodes"
                )
            penalty_nodes.add(
                node_id
            )
            if (
                type(cost) is not int
                or not 0
                <= cost
                <= 1_000_000_000
            ):
                raise GameEngineLabError(
                    "navigation penalty outside bounds"
                )


@dataclass(frozen=True, slots=True)
class PathResult:
    era: EngineEra
    mode: NavigationMode
    start: str
    goal: str
    path: tuple[str, ...]
    total_cost: int | None
    expanded_nodes: int
    smoothed: bool
    region_route: tuple[str, ...]
    digest: str

    @property
    def found(self) -> bool:
        return bool(
            self.path
        )


@dataclass(frozen=True, slots=True)
class NavigationSnapshot:
    era: EngineEra
    blocked: tuple[str, ...]
    penalties: tuple[
        tuple[str, int],
        ...,
    ]
    digest: str


@dataclass(frozen=True, slots=True)
class SteeringNeighbor:
    agent_id: str
    x: float
    z: float

    def __post_init__(self) -> None:
        _token(
            self.agent_id,
            "steering agent id",
        )
        _finite(
            self.x,
            "steering neighbor x",
        )
        _finite(
            self.z,
            "steering neighbor z",
        )


@dataclass(frozen=True, slots=True)
class SteeringResult:
    era: EngineEra
    velocity_x: float
    velocity_z: float
    considered: tuple[str, ...]
    digest: str


def _distance_floor(
    left: NavNode,
    right: NavNode,
) -> int:
    dx = (
        left.x
        - right.x
    )
    dy = (
        left.y
        - right.y
    )
    dz = (
        left.z
        - right.z
    )
    return math.isqrt(
        dx * dx
        + dy * dy
        + dz * dz
    )


def validate_navigation_source(
    era: EngineEra | str,
    source: NavigationSource,
) -> None:
    policy = navigation_policy(
        era
    )
    if (
        len(source.nodes)
        > policy.max_nodes
        or len(source.edges)
        > policy.max_edges
    ):
        raise GameEngineLabError(
            "navigation source exceeds era graph budget"
        )
    node_ids = tuple(
        node.node_id
        for node in source.nodes
    )
    if len(node_ids) != len(
        set(node_ids)
    ):
        raise GameEngineLabError(
            "navigation node ids must be unique"
        )
    nodes = {
        node.node_id:
            node
        for node in source.nodes
    }
    regions = {
        node.region
        for node in source.nodes
    }
    if (
        len(regions)
        > policy.max_regions
    ):
        raise GameEngineLabError(
            "navigation region budget exceeded"
        )
    if (
        policy.dimensions == 2
        and any(
            node.z != 0
            for node in source.nodes
        )
    ):
        raise GameEngineLabError(
            "2D navigation era cannot contain nonzero z coordinates"
        )
    identities = set()
    costs = set()
    for edge in source.edges:
        if (
            edge.source not in nodes
            or edge.target not in nodes
        ):
            raise GameEngineLabError(
                "navigation edge references missing node"
            )
        identity = (
            edge.source,
            edge.target,
        )
        reverse = (
            edge.target,
            edge.source,
        )
        if (
            identity in identities
            or (
                edge.bidirectional
                and reverse
                in identities
            )
        ):
            raise GameEngineLabError(
                "navigation edges must be unique"
            )
        identities.add(
            identity
        )
        left = nodes[
            edge.source
        ]
        right = nodes[
            edge.target
        ]
        if (
            policy.heuristic
            is NavigationHeuristic.MANHATTAN
        ):
            geometric = (
                abs(
                    left.x
                    - right.x
                )
                + abs(
                    left.y
                    - right.y
                )
                + abs(
                    left.z
                    - right.z
                )
            )
        elif (
            policy.heuristic
            is NavigationHeuristic.EUCLIDEAN
        ):
            geometric = (
                _distance_floor(
                    left,
                    right,
                )
            )
        else:
            geometric = 0
        if (
            geometric
            * policy.heuristic_scale
            > edge.cost
        ):
            raise GameEngineLabError(
                "navigation edge cost violates admissible heuristic contract"
            )
        costs.add(
            edge.cost
        )
    if (
        policy.mode
        is NavigationMode.GRID_BFS
        and len(costs) > 1
    ):
        raise GameEngineLabError(
            "grid BFS era requires uniform edge costs"
        )


def _source_document(
    source: NavigationSource,
) -> dict[str, object]:
    return {
        "nodes": [
            {
                "node_id":
                    node.node_id,
                "x": node.x,
                "y": node.y,
                "z": node.z,
                "region":
                    node.region,
            }
            for node
            in sorted(
                source.nodes,
                key=lambda value:
                    value.node_id,
            )
        ],
        "edges": [
            {
                "source":
                    edge.source,
                "target":
                    edge.target,
                "cost":
                    edge.cost,
                "bidirectional":
                    edge.bidirectional,
            }
            for edge
            in sorted(
                source.edges,
                key=lambda value: (
                    value.source,
                    value.target,
                    value.cost,
                    value.bidirectional,
                ),
            )
        ],
    }


def navigation_policy_document(
    era: EngineEra | str,
) -> dict[str, object]:
    policy = navigation_policy(
        era
    )
    return {
        "schema_version":
            NAVIGATION_SCHEMA_VERSION,
        "engine_era":
            policy.era.value,
        "mode":
            policy.mode.value,
        "dimensions":
            policy.dimensions,
        "max_nodes":
            policy.max_nodes,
        "max_edges":
            policy.max_edges,
        "heuristic":
            policy.heuristic.value,
        "heuristic_scale":
            policy.heuristic_scale,
        "dynamic_obstacles":
            policy.dynamic_obstacles,
        "dynamic_costs":
            policy.dynamic_costs,
        "hierarchical":
            policy.hierarchical,
        "smoothing":
            policy.smoothing,
        "crowd_steering":
            policy.crowd_steering,
        "max_regions":
            policy.max_regions,
        "max_path_nodes":
            policy.max_path_nodes,
        "host_navigation_api":
            False,
    }


@dataclass(frozen=True, slots=True)
class NavigationBuild:
    era: EngineEra
    source_digest: str
    policy_digest: str
    manifest_digest: str
    source_document: dict[
        str,
        object,
    ]

    def manifest(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version":
                NAVIGATION_SCHEMA_VERSION,
            "engine_era":
                self.era.value,
            "source_digest":
                self.source_digest,
            "policy_digest":
                self.policy_digest,
            "manifest_digest":
                self.manifest_digest,
            "host_navigation_api":
                False,
        }


def compile_navigation_build(
    era: EngineEra | str,
    source: NavigationSource,
) -> NavigationBuild:
    policy = navigation_policy(
        era
    )
    validate_navigation_source(
        policy.era,
        source,
    )
    source_doc = (
        _source_document(
            source
        )
    )
    policy_doc = (
        navigation_policy_document(
            policy.era
        )
    )
    source_digest = (
        _digest(
            source_doc
        )
    )
    policy_digest = (
        _digest(
            policy_doc
        )
    )
    identity = {
        "schema_version":
            NAVIGATION_SCHEMA_VERSION,
        "engine_era":
            policy.era.value,
        "source_digest":
            source_digest,
        "policy_digest":
            policy_digest,
    }
    return NavigationBuild(
        policy.era,
        source_digest,
        policy_digest,
        _digest(
            identity
        ),
        source_doc,
    )


def navigation_build_patches(
    build: NavigationBuild,
) -> tuple[
    SandboxPatch,
    ...,
]:
    return (
        SandboxPatch(
            "navigation/compiled/manifest.json",
            json.dumps(
                build.manifest(),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
        SandboxPatch(
            "navigation/compiled/policy.json",
            json.dumps(
                navigation_policy_document(
                    build.era
                ),
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
        SandboxPatch(
            "navigation/compiled/graph.json",
            json.dumps(
                build.source_document,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        ),
    )


def attach_navigation_build(
    sandbox: RoutedEngineSandbox,
    source: NavigationSource,
) -> RoutedEngineSandbox:
    build = compile_navigation_build(
        sandbox.era,
        source,
    )
    return sandbox.apply(
        tuple(
            SandboxPatch(
                patch.path,
                patch.content,
                sandbox.tree.file_digest(
                    patch.path
                ),
            )
            for patch
            in navigation_build_patches(
                build
            )
        )
    )


def canonical_navigation_patches(
    sandbox: RoutedEngineSandbox,
    source: NavigationSource,
) -> tuple[
    SandboxPatch,
    ...,
]:
    build = compile_navigation_build(
        sandbox.era,
        source,
    )
    expected = {
        patch.path:
            patch.content
        for patch
        in navigation_build_patches(
            build
        )
    }
    existing = {
        path
        for path
        in sandbox.tree.files
        if path.startswith(
            "navigation/compiled/"
        )
    }
    patches = []
    for path in sorted(
        set(expected)
        | existing
    ):
        wanted = expected.get(
            path
        )
        try:
            current = (
                sandbox.tree.read(
                    path
                )
            )
        except GameEngineLabError:
            current = None
        if current == wanted:
            continue
        patches.append(
            SandboxPatch(
                path,
                wanted,
                sandbox.tree.file_digest(
                    path
                ),
            )
        )
    return tuple(
        patches
    )


class NavigationRuntime:
    """Stable integer-cost pathfinding and optional crowd steering."""

    def __init__(
        self,
        era: EngineEra | str,
        source: NavigationSource,
    ) -> None:
        self.policy = navigation_policy(
            era
        )
        validate_navigation_source(
            self.policy.era,
            source,
        )
        self.source = source
        self.nodes = {
            node.node_id:
                node
            for node in source.nodes
        }
        adjacency: dict[
            str,
            list[
                tuple[str, int]
            ],
        ] = {
            node_id: []
            for node_id
            in self.nodes
        }
        for edge in source.edges:
            adjacency[
                edge.source
            ].append(
                (
                    edge.target,
                    edge.cost,
                )
            )
            if edge.bidirectional:
                adjacency[
                    edge.target
                ].append(
                    (
                        edge.source,
                        edge.cost,
                    )
                )
        self.adjacency = {
            node_id: tuple(
                sorted(
                    values,
                    key=lambda row: (
                        row[0],
                        row[1],
                    ),
                )
            )
            for node_id, values
            in adjacency.items()
        }
        self._blocked: set[
            str
        ] = set()
        self._penalties: dict[
            str,
            int,
        ] = {}

    @property
    def era(self) -> EngineEra:
        return self.policy.era

    def _heuristic(
        self,
        node_id: str,
        goal_id: str,
    ) -> int:
        if (
            self.policy.heuristic
            is NavigationHeuristic.NONE
        ):
            return 0
        node = self.nodes[
            node_id
        ]
        goal = self.nodes[
            goal_id
        ]
        if (
            self.policy.heuristic
            is NavigationHeuristic.MANHATTAN
        ):
            distance = (
                abs(
                    node.x
                    - goal.x
                )
                + abs(
                    node.y
                    - goal.y
                )
                + abs(
                    node.z
                    - goal.z
                )
            )
        else:
            distance = (
                _distance_floor(
                    node,
                    goal,
                )
            )
        return (
            distance
            * self.policy.heuristic_scale
        )

    def set_blocked(
        self,
        node_id: str,
        blocked: bool = True,
    ) -> None:
        _token(
            node_id,
            "navigation node id",
        )
        if node_id not in self.nodes:
            raise GameEngineLabError(
                "navigation block references missing node"
            )
        if type(blocked) is not bool:
            raise GameEngineLabError(
                "navigation blocked flag must be boolean"
            )
        if not self.policy.dynamic_obstacles:
            raise GameEngineLabError(
                "dynamic navigation obstacles unavailable in engine era"
            )
        if blocked:
            self._blocked.add(
                node_id
            )
        else:
            self._blocked.discard(
                node_id
            )

    def set_penalty(
        self,
        node_id: str,
        cost: int,
    ) -> None:
        _token(
            node_id,
            "navigation node id",
        )
        if node_id not in self.nodes:
            raise GameEngineLabError(
                "navigation penalty references missing node"
            )
        if not self.policy.dynamic_costs:
            raise GameEngineLabError(
                "dynamic navigation costs unavailable in engine era"
            )
        if (
            type(cost) is not int
            or not 0
            <= cost
            <= 1_000_000_000
        ):
            raise GameEngineLabError(
                "navigation dynamic penalty outside bounds"
            )
        if cost == 0:
            self._penalties.pop(
                node_id,
                None,
            )
        else:
            self._penalties[
                node_id
            ] = cost

    def _region_route(
        self,
        start: str,
        goal: str,
    ) -> tuple[str, ...]:
        start_region = (
            self.nodes[
                start
            ].region
        )
        goal_region = (
            self.nodes[
                goal
            ].region
        )
        if not self.policy.hierarchical:
            return ()
        if start_region == goal_region:
            return (
                start_region,
            )
        graph: dict[
            str,
            set[str],
        ] = {}
        for source_id, rows in (
            self.adjacency.items()
        ):
            source_region = (
                self.nodes[
                    source_id
                ].region
            )
            graph.setdefault(
                source_region,
                set(),
            )
            for target_id, _ in rows:
                target_region = (
                    self.nodes[
                        target_id
                    ].region
                )
                if (
                    target_region
                    != source_region
                ):
                    graph[
                        source_region
                    ].add(
                        target_region
                    )
        queue = deque(
            [start_region]
        )
        parent = {
            start_region:
                None,
        }
        while queue:
            current = (
                queue.popleft()
            )
            if current == goal_region:
                break
            for neighbor in sorted(
                graph.get(
                    current,
                    (),
                )
            ):
                if neighbor in parent:
                    continue
                parent[
                    neighbor
                ] = current
                queue.append(
                    neighbor
                )
        if goal_region not in parent:
            return ()
        route = []
        current: str | None = (
            goal_region
        )
        while current is not None:
            route.append(
                current
            )
            current = parent[
                current
            ]
        return tuple(
            reversed(
                route
            )
        )

    def _effective_state(
        self,
        query: NavigationQuery,
    ) -> tuple[
        frozenset[str],
        dict[str, int],
    ]:
        if query.start not in self.nodes:
            raise GameEngineLabError(
                "navigation query start node missing"
            )
        if query.goal not in self.nodes:
            raise GameEngineLabError(
                "navigation query goal node missing"
            )
        if (
            query.blocked
            and not self.policy.dynamic_obstacles
        ):
            raise GameEngineLabError(
                "query-time navigation obstacles unavailable in engine era"
            )
        if (
            query.penalties
            and not self.policy.dynamic_costs
        ):
            raise GameEngineLabError(
                "query-time navigation costs unavailable in engine era"
            )
        for node_id in query.blocked:
            if node_id not in self.nodes:
                raise GameEngineLabError(
                    "navigation query blocks missing node"
                )
        penalties = dict(
            self._penalties
        )
        for node_id, cost in (
            query.penalties
        ):
            if node_id not in self.nodes:
                raise GameEngineLabError(
                    "navigation query penalizes missing node"
                )
            if cost == 0:
                penalties.pop(
                    node_id,
                    None,
                )
            else:
                penalties[
                    node_id
                ] = cost
        blocked = frozenset(
            self._blocked
            | set(
                query.blocked
            )
        )
        if (
            query.start in blocked
            or query.goal in blocked
        ):
            return (
                blocked,
                penalties,
            )
        return (
            blocked,
            penalties,
        )

    def _direct(
        self,
        query: NavigationQuery,
        blocked: frozenset[str],
        penalties: Mapping[str, int],
    ) -> tuple[
        tuple[str, ...],
        int | None,
        int,
    ]:
        if (
            query.start in blocked
            or query.goal in blocked
        ):
            return (
                (),
                None,
                0,
            )
        if query.start == query.goal:
            return (
                (
                    query.start,
                ),
                0,
                1,
            )
        for neighbor, cost in (
            self.adjacency[
                query.start
            ]
        ):
            if (
                neighbor
                == query.goal
                and neighbor
                not in blocked
            ):
                return (
                    (
                        query.start,
                        query.goal,
                    ),
                    cost
                    + penalties.get(
                        query.goal,
                        0,
                    ),
                    2,
                )
        return (
            (),
            None,
            1,
        )

    def _bfs(
        self,
        query: NavigationQuery,
        blocked: frozenset[str],
        penalties: Mapping[str, int],
    ) -> tuple[
        tuple[str, ...],
        int | None,
        int,
    ]:
        if (
            query.start in blocked
            or query.goal in blocked
        ):
            return (
                (),
                None,
                0,
            )
        queue = deque(
            [query.start]
        )
        parent: dict[
            str,
            str | None,
        ] = {
            query.start:
                None,
        }
        expanded = 0
        while queue:
            current = (
                queue.popleft()
            )
            expanded += 1
            if current == query.goal:
                break
            for neighbor, _ in (
                self.adjacency[
                    current
                ]
            ):
                if (
                    neighbor in blocked
                    or neighbor in parent
                ):
                    continue
                parent[
                    neighbor
                ] = current
                queue.append(
                    neighbor
                )
        if query.goal not in parent:
            return (
                (),
                None,
                expanded,
            )
        path = self._reconstruct(
            parent,
            query.goal,
        )
        return (
            path,
            self._path_cost(
                path,
                penalties,
            ),
            expanded,
        )

    def _astar(
        self,
        query: NavigationQuery,
        blocked: frozenset[str],
        penalties: Mapping[str, int],
    ) -> tuple[
        tuple[str, ...],
        int | None,
        int,
    ]:
        if (
            query.start in blocked
            or query.goal in blocked
        ):
            return (
                (),
                None,
                0,
            )
        frontier: list[
            tuple[
                int,
                int,
                str,
            ]
        ] = [
            (
                self._heuristic(
                    query.start,
                    query.goal,
                ),
                0,
                query.start,
            )
        ]
        best = {
            query.start:
                0,
        }
        parent: dict[
            str,
            str | None,
        ] = {
            query.start:
                None,
        }
        expanded = 0
        while frontier:
            _, cost, current = (
                heapq.heappop(
                    frontier
                )
            )
            if (
                cost
                != best.get(
                    current
                )
            ):
                continue
            expanded += 1
            if current == query.goal:
                break
            for neighbor, edge_cost in (
                self.adjacency[
                    current
                ]
            ):
                if neighbor in blocked:
                    continue
                candidate = (
                    cost
                    + edge_cost
                    + penalties.get(
                        neighbor,
                        0,
                    )
                )
                previous = (
                    best.get(
                        neighbor
                    )
                )
                if (
                    previous is None
                    or candidate
                    < previous
                ):
                    best[
                        neighbor
                    ] = candidate
                    parent[
                        neighbor
                    ] = current
                    heapq.heappush(
                        frontier,
                        (
                            candidate
                            + self._heuristic(
                                neighbor,
                                query.goal,
                            ),
                            candidate,
                            neighbor,
                        ),
                    )
                elif (
                    candidate
                    == previous
                    and current
                    < (
                        parent[
                            neighbor
                        ]
                        or current
                    )
                ):
                    parent[
                        neighbor
                    ] = current
                    heapq.heappush(
                        frontier,
                        (
                            candidate
                            + self._heuristic(
                                neighbor,
                                query.goal,
                            ),
                            candidate,
                            neighbor,
                        ),
                    )
        if query.goal not in best:
            return (
                (),
                None,
                expanded,
            )
        return (
            self._reconstruct(
                parent,
                query.goal,
            ),
            best[
                query.goal
            ],
            expanded,
        )

    @staticmethod
    def _reconstruct(
        parent: Mapping[
            str,
            str | None,
        ],
        goal: str,
    ) -> tuple[str, ...]:
        values = []
        current: str | None = (
            goal
        )
        while current is not None:
            values.append(
                current
            )
            current = parent[
                current
            ]
        return tuple(
            reversed(
                values
            )
        )

    def _edge_cost(
        self,
        source: str,
        target: str,
    ) -> int:
        for neighbor, cost in (
            self.adjacency[
                source
            ]
        ):
            if neighbor == target:
                return cost
        raise GameEngineLabError(
            "navigation path contains non-edge hop"
        )

    def _path_cost(
        self,
        path: tuple[str, ...],
        penalties: Mapping[
            str,
            int,
        ],
    ) -> int:
        total = 0
        for index in range(
            1,
            len(path),
        ):
            total += self._edge_cost(
                path[
                    index - 1
                ],
                path[
                    index
                ],
            )
            total += penalties.get(
                path[
                    index
                ],
                0,
            )
        return total

    def _smooth(
        self,
        path: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Collapse collinear waypoint runs without changing path cost authority."""
        if (
            not self.policy.smoothing
            or len(path) <= 2
        ):
            return path
        result = [
            path[0]
        ]
        for index in range(
            1,
            len(path) - 1,
        ):
            left = self.nodes[
                result[-1]
            ]
            current = self.nodes[
                path[index]
            ]
            right = self.nodes[
                path[index + 1]
            ]
            ax = (
                current.x
                - left.x
            )
            ay = (
                current.y
                - left.y
            )
            az = (
                current.z
                - left.z
            )
            bx = (
                right.x
                - current.x
            )
            by = (
                right.y
                - current.y
            )
            bz = (
                right.z
                - current.z
            )
            cross = (
                ay * bz
                - az * by,
                az * bx
                - ax * bz,
                ax * by
                - ay * bx,
            )
            same_direction = (
                ax * bx
                + ay * by
                + az * bz
                > 0
            )
            if (
                cross
                == (
                    0,
                    0,
                    0,
                )
                and same_direction
            ):
                continue
            result.append(
                path[index]
            )
        result.append(
            path[-1]
        )
        return tuple(
            result
        )

    def path(
        self,
        query: NavigationQuery,
    ) -> PathResult:
        blocked, penalties = (
            self._effective_state(
                query
            )
        )
        if (
            self.policy.mode
            is NavigationMode.DIRECT
        ):
            path, cost, expanded = (
                self._direct(
                    query,
                    blocked,
                    penalties,
                )
            )
        elif (
            self.policy.mode
            is NavigationMode.GRID_BFS
        ):
            path, cost, expanded = (
                self._bfs(
                    query,
                    blocked,
                    penalties,
                )
            )
        else:
            path, cost, expanded = (
                self._astar(
                    query,
                    blocked,
                    penalties,
                )
            )
        if (
            len(path)
            > self.policy.max_path_nodes
        ):
            raise GameEngineLabError(
                "navigation path exceeds era result budget"
            )
        smoothed_path = (
            self._smooth(
                path
            )
            if path
            else path
        )
        region_route = (
            self._region_route(
                query.start,
                query.goal,
            )
            if path
            else ()
        )
        payload = {
            "engine_era":
                self.era.value,
            "mode":
                self.policy.mode.value,
            "start":
                query.start,
            "goal":
                query.goal,
            "path":
                smoothed_path,
            "unsmoothed_path":
                path,
            "total_cost":
                cost,
            "expanded_nodes":
                expanded,
            "region_route":
                region_route,
            "blocked":
                tuple(
                    sorted(
                        blocked
                    )
                ),
            "penalties":
                tuple(
                    sorted(
                        penalties.items()
                    )
                ),
        }
        return PathResult(
            self.era,
            self.policy.mode,
            query.start,
            query.goal,
            smoothed_path,
            cost,
            expanded,
            (
                smoothed_path
                != path
            ),
            region_route,
            _digest(
                payload
            ),
        )

    def snapshot(
        self,
    ) -> NavigationSnapshot:
        payload = {
            "engine_era":
                self.era.value,
            "blocked":
                tuple(
                    sorted(
                        self._blocked
                    )
                ),
            "penalties":
                tuple(
                    sorted(
                        self._penalties.items()
                    )
                ),
        }
        return NavigationSnapshot(
            self.era,
            payload[
                "blocked"
            ],
            payload[
                "penalties"
            ],
            _digest(
                payload
            ),
        )

    def restore(
        self,
        snapshot: NavigationSnapshot,
    ) -> None:
        if snapshot.era is not self.era:
            raise GameEngineLabError(
                "navigation snapshot era mismatch"
            )
        payload = {
            "engine_era":
                snapshot.era.value,
            "blocked":
                snapshot.blocked,
            "penalties":
                snapshot.penalties,
        }
        if (
            _digest(
                payload
            )
            != snapshot.digest
        ):
            raise GameEngineLabError(
                "navigation snapshot digest mismatch"
            )
        blocked = set(
            snapshot.blocked
        )
        penalties = dict(
            snapshot.penalties
        )
        if (
            not blocked
            <= set(
                self.nodes
            )
            or not set(
                penalties
            )
            <= set(
                self.nodes
            )
        ):
            raise GameEngineLabError(
                "navigation snapshot references missing node"
            )
        if (
            blocked
            and not self.policy.dynamic_obstacles
        ):
            raise GameEngineLabError(
                "navigation snapshot violates dynamic obstacle policy"
            )
        if (
            penalties
            and not self.policy.dynamic_costs
        ):
            raise GameEngineLabError(
                "navigation snapshot violates dynamic cost policy"
            )
        for cost in (
            penalties.values()
        ):
            if (
                type(cost) is not int
                or not 0
                < cost
                <= 1_000_000_000
            ):
                raise GameEngineLabError(
                    "navigation snapshot penalty invalid"
                )
        self._blocked = blocked
        self._penalties = penalties

    def fingerprint(
        self,
    ) -> str:
        return self.snapshot().digest

    def steer(
        self,
        *,
        agent_x: float,
        agent_z: float,
        desired_x: float,
        desired_z: float,
        neighbors: Iterable[
            SteeringNeighbor
        ] = (),
        separation_radius: float = 2.0,
    ) -> SteeringResult:
        if not self.policy.crowd_steering:
            raise GameEngineLabError(
                "crowd steering unavailable in engine era"
            )
        agent_x = _finite(
            agent_x,
            "steering agent x",
        )
        agent_z = _finite(
            agent_z,
            "steering agent z",
        )
        desired_x = _finite(
            desired_x,
            "steering desired x",
        )
        desired_z = _finite(
            desired_z,
            "steering desired z",
        )
        separation_radius = (
            _finite(
                separation_radius,
                "steering separation radius",
            )
        )
        if not (
            0
            < separation_radius
            <= 1000
        ):
            raise GameEngineLabError(
                "steering separation radius outside bounds"
            )
        values = tuple(
            sorted(
                neighbors,
                key=lambda item:
                    item.agent_id,
            )
        )
        if (
            len(values)
            > MAX_STEERING_NEIGHBORS
        ):
            raise GameEngineLabError(
                "steering neighbor budget exceeded"
            )
        if len(
            {
                item.agent_id
                for item
                in values
            }
        ) != len(values):
            raise GameEngineLabError(
                "steering neighbor ids must be unique"
            )
        vx = desired_x
        vz = desired_z
        considered = []
        radius_sq = (
            separation_radius
            * separation_radius
        )
        for neighbor in values:
            dx = (
                agent_x
                - neighbor.x
            )
            dz = (
                agent_z
                - neighbor.z
            )
            distance_sq = (
                dx * dx
                + dz * dz
            )
            if (
                distance_sq
                <= 1e-12
                or distance_sq
                >= radius_sq
            ):
                continue
            distance = math.sqrt(
                distance_sq
            )
            strength = (
                1.0
                - distance
                / separation_radius
            )
            vx += (
                dx
                / distance
                * strength
            )
            vz += (
                dz
                / distance
                * strength
            )
            considered.append(
                neighbor.agent_id
            )
        magnitude = math.hypot(
            vx,
            vz,
        )
        if magnitude > 1.0:
            vx /= magnitude
            vz /= magnitude
        vx = round(
            vx,
            12,
        )
        vz = round(
            vz,
            12,
        )
        payload = {
            "engine_era":
                self.era.value,
            "velocity": (
                vx,
                vz,
            ),
            "considered":
                tuple(
                    considered
                ),
        }
        return SteeringResult(
            self.era,
            vx,
            vz,
            tuple(
                considered
            ),
            _digest(
                payload
            ),
        )


def _reference_shortest_cost(
    runtime: NavigationRuntime,
    query: NavigationQuery,
) -> int | None:
    blocked, penalties = (
        runtime._effective_state(
            query
        )
    )
    if (
        query.start in blocked
        or query.goal in blocked
    ):
        return None
    frontier = [
        (
            0,
            query.start,
        )
    ]
    best = {
        query.start:
            0,
    }
    while frontier:
        cost, current = (
            heapq.heappop(
                frontier
            )
        )
        if (
            cost
            != best.get(
                current
            )
        ):
            continue
        if current == query.goal:
            return cost
        for neighbor, edge_cost in (
            runtime.adjacency[
                current
            ]
        ):
            if neighbor in blocked:
                continue
            candidate = (
                cost
                + edge_cost
                + penalties.get(
                    neighbor,
                    0,
                )
            )
            if (
                candidate
                < best.get(
                    neighbor,
                    1 << 62,
                )
            ):
                best[
                    neighbor
                ] = candidate
                heapq.heappush(
                    frontier,
                    (
                        candidate,
                        neighbor,
                    ),
                )
    return None


@dataclass(frozen=True, slots=True)
class NavigationProbe:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class NavigationQualityReport:
    era: EngineEra
    probes: tuple[
        NavigationProbe,
        ...,
    ]

    @property
    def passed(self) -> bool:
        return bool(
            self.probes
        ) and all(
            probe.passed
            for probe
            in self.probes
        )

    @property
    def score(self) -> float:
        return sum(
            probe.passed
            for probe
            in self.probes
        ) / max(
            1,
            len(
                self.probes
            ),
        )

    @property
    def failed(
        self,
    ) -> tuple[str, ...]:
        return tuple(
            probe.name
            for probe
            in self.probes
            if not probe.passed
        )


class NavigationAdversary:
    """Attest compiled navigation plus deterministic path/runtime semantics."""

    def evaluate(
        self,
        sandbox: RoutedEngineSandbox,
        source: NavigationSource,
    ) -> NavigationQualityReport:
        names = (
            "manifest",
            "inventory",
            "integrity",
            "replay",
            "optimality",
            "snapshot",
            "dynamic",
            "hierarchy",
            "steering",
        )
        try:
            expected = (
                compile_navigation_build(
                    sandbox.era,
                    source,
                )
            )
            manifest = json.loads(
                sandbox.tree.read(
                    "navigation/compiled/manifest.json"
                )
            )
            policy_doc = json.loads(
                sandbox.tree.read(
                    "navigation/compiled/policy.json"
                )
            )
            graph_doc = json.loads(
                sandbox.tree.read(
                    "navigation/compiled/graph.json"
                )
            )
        except (
            GameEngineLabError,
            json.JSONDecodeError,
        ) as exc:
            return NavigationQualityReport(
                sandbox.era,
                tuple(
                    NavigationProbe(
                        name,
                        False,
                        str(exc),
                    )
                    for name in names
                ),
            )

        expected_paths = {
            patch.path
            for patch
            in navigation_build_patches(
                expected
            )
        }
        actual_paths = {
            path
            for path
            in sandbox.tree.files
            if path.startswith(
                "navigation/compiled/"
            )
        }
        manifest_ok = (
            manifest
            == expected.manifest()
        )
        inventory_ok = (
            expected_paths
            == actual_paths
        )
        integrity_ok = (
            policy_doc
            == navigation_policy_document(
                sandbox.era
            )
            and graph_doc
            == expected.source_document
        )

        runtime_a = (
            NavigationRuntime(
                sandbox.era,
                source,
            )
        )
        runtime_b = (
            NavigationRuntime(
                sandbox.era,
                source,
            )
        )
        query = canonical_navigation_query(
            sandbox.era
        )
        first = runtime_a.path(
            query
        )
        second = runtime_b.path(
            query
        )
        replay_ok = (
            first == second
            and first.found
            and len(
                first.digest
            )
            == 64
        )
        reference = (
            _reference_shortest_cost(
                runtime_a,
                query,
            )
        )
        optimality_ok = (
            first.total_cost
            == reference
        )

        snapshot_runtime = (
            NavigationRuntime(
                sandbox.era,
                source,
            )
        )
        snapshot = (
            snapshot_runtime.snapshot()
        )
        before = (
            snapshot_runtime.fingerprint()
        )
        policy = (
            snapshot_runtime.policy
        )
        if policy.dynamic_obstacles:
            candidate = next(
                (
                    node_id
                    for node_id
                    in first.path[
                        1:-1
                    ]
                ),
                None,
            )
            if candidate is not None:
                snapshot_runtime.set_blocked(
                    candidate,
                    True,
                )
        if policy.dynamic_costs:
            snapshot_runtime.set_penalty(
                query.goal,
                5,
            )
        snapshot_runtime.restore(
            snapshot
        )
        snapshot_ok = (
            snapshot_runtime.fingerprint()
            == before
        )

        dynamic_ok = True
        if policy.dynamic_obstacles:
            middle = next(
                (
                    node_id
                    for node_id
                    in first.path[
                        1:-1
                    ]
                ),
                None,
            )
            if middle is not None:
                dynamic_runtime = (
                    NavigationRuntime(
                        sandbox.era,
                        source,
                    )
                )
                dynamic_runtime.set_blocked(
                    middle,
                    True,
                )
                reroute = (
                    dynamic_runtime.path(
                        query
                    )
                )
                dynamic_ok = (
                    (
                        not reroute.found
                        or middle
                        not in reroute.path
                    )
                    and reroute
                    != first
                )

        hierarchy_ok = (
            bool(
                first.region_route
            )
            if policy.hierarchical
            else first.region_route
            == ()
        )

        steering_ok = True
        if policy.crowd_steering:
            kwargs = {
                "agent_x":
                    0.0,
                "agent_z":
                    0.0,
                "desired_x":
                    1.0,
                "desired_z":
                    0.0,
                "neighbors": (
                    SteeringNeighbor(
                        "left",
                        -0.5,
                        0.0,
                    ),
                    SteeringNeighbor(
                        "front",
                        0.5,
                        0.25,
                    ),
                ),
            }
            steer_a = (
                runtime_a.steer(
                    **kwargs
                )
            )
            steer_b = (
                runtime_b.steer(
                    **kwargs
                )
            )
            steering_ok = (
                steer_a == steer_b
                and math.hypot(
                    steer_a.velocity_x,
                    steer_a.velocity_z,
                )
                <= 1.000000000001
            )

        return NavigationQualityReport(
            sandbox.era,
            (
                NavigationProbe(
                    "manifest",
                    manifest_ok,
                    "canonical navigation manifest",
                ),
                NavigationProbe(
                    "inventory",
                    inventory_ok,
                    "exact compiled navigation inventory",
                ),
                NavigationProbe(
                    "integrity",
                    integrity_ok,
                    "navigation policy and graph attested",
                ),
                NavigationProbe(
                    "replay",
                    replay_ok,
                    "deterministic path replay",
                ),
                NavigationProbe(
                    "optimality",
                    optimality_ok,
                    "path cost matches independent Dijkstra reference",
                ),
                NavigationProbe(
                    "snapshot",
                    snapshot_ok,
                    "dynamic navigation snapshot roundtrip",
                ),
                NavigationProbe(
                    "dynamic",
                    dynamic_ok,
                    "dynamic obstacle rerouting contract",
                ),
                NavigationProbe(
                    "hierarchy",
                    hierarchy_ok,
                    "hierarchical region route contract",
                ),
                NavigationProbe(
                    "steering",
                    steering_ok,
                    "deterministic crowd steering contract",
                ),
            ),
        )


def canonical_navigation_source(
    era: EngineEra | str,
) -> NavigationSource:
    policy = navigation_policy(
        era
    )
    if (
        policy.mode
        is NavigationMode.DIRECT
    ):
        return NavigationSource(
            (
                NavNode(
                    "start",
                    0,
                    0,
                ),
                NavNode(
                    "goal",
                    1,
                    0,
                ),
            ),
            (
                NavEdge(
                    "start",
                    "goal",
                    10,
                ),
            ),
        )

    nodes = []
    for y in range(5):
        for x in range(5):
            z = (
                0
                if policy.dimensions
                == 2
                else (
                    1
                    if (
                        x == 2
                        and y in {
                            1,
                            2,
                            3,
                        }
                    )
                    else 0
                )
            )
            nodes.append(
                NavNode(
                    f"n{x}_{y}",
                    x,
                    y,
                    z,
                    (
                        f"r{x // 2}_{y // 2}"
                        if policy.hierarchical
                        else "root"
                    ),
                )
            )

    edges = []
    for y in range(5):
        for x in range(5):
            current = (
                f"n{x}_{y}"
            )
            if x < 4:
                extra = (
                    2
                    if (
                        policy.mode
                        is NavigationMode.GRID_ASTAR
                        and y == 2
                    )
                    else 0
                )
                edges.append(
                    NavEdge(
                        current,
                        f"n{x + 1}_{y}",
                        10 + extra,
                    )
                )
            if y < 4:
                extra = (
                    1
                    if (
                        policy.mode
                        is NavigationMode.GRID_ASTAR
                        and x == 1
                    )
                    else 0
                )
                edges.append(
                    NavEdge(
                        current,
                        f"n{x}_{y + 1}",
                        10 + extra,
                    )
                )

    return NavigationSource(
        tuple(
            nodes
        ),
        tuple(
            edges
        ),
    )


def canonical_navigation_query(
    era: EngineEra | str,
) -> NavigationQuery:
    policy = navigation_policy(
        era
    )
    if (
        policy.mode
        is NavigationMode.DIRECT
    ):
        return NavigationQuery(
            "start",
            "goal",
        )
    return NavigationQuery(
        "n0_0",
        "n4_4",
    )


def build_navigation_runtime(
    era: EngineEra | str,
    source:
        NavigationSource
        | None = None,
) -> NavigationRuntime:
    key = (
        era
        if isinstance(
            era,
            EngineEra,
        )
        else EngineEra(
            str(era)
        )
    )
    return NavigationRuntime(
        key,
        (
            source
            if source is not None
            else canonical_navigation_source(
                key
            )
        ),
    )
