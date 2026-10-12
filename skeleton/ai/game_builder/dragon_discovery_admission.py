"""Fail-closed admission of Dragon's *discovered* source supplements.

This bridge makes the catalog-expansion evidence operational without treating a
found hyperlink as a fetch grant, a rights grant, an approved fact or a training
sample. No network access is performed here. Source-line identities and Git
identities are preserved as *claims in discovery evidence*, not attested facts.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import DragonAlmanacs
from .dragon_almanac_sequence import SequentialAlmanacWorker
from .dragon_source_catalog import canonical_source_url


SCHEMA = "skeleton.dragon.source_discovery_supplement.v1"
STATUS = "partial_discovery_only_not_ingested_into_canonical_queue"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
MAX_SUPPLEMENTS = 32
MAX_CANDIDATES = 50_000
MAX_BYTES = 8_000_000


def _supplement(path: str | Path) -> tuple[str, dict]:
    file = Path(path)
    if not file.is_file() or file.suffix != ".json":
        raise ValueError("a JSON discovery supplement file is required")
    with file.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("supplement exceeds byte budget")
    doc = json.loads(raw)
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA or doc.get("status") != STATUS:
        raise ValueError("unreviewed discovery supplement required")
    root = Path(__file__).resolve().parents[3]
    try:
        evidence_path = file.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("supplement must belong to the checked-out repository") from exc
    if not evidence_path.startswith("docs/ai/evidence/dragon-source-expansion-"):
        raise ValueError("supplement path is outside the discovery evidence lane")
    return evidence_path, doc


def validate_discovery_chain(registry: dict, named_documents: list[tuple[str, dict]]) -> dict:
    """Validate the full, consecutive evidence chain before *any* DB write.

    The supplements are a non-authoritative expansion of the pinned baseline,
    not an additional catalog of verified sources.
    """
    if not 1 <= len(named_documents) <= MAX_SUPPLEMENTS:
        raise ValueError("bounded nonempty supplement chain required")
    source_rows = registry["sources"]
    baseline = {row["url"] for row in source_rows}
    baseline_size = registry["unique_urls"]
    if (len(baseline) != baseline_size
            or baseline_size != len(source_rows)
            or canonical_digest({k: v for k, v in registry.items()
                                 if k != "catalog_digest"}) != registry["catalog_digest"]):
        raise ValueError("canonical baseline invalid")
    existing = set(baseline)
    seen_paths = []
    collected: dict[str, dict] = {}
    for name, doc in named_documents:
        if name in seen_paths or not isinstance(name, str) or len(name) > 4096:
            raise ValueError("duplicate or invalid supplement path")
        if (doc.get("schema") != SCHEMA or doc.get("status") != STATUS
                or doc.get("baseline_registry_digest") != registry["catalog_digest"]
                or doc.get("requested_total_urls") != baseline_size * 10):
            raise ValueError("supplement baseline or target mismatch")
        parents = doc.get("parents", [])
        if "parent_supplement" in doc:
            parents = [doc["parent_supplement"]]
        if not isinstance(parents, list) or parents != seen_paths:
            raise ValueError("supplement chain is missing, reordered or forked")
        candidates, catalogs, counts = doc.get("candidates"), doc.get("catalogs"), doc.get("counts")
        if (not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES
                or not isinstance(catalogs, list) or not isinstance(counts, dict)):
            raise ValueError("invalid supplement structure")
        new_count = counts.get("new_candidate_urls")
        if type(new_count) is not int or new_count != len(candidates):
            raise ValueError("supplement count differs from entries")
        previous = counts.get("previous_provisional_total_urls")
        if previous is None and "previous_new_candidate_urls" in counts:
            previous = baseline_size + counts["previous_new_candidate_urls"]
        if previous is None:
            previous = doc.get("baseline_urls")
        if type(previous) is not int or previous != len(existing):
            raise ValueError("nonconsecutive discovery totals")
        known_sources = set()
        for catalog in catalogs:
            if not isinstance(catalog, dict) or not REPO.fullmatch(catalog.get("repository", "")):
                raise ValueError("invalid catalog repository identity")
            if "commit_sha" in catalog:
                if not SHA40.fullmatch(catalog["commit_sha"]) or not SHA40.fullmatch(catalog.get("readme_blob_sha", "")):
                    raise ValueError("invalid pinned Git identity")
                known_sources.add((catalog["repository"], catalog["commit_sha"], catalog["readme_blob_sha"]))
            else:
                if not SHA40.fullmatch(catalog.get("git_blob_sha", "")):
                    raise ValueError("invalid catalog blob")
                known_sources.add((catalog["url"], catalog["git_blob_sha"]))
        for row in candidates:
            if not isinstance(row, dict):
                raise ValueError("invalid candidate")
            url = canonical_source_url(row["url"])
            if url != row["url"] or url in existing:
                raise ValueError("duplicate, noncanonical or baseline URL")
            sid = "source-" + sha256(url.encode("utf-8")).hexdigest()
            if row.get("source_id") != sid:
                raise ValueError("source ID does not bind URL")
            if (row.get("availability") != "not_checked"
                    or row.get("rights") != "not_assessed"
                    or row.get("independence") != "not_assessed"
                    or row.get("training_authorized") is not False
                    or row.get("canonical_admission") is not False):
                raise ValueError("discovery cannot confer use or training authority")
            if not isinstance(row.get("discoveries"), list) or not row["discoveries"]:
                raise ValueError("each source needs discovery lineage")
            repositories = set()
            for origin in row["discoveries"]:
                if not isinstance(origin, dict):
                    raise ValueError("invalid discovery origin")
                if "repository" in origin:
                    key = (origin.get("repository"), origin.get("commit_sha"), origin.get("readme_blob_sha"))
                    if key not in known_sources or origin.get("exact_url") != url:
                        raise ValueError("discovery not tied to pinned repository")
                    repositories.add(key[0])
                else:
                    key = (origin.get("catalog_url"), origin.get("catalog_blob"))
                    if key not in known_sources or canonical_source_url(origin.get("exact_link", "")) != url:
                        raise ValueError("discovery not tied to pinned catalog")
                    if (type(origin.get("line")) is not int or not 1 <= origin["line"] <= 1_000_000
                            or not isinstance(origin.get("headers"), list)
                            or not origin["headers"] or len(origin["headers"]) > 16):
                        raise ValueError("invalid catalog line or headers")
                    repositories.add(next(c["repository"] for c in catalogs
                                          if c.get("url") == key[0] and c.get("git_blob_sha") == key[1]))
            if len(repositories) > 32:
                raise ValueError("too many claimed discoveries per URL")
            collected[url] = {"source_id": sid, "url": url,
                              "host": urlsplit(url).hostname,
                              "kind": "video_candidate" if urlsplit(url).hostname in
                                  {"www.youtube.com", "youtube.com", "youtu.be", "vimeo.com", "www.vimeo.com"}
                                  else "web_candidate",
                              "availability": "not_checked", "rights": "not_assessed",
                              "independence": "not_assessed", "training_authorized": False,
                              "discoveries": [],
                              "provisional_discovery": True}
            existing.add(url)
        if counts.get("provisional_total_urls") != len(existing):
            raise ValueError("provisional total inconsistent with distinct URLs")
        seen_paths.append(name)
    return {"baseline": baseline_size, "new": len(collected),
            "total_discovered": len(existing), "sources": collected}


class DragonDiscoveryAdmission:
    """Owner-isolated metadata-only ingress to the canonical sequential queue."""

    def __init__(self, almanacs: DragonAlmanacs):
        if not isinstance(almanacs, DragonAlmanacs):
            raise TypeError("DragonAlmanacs required")
        self.almanacs = almanacs
        self.db = almanacs.db
        self.worker = SequentialAlmanacWorker(almanacs)
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_almanac_supplement_receipts (
            owner TEXT NOT NULL, source TEXT NOT NULL,
            supplement_digest TEXT NOT NULL, body TEXT NOT NULL,
            digest TEXT NOT NULL,
            PRIMARY KEY (owner, source, supplement_digest))""")

    def import_chain(self, owner: str, registry: dict,
                     named_documents: list[tuple[str, dict]], *, authorized: bool) -> dict:
        if not isinstance(owner, str) or not 1 <= len(owner) <= 128 or authorized is not True:
            raise PermissionError("authenticated owner required")
        parsed = validate_discovery_chain(registry, named_documents)
        if len(parsed["sources"]) + registry["unique_urls"] > 100_000:
            raise ValueError("canonical source budget exceeded")
        inserted = receipts = 0
        self.db.execute("BEGIN IMMEDIATE")
        try:
            for name, doc in named_documents:
                supplement_digest = canonical_digest(doc)
                for item in doc["candidates"]:
                    sid = item["source_id"]
                    canonical = parsed["sources"][item["url"]]
                    old = self.db.execute(
                        "SELECT body,digest FROM dragon_almanac_sources WHERE owner=? AND source=?",
                        (owner, sid)).fetchone()
                    if old and canonical_digest(json.loads(old[0])) != old[1]:
                        raise ValueError("existing source metadata is corrupt")
                    if old is None:
                        body = canonical_json(canonical)
                        self.db.execute("INSERT INTO dragon_almanac_sources VALUES (?,?,?,?)",
                                        (owner, sid, body, canonical_digest(canonical)))
                        inserted += 1
                    claimed = {"evidence_path": name, "candidate": item,
                               "supplement_digest": supplement_digest,
                               "authority": "unreviewed_discovery_only"}
                    raw = canonical_json(claimed)
                    digest = canonical_digest(claimed)
                    previous = self.db.execute(
                        """SELECT digest FROM dragon_almanac_supplement_receipts
                           WHERE owner=? AND source=? AND supplement_digest=?""",
                        (owner, sid, supplement_digest)).fetchone()
                    if previous and previous[0] != digest:
                        raise ValueError("conflicting supplemental receipt")
                    if previous is None:
                        self.db.execute(
                            "INSERT INTO dragon_almanac_supplement_receipts VALUES(?,?,?,?,?)",
                            (owner, sid, supplement_digest, raw, digest))
                        receipts += 1
                    for origin in item["discoveries"]:
                        repo = origin.get("repository")
                        if repo is None:
                            repo = next(c["repository"] for c in doc["catalogs"]
                                        if c.get("url") == origin["catalog_url"]
                                        and c["git_blob_sha"] == origin["catalog_blob"])
                        topic = self.almanacs.ensure_topic(
                            owner, ("Sources", "Provisional", repo), authorized=True)
                        while topic:
                            self.db.execute(
                                "INSERT OR IGNORE INTO dragon_almanac_members VALUES(?,?,?)",
                                (owner, topic, sid))
                            topic = self.db.execute(
                                "SELECT parent FROM dragon_almanac_topics WHERE owner=? AND topic=?",
                                (owner, topic)).fetchone()[0]
            queued = self.worker.seed(owner, authorized=True)
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {"new_discovery_sources": inserted, "new_provenance_receipts": receipts,
                "new_policy_stage_jobs": queued, "total_discovered_urls": parsed["total_discovered"],
                "approved_sources": 0, "training_authorized": False,
                "status": "policy_review_required_before_any_network_fetch"}


def import_supplement_files(almanacs: DragonAlmanacs, owner: str, registry: dict,
                            paths: list[str | Path], *, authorized: bool) -> dict:
    return DragonDiscoveryAdmission(almanacs).import_chain(
        owner, registry, [_supplement(path) for path in paths], authorized=authorized)
