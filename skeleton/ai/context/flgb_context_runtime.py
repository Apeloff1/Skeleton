"""FLGB-03 deterministic context, memory, retrieval, and evidence contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS = 256
MAX_CONTEXT_ITEMS = 16_384
MAX_MEMORY_ENTRIES = 65_536
MAX_TOKEN_BUDGET = 10_000_000
MAX_GRAPH_NODES = 100_000
MAX_GRAPH_EDGES = 500_000
MAX_HOPS = 32
MAX_SCORE_PPM = 1_000_000


class ContextContractError(ValueError):
    """Fail-closed FLGB-03 contract error."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def require_id(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_ID_CHARS
        or any(ord(ch) < 32 for ch in value)
    ):
        raise ContextContractError(f"invalid {name}")
    return value


def require_digest(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ContextContractError(f"invalid {name}")
    return value


def digest_json(value: Any) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContextContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()


@dataclass(frozen=True)
class ContextItem:
    item_id: str
    kind: str
    content_digest: str
    provenance_digest: str
    token_cost: int
    priority: int = 0
    mandatory: bool = False

    def __post_init__(self) -> None:
        require_id(self.item_id, "item_id")
        require_id(self.kind, "kind")
        require_digest(self.content_digest, "content_digest")
        require_digest(self.provenance_digest, "provenance_digest")
        if not _is_int(self.token_cost) or not 0 <= self.token_cost <= MAX_TOKEN_BUDGET:
            raise ContextContractError("invalid token_cost")
        if not _is_int(self.priority) or not -1_000_000 <= self.priority <= 1_000_000:
            raise ContextContractError("invalid priority")
        if not isinstance(self.mandatory, bool):
            raise ContextContractError("mandatory must be boolean")


@dataclass(frozen=True)
class CompiledContext:
    operation_id: str
    budget_tokens: int
    selected_ids: tuple[str, ...]
    omitted_ids: tuple[str, ...]
    used_tokens: int
    source_digest: str

    def __post_init__(self) -> None:
        require_id(self.operation_id, "operation_id")
        require_digest(self.source_digest, "source_digest")
        if not _is_int(self.budget_tokens) or not 0 <= self.budget_tokens <= MAX_TOKEN_BUDGET:
            raise ContextContractError("invalid budget_tokens")
        if not _is_int(self.used_tokens) or not 0 <= self.used_tokens <= self.budget_tokens:
            raise ContextContractError("invalid used_tokens")
        if set(self.selected_ids) & set(self.omitted_ids):
            raise ContextContractError("selected and omitted context overlap")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


def compile_context(
    operation_id: str,
    items: Sequence[ContextItem],
    *,
    token_budget: int,
) -> CompiledContext:
    require_id(operation_id, "operation_id")
    if not _is_int(token_budget) or not 0 <= token_budget <= MAX_TOKEN_BUDGET:
        raise ContextContractError("invalid context token budget")
    if len(items) > MAX_CONTEXT_ITEMS:
        raise ContextContractError("context item budget exceeded")
    ids = [item.item_id for item in items]
    if len(set(ids)) != len(ids):
        raise ContextContractError("duplicate context item id")
    mandatory = sorted(
        (item for item in items if item.mandatory),
        key=lambda item: (-item.priority, item.item_id),
    )
    mandatory_cost = sum(item.token_cost for item in mandatory)
    if mandatory_cost > token_budget:
        raise ContextContractError("mandatory context exceeds token budget")
    optional = sorted(
        (item for item in items if not item.mandatory),
        key=lambda item: (-item.priority, item.token_cost, item.item_id),
    )
    selected = list(mandatory)
    used = mandatory_cost
    for item in optional:
        if used + item.token_cost <= token_budget:
            selected.append(item)
            used += item.token_cost
    selected_ids = tuple(item.item_id for item in selected)
    selected_set = set(selected_ids)
    omitted_ids = tuple(sorted(item.item_id for item in items if item.item_id not in selected_set))
    source_digest = digest_json(
        [
            {
                "item_id": item.item_id,
                "kind": item.kind,
                "content_digest": item.content_digest,
                "provenance_digest": item.provenance_digest,
                "token_cost": item.token_cost,
                "priority": item.priority,
                "mandatory": item.mandatory,
            }
            for item in sorted(items, key=lambda entry: entry.item_id)
        ]
    )
    return CompiledContext(
        operation_id,
        token_budget,
        selected_ids,
        omitted_ids,
        used,
        source_digest,
    )


@dataclass(frozen=True)
class MemoryValue:
    key: str
    value_digest: str
    provenance_digest: str
    revision: int

    def __post_init__(self) -> None:
        require_id(self.key, "memory key")
        require_digest(self.value_digest, "value_digest")
        require_digest(self.provenance_digest, "provenance_digest")
        if not _is_int(self.revision) or self.revision < 0:
            raise ContextContractError("invalid memory revision")


class WorkingMemory:
    def __init__(self, entries: Sequence[MemoryValue] = (), *, revision: int = 0) -> None:
        if len(entries) > MAX_MEMORY_ENTRIES:
            raise ContextContractError("working memory entry budget exceeded")
        if not _is_int(revision) or revision < 0:
            raise ContextContractError("invalid working memory revision")
        values: dict[str, MemoryValue] = {}
        for entry in entries:
            if not isinstance(entry, MemoryValue):
                raise ContextContractError("MemoryValue required")
            if entry.key in values:
                raise ContextContractError("duplicate working-memory key")
            values[entry.key] = entry
        self._entries = MappingProxyType(values)
        self.revision = revision

    def get(self, key: str) -> MemoryValue:
        require_id(key, "memory key")
        try:
            return self._entries[key]
        except KeyError as exc:
            raise ContextContractError("working-memory key not found") from exc

    def upsert(self, key: str, value_digest: str, provenance_digest: str) -> "WorkingMemory":
        require_id(key, "memory key")
        require_digest(value_digest, "value_digest")
        require_digest(provenance_digest, "provenance_digest")
        if key not in self._entries and len(self._entries) >= MAX_MEMORY_ENTRIES:
            raise ContextContractError("working memory entry budget exceeded")
        next_revision = self.revision + 1
        values = dict(self._entries)
        values[key] = MemoryValue(key, value_digest, provenance_digest, next_revision)
        return WorkingMemory(tuple(values.values()), revision=next_revision)

    def remove(self, key: str) -> "WorkingMemory":
        require_id(key, "memory key")
        if key not in self._entries:
            raise ContextContractError("cannot remove absent working-memory key")
        values = dict(self._entries)
        del values[key]
        return WorkingMemory(tuple(values.values()), revision=self.revision + 1)

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "revision": self.revision,
                "entries": [
                    entry.__dict__
                    for entry in sorted(self._entries.values(), key=lambda value: value.key)
                ],
            }
        )


