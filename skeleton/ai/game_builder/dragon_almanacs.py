"""Topic almanacs and project-learning projections in the canonical library.

No second knowledge authority: source notes remain in ReviewedKnowledgeStore;
Wiki/HOAG, rights and model training retain their existing admission gates.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import islice
import json
from pathlib import Path
from typing import Iterable

from .contracts import canonical_digest, canonical_json
from .dragon_source_catalog import canonical_source_url
from .reviewed_knowledge import ReviewedKnowledgeStore, _id, _digest, _integer, _text


def _auth(owner: str, authorized: bool) -> None:
    if authorized is not True:
        raise PermissionError("authenticated library owner required")
    _id(owner, "owner")


def _bounded(rows: Iterable, maximum: int) -> tuple:
    result = tuple(islice(rows, maximum + 1))
    if len(result) > maximum:
        raise ValueError("input budget exceeded")
    return result


def read_source_registry(directory: str | Path) -> dict:
    """Verify shipped shards before returning discovery metadata."""
    root = Path(directory)
    raw = (root / "manifest.json").read_bytes()
    if len(raw) > 1_000_000:
        raise ValueError("manifest size exceeded")
    manifest = json.loads(raw)
    shards = manifest.pop("shards")
    if not isinstance(shards, list) or len(shards) > 1000:
        raise ValueError("shard budget exceeded")
    sources = []
    paths = set()
    for shard in shards:
        name = shard["path"]
        if not isinstance(name, str) or Path(name).name != name or name in paths:
            raise ValueError("invalid or duplicate shard path")
        paths.add(name)
        with (root / name).open("rb") as stream:
            data = stream.read(2_000_001)
        if len(data) > 2_000_000 or sha256(data).hexdigest() != shard["sha256"]:
            raise ValueError("source shard integrity invalid")
        rows = [json.loads(line) for line in data.splitlines() if line]
        if len(rows) != shard["count"] or len(sources) + len(rows) > 100_000:
            raise ValueError("source count mismatch or budget exceeded")
        sources.extend(rows)
    digest = manifest.pop("catalog_digest")
    body = {**manifest, "sources": sources}
    if canonical_digest(body) != digest or len(sources) != body["unique_urls"]:
        raise ValueError("catalog integrity invalid")
    return {**body, "catalog_digest": digest}


@dataclass(frozen=True, slots=True)
class ProjectLearning:
    project_id: str
    artifact_digest: str
    topic_id: str
    stage: str
    kind: str
    statement: str
    method: str
    limitations: str
    evidence_digests: tuple[str, ...]
    parent_learning: tuple[str, ...] = ()
    source_refs: tuple[tuple[str, str, str], ...] = ()

    def __post_init__(self):
        _id(self.project_id, "project"); _id(self.topic_id, "topic")
        _digest(self.artifact_digest, "artifact")
        if self.stage not in {"research", "steppingstone", "product", "field_evaluation"}:
            raise ValueError("unknown learning stage")
        if self.kind not in {"ai_hypothesis", "measured_experiment", "negative_result", "source_synthesis"}:
            raise ValueError("unknown learning kind")
        for key in ("statement", "method", "limitations"):
            _text(getattr(self, key), key, 2048)
        for key in ("evidence_digests", "parent_learning", "source_refs"):
            values = getattr(self, key)
            if not isinstance(values, tuple) or len(values) > 32 or len(set(values)) != len(values):
                raise ValueError("bounded unique immutable learning references required")
        if not self.evidence_digests:
            raise ValueError("learning needs captured evidence, including hypotheses")
        for value in self.evidence_digests + self.parent_learning:
            _digest(value, "learning evidence")
        for ref in self.source_refs:
            if not isinstance(ref, tuple) or len(ref) != 3:
                raise ValueError("source/revision/note reference required")
            _id(ref[0], "source"); _digest(ref[1], "revision"); _id(ref[2], "note")


class DragonAlmanacs:
    """Owner-scoped derived indexes. Each heading path has its own almanac."""

    def __init__(self, library: ReviewedKnowledgeStore):
        if not isinstance(library, ReviewedKnowledgeStore):
            raise TypeError("canonical ReviewedKnowledgeStore required")
        self.library, self.db = library, library.db
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS dragon_almanac_topics (
          owner TEXT NOT NULL, topic TEXT NOT NULL, parent TEXT, path TEXT NOT NULL,
          PRIMARY KEY(owner,topic), UNIQUE(owner,path));
        CREATE TABLE IF NOT EXISTS dragon_almanac_sources (
          owner TEXT NOT NULL, source TEXT NOT NULL, body TEXT NOT NULL,
          digest TEXT NOT NULL, PRIMARY KEY(owner,source));
        CREATE TABLE IF NOT EXISTS dragon_almanac_members (
          owner TEXT NOT NULL, topic TEXT NOT NULL, source TEXT NOT NULL,
          PRIMARY KEY(owner,topic,source));
        CREATE TABLE IF NOT EXISTS dragon_almanac_learning (
          owner TEXT NOT NULL, digest TEXT NOT NULL, topic TEXT NOT NULL,
          body TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY(owner,digest));
        CREATE INDEX IF NOT EXISTS dragon_almanac_learning_topic
          ON dragon_almanac_learning(owner,topic,at);
        CREATE TABLE IF NOT EXISTS dragon_almanac_entities (
          owner TEXT NOT NULL, kind TEXT NOT NULL, provider TEXT NOT NULL,
          entity_id TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL,
          digest TEXT NOT NULL, PRIMARY KEY(owner,kind,provider,entity_id,revision));
        """)

    def ensure_topic(self, owner: str, path: Iterable[str], *, authorized: bool) -> str:
        _auth(owner, authorized)
        if isinstance(path, (str, bytes)):
            raise ValueError("topic path must be a sequence of headers")
        parts = _bounded(path, 16)
        if not parts:
            raise ValueError("nonempty topic path required")
        for part in parts:
            _text(part, "topic header", 160)
        parent = None
        count = self.db.execute("SELECT COUNT(*) FROM dragon_almanac_topics WHERE owner=?", (owner,)).fetchone()[0]
        if count + len(parts) > 100_000:
            raise ValueError("owner topic capacity exceeded")
        # Stable identity includes the full path, avoiding same-name collisions.
        for i in range(1, len(parts) + 1):
            prefix = parts[:i]
            topic = "topic-" + canonical_digest(prefix)
            self.db.execute("INSERT OR IGNORE INTO dragon_almanac_topics VALUES(?,?,?,?)",
                            (owner, topic, parent, canonical_json(prefix)))
            parent = topic
        return topic

    def ingest_sources(self, owner: str, registry: dict, *, authorized: bool) -> dict:
        _auth(owner, authorized)
        rows = _bounded(registry["sources"], 100_000)
        catalog_ids = {r["catalog_id"] for r in registry["catalogs"]}
        body = {k: v for k, v in registry.items() if k != "catalog_digest"}
        if canonical_digest(body) != registry["catalog_digest"]:
            raise ValueError("registry digest mismatch")
        inserted = 0
        self.db.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                url = canonical_source_url(row["url"])
                source = "source-" + sha256(url.encode()).hexdigest()
                if source != row["source_id"] or url != row["url"]:
                    raise ValueError("source identity invalid")
                old = self.db.execute("SELECT body,digest FROM dragon_almanac_sources WHERE owner=? AND source=?",
                                      (owner, source)).fetchone()
                if old and canonical_digest(json.loads(old[0])) != old[1]:
                    raise ValueError("source metadata integrity invalid")
                merged = json.loads(old[0]) if old else {**row, "discoveries": []}
                for origin in _bounded(row["discoveries"], 256):
                    if origin["catalog_id"] not in catalog_ids:
                        raise ValueError("unknown discovery catalog")
                    _integer(origin["line"], "catalog line", 1, 1_000_000)
                    topic = self.ensure_topic(owner, ("Sources", origin["catalog_id"], *origin["headers"]), authorized=True)
                    # Every ancestor receives membership, not only the leaf.
                    while topic:
                        self.db.execute("INSERT OR IGNORE INTO dragon_almanac_members VALUES(?,?,?)", (owner, topic, source))
                        topic = self.db.execute("SELECT parent FROM dragon_almanac_topics WHERE owner=? AND topic=?", (owner, topic)).fetchone()[0]
                    if origin not in merged["discoveries"]:
                        merged["discoveries"].append(origin)
                merged["discoveries"].sort(key=lambda x: (x["catalog_id"], x["line"]))
                self.db.execute("INSERT INTO dragon_almanac_sources VALUES(?,?,?,?) ON CONFLICT(owner,source) DO UPDATE SET body=excluded.body,digest=excluded.digest",
                    (owner, source, canonical_json(merged), canonical_digest(merged)))
                inserted += old is None
            count = self.db.execute("SELECT COUNT(*) FROM dragon_almanac_sources WHERE owner=?", (owner,)).fetchone()[0]
            if count > 100_000:
                raise ValueError("owner discovery capacity exceeded")
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {"new_sources": inserted, "total_sources": count, "approved_knowledge_added": 0}

    def record_learning(self, owner: str, learning: ProjectLearning, *, now: int,
                        authorized: bool) -> str:
        _auth(owner, authorized)
        _integer(now, "capture time", 0, 4_102_444_800)
        if not isinstance(learning, ProjectLearning):
            raise TypeError("typed project learning required")
        if not self.db.execute("SELECT 1 FROM dragon_almanac_topics WHERE owner=? AND topic=?", (owner, learning.topic_id)).fetchone():
            raise ValueError("unknown topic")
        for parent in learning.parent_learning:
            row = self.db.execute("SELECT body,at FROM dragon_almanac_learning WHERE owner=? AND digest=?", (owner, parent)).fetchone()
            if row is None or row[1] > now or canonical_digest(json.loads(row[0])) != parent:
                raise ValueError("missing, future or corrupt learning parent")
        # Exact source references must already exist in the canonical store.
        current = {r["source_id"]: r for r in self.library._rows(owner)}
        for source, revision, note in learning.source_refs:
            row = current.get(source)
            if (not row or row["status"] != "active" or "design_reference" not in row["allowed_scopes"] or row["revision_digest"] != revision
                    or note not in {n["note"]["note_id"] for n in row["notes"]}):
                raise ValueError("learning cites stale or missing canonical evidence")
        if self.db.execute("SELECT COUNT(*) FROM dragon_almanac_learning WHERE owner=?", (owner,)).fetchone()[0] >= 100_000:
            raise ValueError("owner learning capacity exceeded")
        body = {"schema": "skeleton.dragon.project_learning.v1", "owner": owner,
                **asdict(learning), "at": now, "epistemic_state": "unreviewed",
                "independent_external_support_added": 0, "training_authorized": False,
                "memory_promotion_authorized": False, "release_authorized": False}
        digest = canonical_digest(body)
        self.db.execute("INSERT OR IGNORE INTO dragon_almanac_learning VALUES(?,?,?,?,?)",
                        (owner, digest, learning.topic_id, canonical_json(body), now))
        return digest

    def upsert_entity(self, owner: str, *, kind: str, provider: str, entity_id: str,
                      metadata: dict, authorized: bool) -> str:
        """Version game/video identities without collapsing editions or sequels."""
        _auth(owner, authorized)
        if kind not in {"game", "video", "edition", "studio", "platform", "patent"}:
            raise ValueError("unknown catalog entity kind")
        _id(provider, "provider"); _text(entity_id, "provider entity ID", 256)
        if not isinstance(metadata, dict) or len(canonical_json(metadata)) > 16_384:
            raise ValueError("bounded metadata object required")
        _text(metadata.get("title"), "entity title", 300)
        canonical_source_url(metadata.get("source_url"))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.db.execute("SELECT revision,body,digest FROM dragon_almanac_entities WHERE owner=? AND kind=? AND provider=? AND entity_id=? ORDER BY revision DESC LIMIT 1",
                                  (owner, kind, provider, entity_id)).fetchone()
            if old and canonical_digest(json.loads(old[1])) != old[2]:
                raise ValueError("entity lineage integrity invalid")
            if old and json.loads(old[1])["metadata"] == metadata:
                self.db.execute("COMMIT")
                return old[2]
            if (old and old[0] >= 255) or self.db.execute("SELECT COUNT(*) FROM dragon_almanac_entities WHERE owner=?", (owner,)).fetchone()[0] >= 100_000:
                raise ValueError("entity revision budget exceeded")
            body = {"owner": owner, "kind": kind, "provider": provider, "entity_id": entity_id,
                    "revision": old[0] + 1 if old else 0, "parent_digest": old[2] if old else None,
                    "metadata": metadata, "identity_resolution": "provider_scoped_not_cross_provider_verified"}
            digest = canonical_digest(body)
            self.db.execute("INSERT INTO dragon_almanac_entities VALUES(?,?,?,?,?,?,?)",
                            (owner, kind, provider, entity_id, body["revision"], canonical_json(body), digest))
            self.db.execute("COMMIT")
            return digest
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def learning_view(self, owner: str, topic: str, *, authorized: bool, limit: int = 100) -> dict:
        """Recheck inherited source dependencies before displaying AI findings."""
        _auth(owner, authorized); _id(topic, "topic"); _integer(limit, "limit", 1, 1000)
        current = {r["source_id"]: r for r in self.library._rows(owner)}
        memo = {}

        def visit(digest, depth=0):
            if digest in memo:
                return memo[digest]
            if depth > 32 or len(memo) >= 4096:
                raise ValueError("learning ancestry traversal budget exceeded")
            row = self.db.execute("SELECT body FROM dragon_almanac_learning WHERE owner=? AND digest=?", (owner, digest)).fetchone()
            if row is None:
                raise ValueError("missing learning ancestor")
            body = json.loads(row[0])
            if canonical_digest(body) != digest or body["owner"] != owner:
                raise ValueError("learning lineage integrity invalid")
            stale = []
            for source, revision, note in body["source_refs"]:
                evidence = current.get(source)
                if (not evidence or evidence["status"] != "active" or "design_reference" not in evidence["allowed_scopes"] or evidence["revision_digest"] != revision
                        or note not in {n["note"]["note_id"] for n in evidence["notes"]}):
                    stale.append(source)
            for parent in body["parent_learning"]:
                stale.extend(visit(parent, depth+1)["stale_source_dependencies"])
            result = {**body, "learning_digest": digest, "stale_source_dependencies": sorted(set(stale)),
                      "current_source_lineage": not stale, "empirical_truth_established": False}
            memo[digest] = result
            return result

        rows = self.db.execute("SELECT digest FROM dragon_almanac_learning WHERE owner=? AND topic=? ORDER BY at,digest LIMIT ?", (owner, topic, limit)).fetchall()
        return {"owner": owner, "topic": topic, "findings": [visit(row[0]) for row in rows],
                "memory_promotion_authorized": False, "training_authorized": False}

    def entities(self, owner: str, kind: str, *, authorized: bool, limit: int = 100, offset: int = 0) -> dict:
        _auth(owner, authorized); _integer(limit, "limit", 1, 1000); _integer(offset, "offset", 0, 100_000)
        if kind not in {"game", "video", "edition", "studio", "platform", "patent"}:
            raise ValueError("unknown entity kind")
        rows = self.db.execute("""SELECT e.body,e.digest FROM dragon_almanac_entities e
          WHERE e.owner=? AND e.kind=? AND e.revision=(SELECT MAX(x.revision)
          FROM dragon_almanac_entities x WHERE x.owner=e.owner AND x.kind=e.kind
          AND x.provider=e.provider AND x.entity_id=e.entity_id)
          ORDER BY e.provider,e.entity_id LIMIT ? OFFSET ?""", (owner, kind, limit, offset)).fetchall()
        entries = []
        for raw, digest in rows:
            body = json.loads(raw)
            if canonical_digest(body) != digest or body["owner"] != owner or body["kind"] != kind:
                raise ValueError("entity integrity invalid")
            entries.append({**body, "digest": digest})
        return {"entities": entries, "offset": offset, "catalog_complete": False,
                "worldwide_denominator": "unknown", "identity_resolution_required": True}

    def report(self, owner: str, *, authorized: bool, limit: int = 100, offset: int = 0) -> dict:
        _auth(owner, authorized)
        _integer(limit, "report limit", 1, 1000); _integer(offset, "report offset", 0, 100_000)
        topics = self.db.execute("SELECT topic,path FROM dragon_almanac_topics WHERE owner=? ORDER BY path LIMIT ? OFFSET ?", (owner, limit, offset)).fetchall()
        result = []
        for topic, path in topics:
            sources = self.db.execute("SELECT COUNT(*) FROM dragon_almanac_members WHERE owner=? AND topic=?", (owner, topic)).fetchone()[0]
            learning = self.db.execute("SELECT COUNT(*) FROM dragon_almanac_learning WHERE owner=? AND topic=?", (owner, topic)).fetchone()[0]
            result.append({"topic_id": topic, "headers": json.loads(path), "discovered_sources": sources,
                           "machine_learning_records": learning, "scope": "derived_research_index"})
        return {"owner": owner, "almanacs": result, "offset": offset,
                "total_almanacs": self.db.execute("SELECT COUNT(*) FROM dragon_almanac_topics WHERE owner=?", (owner,)).fetchone()[0],
                "catalog_complete": False, "coverage_denominator": "unknown",
                "training_authorized": False, "release_authorized": False}
