"""Topology and gap analysis for the Jeeves semantic lens plane.

The semantic plane contains hundreds of lenses and explicit interaction rules.
This module turns that catalog into an inspectable graph so routing and research
can reason about *coverage of the lens system itself*.

Topology is descriptive. An edge means an interaction rule exists; a suggested
bridge is only a research candidate based on shared cues and structural
complementarity. Neither is evidence about the world being analyzed.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .semantic_depth_interactions import depth_interaction_rules
from .semantic_frontier import (
    LensInteractionKind,
    LensInteractionRule,
    default_interaction_rules,
)
from .semantic_lenses import (
    LensFamily,
    SemanticLensRegistry,
    SemanticLensSpec,
    SemanticRole,
)
from .semantic_plane_interactions import plane_interaction_rules
from .types import AgentContractError, positive_int, probability, stable_fingerprint, stable_id


@dataclass(frozen=True, slots=True)
class LensTopologyEdge:
    edge_id: str
    left_key: str
    right_key: str
    kind: LensInteractionKind
    symmetric: bool
    source: str
    cross_family: bool
    tangent_axis_hint: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return (
            tuple(sorted((self.left_key, self.right_key)))
            if self.symmetric
            else (self.left_key, self.right_key)
        )


@dataclass(frozen=True, slots=True)
class LensTopologyNode:
    lens_key: str
    family: LensFamily
    role: SemanticRole
    rare: bool
    degree: int
    cross_family_degree: int
    neighbor_families: tuple[LensFamily, ...]


@dataclass(frozen=True, slots=True)
class LensBridgeCandidate:
    candidate_id: str
    left_key: str
    right_key: str
    left_family: LensFamily
    right_family: LensFamily
    score: float
    cue_overlap: float
    role_novelty: float
    cross_family: bool
    shared_cues: tuple[str, ...]
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "score", probability("bridge score", self.score))
        object.__setattr__(self, "cue_overlap", probability("cue overlap", self.cue_overlap))
        object.__setattr__(self, "role_novelty", probability("role novelty", self.role_novelty))


@dataclass(frozen=True, slots=True)
class SemanticTopologySnapshot:
    nodes: tuple[LensTopologyNode, ...]
    edges: tuple[LensTopologyEdge, ...]
    component_count: int
    largest_component_size: int
    isolated_lens_keys: tuple[str, ...]
    bridge_lens_keys: tuple[str, ...]
    conflict_edge_ids: tuple[str, ...]
    reinforcement_edge_ids: tuple[str, ...]
    family_pair_counts: tuple[tuple[str, str, int], ...]
    candidate_bridge_count: int
    fingerprint: str


class SemanticLensTopology:
    """Build and inspect the static interaction topology of a semantic registry."""

    def __init__(
        self,
        registry: SemanticLensRegistry,
        *,
        rules: Iterable[LensInteractionRule] | None = None,
    ) -> None:
        if not isinstance(registry, SemanticLensRegistry):
            raise TypeError("registry must be SemanticLensRegistry")
        self.registry = registry
        if rules is None:
            source_rules = (
                ("default", default_interaction_rules()),
                ("plane", plane_interaction_rules()),
                ("depth", depth_interaction_rules()),
            )
        else:
            source_rules = (("custom", tuple(rules)),)

        self._specs = {spec.key: spec for spec in registry.all()}
        self._edges: tuple[LensTopologyEdge, ...] = self._build_edges(
            source_rules
        )
        self._adjacency: dict[str, set[str]] = {
            key: set() for key in self._specs
        }
        for edge in self._edges:
            self._adjacency[edge.left_key].add(edge.right_key)
            self._adjacency[edge.right_key].add(edge.left_key)
        self._bridge_candidates = self._build_bridge_candidates()
        self._snapshot = self._build_snapshot()

    def _build_edges(
        self,
        source_rules: Sequence[tuple[str, Sequence[LensInteractionRule]]],
    ) -> tuple[LensTopologyEdge, ...]:
        seen: set[tuple[str, str, bool]] = set()
        edges: list[LensTopologyEdge] = []
        for source, rules in source_rules:
            for rule in rules:
                if rule.left_key not in self._specs or rule.right_key not in self._specs:
                    # Topology should be buildable on partial/custom registries.
                    continue
                identity = (
                    rule.key[0],
                    rule.key[1],
                    rule.symmetric,
                )
                if identity in seen:
                    raise AgentContractError(
                        f"duplicate semantic topology interaction: {rule.key}"
                    )
                seen.add(identity)
                left = self._specs[rule.left_key]
                right = self._specs[rule.right_key]
                edge_payload: dict[str, object] = {
                    "rule": rule.key,
                    "kind": rule.kind.value,
                    "symmetric": rule.symmetric,
                    "source": source,
                }
                if source == "learned" and rule.metadata:
                    edge_payload["rule_metadata"] = dict(rule.metadata)
                edge_id = stable_id(
                    "semantic-topology-edge",
                    edge_payload,
                    length=28,
                )
                edges.append(
                    LensTopologyEdge(
                        edge_id=edge_id,
                        left_key=rule.left_key,
                        right_key=rule.right_key,
                        kind=rule.kind,
                        symmetric=rule.symmetric,
                        source=source,
                        cross_family=left.family is not right.family,
                        tangent_axis_hint=rule.tangent_axis_hint,
                    )
                )
        return tuple(
            sorted(
                edges,
                key=lambda edge: (
                    edge.left_key,
                    edge.right_key,
                    edge.kind.value,
                    edge.source,
                ),
            )
        )

    def _components_for(
        self,
        adjacency: Mapping[str, set[str]],
    ) -> tuple[tuple[str, ...], ...]:
        unseen = set(self._specs)
        components: list[tuple[str, ...]] = []
        while unseen:
            root = min(unseen)
            queue = [root]
            unseen.remove(root)
            members: list[str] = []
            while queue:
                key = queue.pop()
                members.append(key)
                for neighbor in sorted(adjacency[key]):
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        queue.append(neighbor)
            components.append(tuple(sorted(members)))
        return tuple(
            sorted(
                components,
                key=lambda values: (-len(values), values[0]),
            )
        )

    def _components(self) -> tuple[tuple[str, ...], ...]:
        return self._components_for(self._adjacency)

    def _build_snapshot(
        self,
        *,
        edges: Sequence[LensTopologyEdge] | None = None,
        adjacency: Mapping[str, set[str]] | None = None,
        bridge_candidates: Sequence[LensBridgeCandidate] | None = None,
    ) -> SemanticTopologySnapshot:
        effective_edges = (
            self._edges if edges is None else tuple(edges)
        )
        effective_adjacency = (
            self._adjacency if adjacency is None else adjacency
        )
        effective_candidates = (
            self._bridge_candidates
            if bridge_candidates is None
            else tuple(bridge_candidates)
        )
        nodes: list[LensTopologyNode] = []
        family_pair_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        for key, spec in sorted(self._specs.items()):
            neighbors = effective_adjacency[key]
            neighbor_families = tuple(
                sorted(
                    {self._specs[value].family for value in neighbors},
                    key=lambda family: family.value,
                )
            )
            cross_degree = sum(
                self._specs[value].family is not spec.family
                for value in neighbors
            )
            nodes.append(
                LensTopologyNode(
                    lens_key=key,
                    family=spec.family,
                    role=spec.role,
                    rare=spec.rare,
                    degree=len(neighbors),
                    cross_family_degree=cross_degree,
                    neighbor_families=neighbor_families,
                )
            )
        for edge in effective_edges:
            left = self._specs[edge.left_key].family.value
            right = self._specs[edge.right_key].family.value
            pair = tuple(sorted((left, right)))
            family_pair_counts[pair] += 1

        components = self._components_for(effective_adjacency)
        isolated = tuple(
            node.lens_key for node in nodes if node.degree == 0
        )
        bridges = tuple(
            sorted(
                node.lens_key
                for node in nodes
                if node.cross_family_degree >= 2
                and len(node.neighbor_families) >= 2
            )
        )
        conflicts = tuple(
            edge.edge_id
            for edge in effective_edges
            if edge.kind is LensInteractionKind.CONFLICTS
        )
        reinforces = tuple(
            edge.edge_id
            for edge in effective_edges
            if edge.kind is LensInteractionKind.REINFORCES
        )
        pairs = tuple(
            (left, right, count)
            for (left, right), count in sorted(family_pair_counts.items())
        )
        payload = {
            "nodes": [
                (
                    node.lens_key,
                    node.family.value,
                    node.role.value,
                    node.degree,
                    node.cross_family_degree,
                    node.rare,
                    self._specs[node.lens_key].activation_cues,
                    [family.value for family in node.neighbor_families],
                )
                for node in nodes
            ],
            "edges": [
                (
                    edge.edge_id,
                    edge.key,
                    edge.kind.value,
                    edge.source,
                    edge.cross_family,
                )
                for edge in effective_edges
            ],
            "components": components,
            "isolated": isolated,
            "bridges": bridges,
            "family_pairs": pairs,
            "bridge_candidates": [
                (
                    item.candidate_id,
                    item.left_key,
                    item.right_key,
                    item.score,
                    item.shared_cues,
                )
                for item in effective_candidates
            ],
        }
        return SemanticTopologySnapshot(
            nodes=tuple(nodes),
            edges=tuple(effective_edges),
            component_count=len(components),
            largest_component_size=max((len(values) for values in components), default=0),
            isolated_lens_keys=isolated,
            bridge_lens_keys=bridges,
            conflict_edge_ids=conflicts,
            reinforcement_edge_ids=reinforces,
            family_pair_counts=pairs,
            candidate_bridge_count=len(effective_candidates),
            fingerprint=stable_fingerprint(payload),
        )

    @property
    def snapshot(self) -> SemanticTopologySnapshot:
        return self._snapshot

    def snapshot_with_rules(
        self,
        supplemental_rules: Sequence[LensInteractionRule],
    ) -> SemanticTopologySnapshot:
        """Return an immutable effective topology including validated rules."""

        rules = tuple(supplemental_rules)
        if not rules:
            return self._snapshot
        if any(not isinstance(item, LensInteractionRule) for item in rules):
            raise TypeError(
                "supplemental_rules must contain LensInteractionRule values"
            )

        static_identities = {
            (edge.key[0], edge.key[1], edge.symmetric)
            for edge in self._edges
        }
        for rule in rules:
            identity = (
                rule.key[0],
                rule.key[1],
                rule.symmetric,
            )
            if identity in static_identities:
                raise AgentContractError(
                    "learned topology rule collides with static edge: "
                    + str(rule.key)
                )

        learned_edges = self._build_edges(
            (("learned", rules),)
        )
        combined_edges = tuple(
            sorted(
                (*self._edges, *learned_edges),
                key=lambda edge: (
                    edge.left_key,
                    edge.right_key,
                    edge.kind.value,
                    edge.source,
                ),
            )
        )
        adjacency: dict[str, set[str]] = {
            key: set() for key in self._specs
        }
        for edge in combined_edges:
            adjacency[edge.left_key].add(edge.right_key)
            adjacency[edge.right_key].add(edge.left_key)

        learned_pairs = {
            tuple(sorted((edge.left_key, edge.right_key)))
            for edge in learned_edges
        }
        remaining_candidates = tuple(
            item
            for item in self._bridge_candidates
            if tuple(sorted((item.left_key, item.right_key)))
            not in learned_pairs
        )
        return self._build_snapshot(
            edges=combined_edges,
            adjacency=adjacency,
            bridge_candidates=remaining_candidates,
        )

    def neighbors_with_rules(
        self,
        lens_key: str,
        supplemental_rules: Sequence[LensInteractionRule],
    ) -> tuple[str, ...]:
        snapshot = self.snapshot_with_rules(supplemental_rules)
        key = str(lens_key).strip().casefold()
        if key not in self._specs:
            raise KeyError(key)
        neighbors: set[str] = set()
        for edge in snapshot.edges:
            if edge.left_key == key:
                neighbors.add(edge.right_key)
            elif edge.right_key == key:
                neighbors.add(edge.left_key)
        return tuple(sorted(neighbors))

    def shortest_path_with_rules(
        self,
        source_key: str,
        target_key: str,
        *,
        supplemental_rules: Sequence[LensInteractionRule],
        max_depth: int = 8,
    ) -> tuple[str, ...]:
        source = str(source_key).strip().casefold()
        target = str(target_key).strip().casefold()
        if source not in self._specs:
            raise KeyError(source)
        if target not in self._specs:
            raise KeyError(target)
        if source == target:
            return (source,)
        depth_limit = positive_int("max_depth", max_depth, maximum=100)
        snapshot = self.snapshot_with_rules(supplemental_rules)
        adjacency: dict[str, set[str]] = {
            key: set() for key in self._specs
        }
        for edge in snapshot.edges:
            adjacency[edge.left_key].add(edge.right_key)
            adjacency[edge.right_key].add(edge.left_key)
        queue: deque[tuple[str, tuple[str, ...]]] = deque(
            [(source, (source,))]
        )
        seen = {source}
        while queue:
            current, path = queue.popleft()
            if len(path) - 1 >= depth_limit:
                continue
            for neighbor in sorted(adjacency[current]):
                if neighbor in seen:
                    continue
                next_path = (*path, neighbor)
                if neighbor == target:
                    return next_path
                seen.add(neighbor)
                queue.append((neighbor, next_path))
        return ()

    def neighbors(self, lens_key: str) -> tuple[str, ...]:
        key = str(lens_key).strip().casefold()
        if key not in self._adjacency:
            raise KeyError(key)
        return tuple(sorted(self._adjacency[key]))

    def shortest_path(
        self,
        source_key: str,
        target_key: str,
        *,
        max_depth: int = 8,
    ) -> tuple[str, ...]:
        source = str(source_key).strip().casefold()
        target = str(target_key).strip().casefold()
        if source not in self._adjacency:
            raise KeyError(source)
        if target not in self._adjacency:
            raise KeyError(target)
        if source == target:
            return (source,)
        depth_limit = positive_int("max_depth", max_depth, maximum=100)
        queue: deque[tuple[str, tuple[str, ...]]] = deque([(source, (source,))])
        seen = {source}
        while queue:
            current, path = queue.popleft()
            if len(path) - 1 >= depth_limit:
                continue
            for neighbor in sorted(self._adjacency[current]):
                if neighbor in seen:
                    continue
                next_path = (*path, neighbor)
                if neighbor == target:
                    return next_path
                seen.add(neighbor)
                queue.append((neighbor, next_path))
        return ()

    @staticmethod
    def _cue_overlap(
        left: SemanticLensSpec,
        right: SemanticLensSpec,
    ) -> tuple[float, tuple[str, ...]]:
        a, b = set(left.activation_cues), set(right.activation_cues)
        if not a or not b:
            return 0.0, ()
        shared = tuple(sorted(a & b))
        if not shared:
            return 0.0, ()
        return len(shared) / len(a | b), shared

    def _build_bridge_candidates(self) -> tuple[LensBridgeCandidate, ...]:
        specs = tuple(sorted(self._specs.values(), key=lambda spec: spec.key))
        existing = {
            tuple(sorted((edge.left_key, edge.right_key)))
            for edge in self._edges
        }
        candidates: list[LensBridgeCandidate] = []
        for index, left in enumerate(specs):
            for right in specs[index + 1 :]:
                pair = tuple(sorted((left.key, right.key)))
                if pair in existing:
                    continue
                overlap, shared = self._cue_overlap(left, right)
                if overlap <= 0.0:
                    continue
                cross_family = left.family is not right.family
                role_novelty = 1.0 if left.role is not right.role else 0.25
                score = min(
                    1.0,
                    0.65 * overlap
                    + 0.20 * float(cross_family)
                    + 0.15 * role_novelty,
                )
                candidate_id = stable_id(
                    "semantic-bridge-candidate",
                    {
                        "left": left.key,
                        "right": right.key,
                        "shared": shared,
                        "score": score,
                    },
                    length=28,
                )
                candidates.append(
                    LensBridgeCandidate(
                        candidate_id=candidate_id,
                        left_key=left.key,
                        right_key=right.key,
                        left_family=left.family,
                        right_family=right.family,
                        score=score,
                        cue_overlap=overlap,
                        role_novelty=role_novelty,
                        cross_family=cross_family,
                        shared_cues=shared,
                        rationale=(
                            "Unmodeled lens bridge candidate: shared activation cues "
                            f"{', '.join(shared)} with "
                            f"{'cross-family' if cross_family else 'within-family'} "
                            "structural complementarity. Validate before adding an interaction rule."
                        ),
                    )
                )
        candidates.sort(
            key=lambda item: (
                -item.score,
                -int(item.cross_family),
                item.left_key,
                item.right_key,
            )
        )
        return tuple(candidates)

    def bridge_candidates(
        self,
        *,
        limit: int = 32,
        minimum_score: float = 0.18,
        focus_keys: Sequence[str] = (),
    ) -> tuple[LensBridgeCandidate, ...]:
        maximum = positive_int("limit", limit, maximum=10_000)
        threshold = probability("minimum_score", minimum_score)
        focus = {
            str(key).strip().casefold()
            for key in focus_keys
            if str(key).strip()
        }
        unknown_focus = focus - set(self._specs)
        if unknown_focus:
            raise KeyError(sorted(unknown_focus)[0])
        values = (
            candidate
            for candidate in self._bridge_candidates
            if candidate.score >= threshold
            and (
                not focus
                or candidate.left_key in focus
                or candidate.right_key in focus
            )
        )
        result: list[LensBridgeCandidate] = []
        for candidate in values:
            result.append(candidate)
            if len(result) >= maximum:
                break
        return tuple(result)

    @property
    def fingerprint(self) -> str:
        return self._snapshot.fingerprint