@dataclass(frozen=True)
class Episode:
    episode_id: str
    sequence: int
    event_digest: str
    provenance_digest: str
    prior_episode_digest: str | None = None

    def __post_init__(self) -> None:
        require_id(self.episode_id, "episode_id")
        if not _is_int(self.sequence) or self.sequence < 0:
            raise ContextContractError("invalid episode sequence")
        require_digest(self.event_digest, "event_digest")
        require_digest(self.provenance_digest, "provenance_digest")
        if self.prior_episode_digest is not None:
            require_digest(self.prior_episode_digest, "prior_episode_digest")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


class EpisodicMemory:
    def __init__(self, episodes: Sequence[Episode] = ()) -> None:
        if len(episodes) > MAX_MEMORY_ENTRIES:
            raise ContextContractError("episodic memory budget exceeded")
        prior: str | None = None
        ids: set[str] = set()
        for index, episode in enumerate(episodes):
            if not isinstance(episode, Episode) or episode.sequence != index:
                raise ContextContractError("episodic memory sequence drift")
            if episode.episode_id in ids:
                raise ContextContractError("duplicate episode id")
            if episode.prior_episode_digest != prior:
                raise ContextContractError("episode chain drift")
            ids.add(episode.episode_id)
            prior = episode.digest
        self.episodes = tuple(episodes)

    def append(self, episode_id: str, event_digest: str, provenance_digest: str) -> "EpisodicMemory":
        prior = self.episodes[-1].digest if self.episodes else None
        episode = Episode(
            episode_id,
            len(self.episodes),
            event_digest,
            provenance_digest,
            prior,
        )
        return EpisodicMemory(self.episodes + (episode,))

    @property
    def digest(self) -> str:
        return digest_json([episode.digest for episode in self.episodes])


@dataclass(frozen=True)
class SemanticFact:
    fact_id: str
    subject: str
    predicate: str
    object_digest: str
    evidence_digest: str
    confidence_ppm: int
    revision: int = 0

    def __post_init__(self) -> None:
        require_id(self.fact_id, "fact_id")
        require_id(self.subject, "subject")
        require_id(self.predicate, "predicate")
        require_digest(self.object_digest, "object_digest")
        require_digest(self.evidence_digest, "evidence_digest")
        if not _is_int(self.confidence_ppm) or not 0 <= self.confidence_ppm <= MAX_SCORE_PPM:
            raise ContextContractError("confidence_ppm out of bounds")
        if not _is_int(self.revision) or self.revision < 0:
            raise ContextContractError("invalid semantic revision")


class SemanticMemory:
    def __init__(self, facts: Sequence[SemanticFact] = ()) -> None:
        if len(facts) > MAX_MEMORY_ENTRIES:
            raise ContextContractError("semantic memory budget exceeded")
        by_id: dict[str, SemanticFact] = {}
        for fact in facts:
            if not isinstance(fact, SemanticFact):
                raise ContextContractError("SemanticFact required")
            if fact.fact_id in by_id:
                raise ContextContractError("duplicate semantic fact")
            by_id[fact.fact_id] = fact
        self._facts = MappingProxyType(by_id)

    def put(self, fact: SemanticFact) -> "SemanticMemory":
        if not isinstance(fact, SemanticFact):
            raise ContextContractError("SemanticFact required")
        prior = self._facts.get(fact.fact_id)
        if prior is not None and fact.revision != prior.revision + 1:
            raise ContextContractError("semantic revision must advance exactly once")
        if prior is None and fact.revision != 0:
            raise ContextContractError("new semantic fact must start at revision zero")
        values = dict(self._facts)
        values[fact.fact_id] = fact
        return SemanticMemory(tuple(values.values()))

    def query(self, subject: str, predicate: str | None = None) -> tuple[SemanticFact, ...]:
        require_id(subject, "subject")
        if predicate is not None:
            require_id(predicate, "predicate")
        return tuple(
            sorted(
                (
                    fact
                    for fact in self._facts.values()
                    if fact.subject == subject and (predicate is None or fact.predicate == predicate)
                ),
                key=lambda fact: (-fact.confidence_ppm, fact.fact_id),
            )
        )


@dataclass(frozen=True)
class ProjectMemorySnapshot:
    project_id: str
    revision: int
    state_digest: str
    canon_digest: str
    provenance_digest: str
    parent_digest: str | None = None

    def __post_init__(self) -> None:
        require_id(self.project_id, "project_id")
        if not _is_int(self.revision) or self.revision < 0:
            raise ContextContractError("invalid project revision")
        require_digest(self.state_digest, "state_digest")
        require_digest(self.canon_digest, "canon_digest")
        require_digest(self.provenance_digest, "provenance_digest")
        if self.parent_digest is not None:
            require_digest(self.parent_digest, "parent_digest")
        if self.revision == 0 and self.parent_digest is not None:
            raise ContextContractError("genesis project memory cannot have parent")
        if self.revision > 0 and self.parent_digest is None:
            raise ContextContractError("non-genesis project memory requires parent")

    @property
    def digest(self) -> str:
        return digest_json(self.__dict__)


@dataclass(frozen=True)
class RetrievalCandidate:
    candidate_id: str
    source: str
    content_digest: str
    provenance_digest: str
    lexical_ppm: int
    semantic_ppm: int
    freshness_ppm: int = MAX_SCORE_PPM

    def __post_init__(self) -> None:
        require_id(self.candidate_id, "candidate_id")
        require_id(self.source, "source")
        require_digest(self.content_digest, "content_digest")
        require_digest(self.provenance_digest, "provenance_digest")
        for name in ("lexical_ppm", "semantic_ppm", "freshness_ppm"):
            value = getattr(self, name)
            if not _is_int(value) or not 0 <= value <= MAX_SCORE_PPM:
                raise ContextContractError(f"{name} out of bounds")


def hybrid_rank(
    candidates: Sequence[RetrievalCandidate],
    *,
    lexical_weight: int = 4,
    semantic_weight: int = 5,
    freshness_weight: int = 1,
    limit: int = 20,
) -> tuple[RetrievalCandidate, ...]:
    weights = (lexical_weight, semantic_weight, freshness_weight)
    if any(not _is_int(weight) or weight < 0 for weight in weights) or sum(weights) <= 0:
        raise ContextContractError("invalid retrieval weights")
    if not _is_int(limit) or not 1 <= limit <= 10_000:
        raise ContextContractError("invalid retrieval limit")
    ids = [candidate.candidate_id for candidate in candidates]
    if len(set(ids)) != len(ids):
        raise ContextContractError("duplicate retrieval candidate")
    def score(candidate: RetrievalCandidate) -> int:
        return (
            candidate.lexical_ppm * lexical_weight
            + candidate.semantic_ppm * semantic_weight
            + candidate.freshness_ppm * freshness_weight
        )
    return tuple(
        sorted(candidates, key=lambda item: (-score(item), item.candidate_id))[:limit]
    )


@dataclass(frozen=True)
class CodeHit:
    path: str
    symbol: str
    content_digest: str
    provenance_digest: str
    start_line: int
    end_line: int
    score_ppm: int

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path or self.path.startswith("/") or ".." in self.path.split("/"):
            raise ContextContractError("invalid repository-relative path")
        require_id(self.symbol, "symbol")
        require_digest(self.content_digest, "content_digest")
        require_digest(self.provenance_digest, "provenance_digest")
        if not _is_int(self.start_line) or not _is_int(self.end_line) or not 1 <= self.start_line <= self.end_line:
            raise ContextContractError("invalid code line range")
        if not _is_int(self.score_ppm) or not 0 <= self.score_ppm <= MAX_SCORE_PPM:
            raise ContextContractError("invalid code score")


def rank_code_hits(hits: Sequence[CodeHit], *, limit: int = 20) -> tuple[CodeHit, ...]:
    if not _is_int(limit) or not 1 <= limit <= 10_000:
        raise ContextContractError("invalid code retrieval limit")
    identities = [(hit.path, hit.symbol, hit.start_line, hit.end_line) for hit in hits]
    if len(set(identities)) != len(identities):
        raise ContextContractError("duplicate code retrieval hit")
    return tuple(sorted(hits, key=lambda hit: (-hit.score_ppm, hit.path, hit.start_line, hit.symbol))[:limit])


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    relation: str

    def __post_init__(self) -> None:
        require_id(self.source, "graph source")
        require_id(self.target, "graph target")
        require_id(self.relation, "graph relation")
        if self.source == self.target:
            raise ContextContractError("self graph edge forbidden")


def graph_retrieve(
    seeds: Sequence[str],
    edges: Sequence[GraphEdge],
    *,
    max_hops: int,
    max_results: int,
) -> tuple[str, ...]:
    if not seeds or len(seeds) > MAX_GRAPH_NODES:
        raise ContextContractError("graph seed set out of bounds")
    if len(edges) > MAX_GRAPH_EDGES:
        raise ContextContractError("graph edge budget exceeded")
    if not _is_int(max_hops) or not 0 <= max_hops <= MAX_HOPS:
        raise ContextContractError("invalid max_hops")
    if not _is_int(max_results) or not 1 <= max_results <= MAX_GRAPH_NODES:
        raise ContextContractError("invalid max_results")
    seed_ids = tuple(require_id(seed, "graph seed") for seed in seeds)
    if len(set(seed_ids)) != len(seed_ids):
        raise ContextContractError("duplicate graph seed")
    adjacency: dict[str, set[str]] = {}
    seen_edges: set[tuple[str, str, str]] = set()
    for edge in edges:
        key = (edge.source, edge.target, edge.relation)
        if key in seen_edges:
            raise ContextContractError("duplicate graph edge")
        seen_edges.add(key)
        adjacency.setdefault(edge.source, set()).add(edge.target)
    visited = set(seed_ids)
    frontier = sorted(seed_ids)
    results = list(frontier)
    for _ in range(max_hops):
        next_frontier: list[str] = []
        for node in frontier:
            for target in sorted(adjacency.get(node, ())):
                if target not in visited:
                    visited.add(target)
                    next_frontier.append(target)
                    results.append(target)
                    if len(results) >= max_results:
                        return tuple(results)
        frontier = sorted(next_frontier)
        if not frontier:
            break
    return tuple(results[:max_results])


@dataclass(frozen=True)
class TemporalRecord:
    record_id: str
    content_digest: str
    provenance_digest: str
    valid_from: int
    valid_to: int | None = None

    def __post_init__(self) -> None:
        require_id(self.record_id, "record_id")
        require_digest(self.content_digest, "content_digest")
        require_digest(self.provenance_digest, "provenance_digest")
        if not _is_int(self.valid_from) or self.valid_from < 0:
            raise ContextContractError("invalid valid_from")
        if self.valid_to is not None:
            if not _is_int(self.valid_to) or self.valid_to <= self.valid_from:
                raise ContextContractError("invalid valid_to")

    def active_at(self, sequence: int) -> bool:
        if not _is_int(sequence) or sequence < 0:
            raise ContextContractError("invalid temporal query sequence")
        return self.valid_from <= sequence and (self.valid_to is None or sequence < self.valid_to)


def temporal_retrieve(records: Sequence[TemporalRecord], sequence: int) -> tuple[TemporalRecord, ...]:
    ids = [record.record_id for record in records]
    if len(set(ids)) != len(ids):
        raise ContextContractError("duplicate temporal record")
    return tuple(sorted((record for record in records if record.active_at(sequence)), key=lambda record: record.record_id))


@dataclass(frozen=True)
class Claim:
    claim_id: str
    statement_digest: str
    provenance_digest: str

    def __post_init__(self) -> None:
        require_id(self.claim_id, "claim_id")
        require_digest(self.statement_digest, "statement_digest")
        require_digest(self.provenance_digest, "provenance_digest")


@dataclass(frozen=True)
class EvidenceLink:
    evidence_id: str
    claim_id: str
    evidence_digest: str
    relation: str
    strength_ppm: int

    def __post_init__(self) -> None:
        require_id(self.evidence_id, "evidence_id")
        require_id(self.claim_id, "claim_id")
        require_digest(self.evidence_digest, "evidence_digest")
        if self.relation not in {"supports", "contradicts", "qualifies"}:
            raise ContextContractError("invalid evidence relation")
        if not _is_int(self.strength_ppm) or not 0 <= self.strength_ppm <= MAX_SCORE_PPM:
            raise ContextContractError("invalid evidence strength")


class ClaimEvidenceGraph:
    def __init__(self, claims: Sequence[Claim], evidence: Sequence[EvidenceLink]) -> None:
        if len(claims) > MAX_GRAPH_NODES or len(evidence) > MAX_GRAPH_EDGES:
            raise ContextContractError("claim/evidence graph exceeds budget")
        claim_map = {claim.claim_id: claim for claim in claims}
        if len(claim_map) != len(claims):
            raise ContextContractError("duplicate claim id")
        evidence_ids: set[str] = set()
        for link in evidence:
            if link.evidence_id in evidence_ids:
                raise ContextContractError("duplicate evidence id")
            if link.claim_id not in claim_map:
                raise ContextContractError("orphan evidence link")
            evidence_ids.add(link.evidence_id)
        self.claims = tuple(sorted(claims, key=lambda claim: claim.claim_id))
        self.evidence = tuple(sorted(evidence, key=lambda link: link.evidence_id))

    def evidence_for(self, claim_id: str) -> tuple[EvidenceLink, ...]:
        require_id(claim_id, "claim_id")
        if claim_id not in {claim.claim_id for claim in self.claims}:
            raise ContextContractError("unknown claim")
        return tuple(link for link in self.evidence if link.claim_id == claim_id)

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "claims": [claim.__dict__ for claim in self.claims],
                "evidence": [link.__dict__ for link in self.evidence],
            }
        )


@dataclass(frozen=True)
class Contradiction:
    contradiction_id: str
    left_claim_id: str
    right_claim_id: str
    evidence_digest: str
    status: str = "open"
    resolution_digest: str | None = None

    def __post_init__(self) -> None:
        require_id(self.contradiction_id, "contradiction_id")
        require_id(self.left_claim_id, "left_claim_id")
        require_id(self.right_claim_id, "right_claim_id")
        if self.left_claim_id == self.right_claim_id:
            raise ContextContractError("contradiction requires distinct claims")
        require_digest(self.evidence_digest, "evidence_digest")
        if self.status not in {"open", "resolved", "deferred"}:
            raise ContextContractError("invalid contradiction status")
        if self.status == "resolved":
            if self.resolution_digest is None:
                raise ContextContractError("resolved contradiction requires resolution")
            require_digest(self.resolution_digest, "resolution_digest")
        elif self.resolution_digest is not None:
            raise ContextContractError("unresolved contradiction cannot carry resolution")

    def resolve(self, resolution_digest: str) -> "Contradiction":
        if self.status == "resolved":
            raise ContextContractError("contradiction already resolved")
        return Contradiction(
            self.contradiction_id,
            self.left_claim_id,
            self.right_claim_id,
            self.evidence_digest,
            "resolved",
            require_digest(resolution_digest, "resolution_digest"),
        )


@dataclass(frozen=True)
class CompressionReceipt:
    operation_id: str
    source_digests: tuple[str, ...]
    source_tokens: int
    summary_digest: str
    summary_tokens: int
    preserved_mandatory_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        require_id(self.operation_id, "operation_id")
        if not self.source_digests:
            raise ContextContractError("compression requires sources")
        for source in self.source_digests:
            require_digest(source, "source_digest")
        if len(set(self.source_digests)) != len(self.source_digests):
            raise ContextContractError("duplicate compression source")
        require_digest(self.summary_digest, "summary_digest")
        if not _is_int(self.source_tokens) or not 1 <= self.source_tokens <= MAX_TOKEN_BUDGET:
            raise ContextContractError("invalid source_tokens")
        if not _is_int(self.summary_tokens) or not 0 <= self.summary_tokens < self.source_tokens:
            raise ContextContractError("compression must reduce token count")
        if len(set(self.preserved_mandatory_ids)) != len(self.preserved_mandatory_ids):
            raise ContextContractError("duplicate preserved mandatory id")
        for item_id in self.preserved_mandatory_ids:
            require_id(item_id, "mandatory item id")

    @property
    def savings_tokens(self) -> int:
        return self.source_tokens - self.summary_tokens

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "operation_id": self.operation_id,
                "source_digests": list(self.source_digests),
                "source_tokens": self.source_tokens,
                "summary_digest": self.summary_digest,
                "summary_tokens": self.summary_tokens,
                "preserved_mandatory_ids": list(self.preserved_mandatory_ids),
            }
        )
