"""Owner-isolated, incremental inverted index for Dragon discovery *metadata*.

Only catalog headings, repository names and canonical URL tokens are indexed.
No source text, transcript, model weights, rights decisions or fetch privileges
are written. Recheck source and raw receipt digests before indexing. The index
is an advisory projection and can be rebuilt without changing source custody.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from urllib.parse import urlsplit

from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import DragonAlmanacs, _auth
from .dragon_source_catalog import canonical_source_url
from .reviewed_knowledge import _id, _integer


TERMS = re.compile(r"[a-z0-9]+")
MAX_TERMS_PER_SOURCE = 256
MAX_RECEIPTS_PER_SOURCE = 128
MAX_STORED_BYTES = 32_768


def facet_terms(value: str) -> frozenset[str]:
    if not isinstance(value, str):
        raise ValueError("metadata text required")
    return frozenset(TERMS.findall(value.casefold().replace("_", " ")))


def _checked_origin(origin: object) -> str:
    if not isinstance(origin, dict):
        raise ValueError("invalid discovery origin")
    texts = []
    headers = origin.get("headers", [])
    if not isinstance(headers, (list, tuple)) or len(headers) > 16:
        raise ValueError("invalid heading ancestry")
    for heading in headers:
        if (not isinstance(heading, str) or len(heading) > 2048
                or any(ord(c) < 32 or ord(c) == 127 for c in heading)):
            raise ValueError("invalid heading content")
        texts.append(heading)
    for key in ("repository", "catalog_id"):
        value = origin.get(key)
        if value is not None:
            if not isinstance(value, str) or len(value) > 256:
                raise ValueError("invalid catalog identity")
            texts.append(value)
    return " ".join(texts)


class DiscoveryFacetIndex:
    """Bounded paged indexing. Explicitly not a crawler or review authority."""

    def __init__(self, almanacs: DragonAlmanacs):
        if not isinstance(almanacs, DragonAlmanacs):
            raise TypeError("canonical DragonAlmanacs required")
        self.db = almanacs.db
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_discovery_facet_records (
          owner TEXT NOT NULL, source TEXT NOT NULL,
          source_digest TEXT NOT NULL, receipts_digest TEXT NOT NULL,
          token_digest TEXT NOT NULL, PRIMARY KEY(owner,source))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_discovery_facet_terms (
          owner TEXT NOT NULL, token TEXT NOT NULL, source TEXT NOT NULL,
          PRIMARY KEY(owner,token,source))""")
        self.db.execute("""CREATE INDEX IF NOT EXISTS dragon_facet_by_source
          ON dragon_discovery_facet_terms(owner,source)""")
        # An original catalog import need not contain supplemental receipts.
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_almanac_supplement_receipts_v2 (
          owner TEXT NOT NULL, origin_source TEXT NOT NULL,
          normalized_source TEXT NOT NULL, supplement_digest TEXT NOT NULL,
          body TEXT NOT NULL, digest TEXT NOT NULL,
          PRIMARY KEY(owner,origin_source,supplement_digest))""")
        self.db.execute("""CREATE INDEX IF NOT EXISTS dragon_facet_receipts
          ON dragon_almanac_supplement_receipts_v2(owner,normalized_source)""")
        # Receipt changes would otherwise leave an apparently-current source
        # digest beside stale indexed heading terms. Mark projections dirty at
        # the SQL boundary, independent of which importer writes the receipt.
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_discovery_facet_dirty (
          owner TEXT NOT NULL, source TEXT NOT NULL,
          PRIMARY KEY(owner,source))""")
        for statement in (
            """CREATE TRIGGER IF NOT EXISTS dragon_facet_receipt_insert
               AFTER INSERT ON dragon_almanac_supplement_receipts_v2
               BEGIN
                 INSERT OR IGNORE INTO dragon_discovery_facet_dirty
                   VALUES(NEW.owner,NEW.normalized_source);
               END""",
            """CREATE TRIGGER IF NOT EXISTS dragon_facet_receipt_delete
               AFTER DELETE ON dragon_almanac_supplement_receipts_v2
               BEGIN
                 INSERT OR IGNORE INTO dragon_discovery_facet_dirty
                   VALUES(OLD.owner,OLD.normalized_source);
               END""",
            """CREATE TRIGGER IF NOT EXISTS dragon_facet_receipt_update
               AFTER UPDATE ON dragon_almanac_supplement_receipts_v2
               BEGIN
                 INSERT OR IGNORE INTO dragon_discovery_facet_dirty
                   VALUES(OLD.owner,OLD.normalized_source);
                 INSERT OR IGNORE INTO dragon_discovery_facet_dirty
                   VALUES(NEW.owner,NEW.normalized_source);
               END""",
        ):
            # execute(), unlike executescript(), does not silently commit a
            # caller-owned transaction when installing a missing trigger.
            self.db.execute(statement)

    def _metadata_tokens(self, owner: str, source_id: str,
                         source_raw: str, source_digest: str) -> tuple[tuple[str,...],str]:
        if not isinstance(source_raw, str) or len(source_raw) > MAX_STORED_BYTES:
            raise ValueError("source record exceeds metadata budget")
        source = json.loads(source_raw)
        url = source.get("url")
        if (canonical_digest(source) != source_digest
                or not isinstance(url, str) or url != canonical_source_url(url)
                or source.get("source_id") != source_id
                or source_id != "source-" + sha256(url.encode("utf-8")).hexdigest()):
            raise ValueError("corrupt canonical discovery source")
        texts = [urlsplit(url).hostname or "", urlsplit(url).path]
        discoveries = source.get("discoveries", [])
        if not isinstance(discoveries, list) or len(discoveries) > 256:
            raise ValueError("invalid source discovery metadata")
        texts.extend(_checked_origin(o) for o in discoveries)
        receipts = self.db.execute(
            """SELECT origin_source,supplement_digest,body,digest
               FROM dragon_almanac_supplement_receipts_v2
               WHERE owner=? AND normalized_source=?
               ORDER BY origin_source,supplement_digest LIMIT ?""",
            (owner, source_id, MAX_RECEIPTS_PER_SOURCE + 1),
        ).fetchall()
        if len(receipts) > MAX_RECEIPTS_PER_SOURCE:
            raise ValueError("too many raw source receipts")
        lineage = []
        for origin_id, supplement_digest, receipt_raw, digest in receipts:
            if not isinstance(receipt_raw, str) or len(receipt_raw) > 262_144:
                raise ValueError("oversized raw source receipt")
            body = json.loads(receipt_raw)
            candidate = body.get("candidate")
            if (canonical_digest(body) != digest
                    or not isinstance(candidate, dict)
                    or body.get("normalized_source_id") != source_id
                    or body.get("normalized_url") != url
                    or body.get("supplement_digest") != supplement_digest
                    or body.get("authority") != "unreviewed_discovery_only"
                    or candidate.get("source_id") != origin_id
                    or origin_id != "source-" + sha256(
                        candidate.get("url", "").encode("utf-8")).hexdigest()
                    or canonical_source_url(candidate.get("url")) != url):
                raise ValueError("corrupt supplemental source receipt")
            origins = candidate.get("discoveries", [])
            if not isinstance(origins, list) or len(origins) > 256:
                raise ValueError("invalid raw source origins")
            texts.extend(_checked_origin(o) for o in origins)
            lineage.append((origin_id, supplement_digest, digest))
        tokens = tuple(sorted(facet_terms(" ".join(texts))))
        if len(tokens) > MAX_TERMS_PER_SOURCE:
            raise ValueError("excessive discovery facet tokens")
        return tokens, canonical_digest(lineage)

    def refresh(self, owner: str, *, authorized: bool, limit: int = 500,
                after_source: str | None = None) -> dict:
        """Index one deterministic source-ID page; return a resumable cursor."""
        _auth(owner, authorized)
        _integer(limit, "facet index page size", 1, 1000)
        if after_source is not None:
            _id(after_source, "after_source")
        cursor = after_source or ""
        rows = self.db.execute(
            """SELECT s.source,s.body,s.digest FROM dragon_almanac_sources s
               WHERE s.owner=? AND s.source>? ORDER BY s.source LIMIT ?""",
            (owner, cursor, limit + 1),
        ).fetchall()
        changed = 0
        self.db.execute("BEGIN IMMEDIATE")
        try:
            for source_id, raw, digest in rows[:limit]:
                tokens, receipts_digest = self._metadata_tokens(
                    owner, source_id, raw, digest)
                token_digest = canonical_digest(tokens)
                previous = self.db.execute(
                    """SELECT source_digest,receipts_digest,token_digest
                       FROM dragon_discovery_facet_records WHERE owner=? AND source=?""",
                    (owner, source_id),
                ).fetchone()
                actual = tuple(t[0] for t in self.db.execute(
                    """SELECT token FROM dragon_discovery_facet_terms
                       WHERE owner=? AND source=? ORDER BY token""",
                    (owner, source_id),
                ))
                if (previous == (digest, receipts_digest, token_digest)
                        and actual == tokens):
                    self.db.execute(
                        "DELETE FROM dragon_discovery_facet_dirty WHERE owner=? AND source=?",
                        (owner, source_id))
                    continue
                self.db.execute(
                    "DELETE FROM dragon_discovery_facet_terms WHERE owner=? AND source=?",
                    (owner, source_id),
                )
                self.db.executemany(
                    """INSERT INTO dragon_discovery_facet_terms(owner,token,source)
                       VALUES(?,?,?)""",
                    ((owner, token, source_id) for token in tokens),
                )
                self.db.execute(
                    """INSERT INTO dragon_discovery_facet_records
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(owner,source) DO UPDATE SET
                       source_digest=excluded.source_digest,
                       receipts_digest=excluded.receipts_digest,
                       token_digest=excluded.token_digest""",
                    (owner, source_id, digest, receipts_digest, token_digest),
                )
                self.db.execute(
                    "DELETE FROM dragon_discovery_facet_dirty WHERE owner=? AND source=?",
                    (owner, source_id))
                changed += 1
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        next_cursor = rows[limit-1][0] if len(rows) > limit else None
        return {
            "owner": owner, "processed": min(len(rows),limit),
            "updated": changed, "next_source": next_cursor,
            "metadata_only": True, "crawler_authorized": False,
            "training_authorized": False,
        }

    def audit(self, owner: str, *, authorized: bool, limit: int = 200,
              after_source: str | None = None) -> dict:
        """Check index postings against canonical source and raw receipt lineage.

        Stale snapshots are disclosed, but malformed or forged postings are
        rejected. This is a bounded verification read, not a source refresh or
        a model-quality benchmark.
        """
        _auth(owner, authorized)
        _integer(limit, "audit page size", 1, 1000)
        if after_source is not None:
            _id(after_source, "audit cursor")
        rows = self.db.execute(
            """SELECT source,source_digest,receipts_digest,token_digest
               FROM dragon_discovery_facet_records
               WHERE owner=? AND source>? ORDER BY source LIMIT ?""",
            (owner, after_source or "", limit + 1),
        ).fetchall()
        stale_sources = []
        verified = 0
        for sid, claimed_source, claimed_receipts, claimed_tokens in rows[:limit]:
            stored = self.db.execute(
                "SELECT body,digest FROM dragon_almanac_sources WHERE owner=? AND source=?",
                (owner, sid),
            ).fetchone()
            if stored is None:
                stale_sources.append(sid)
                continue
            tokens, current_receipts = self._metadata_tokens(
                owner, sid, stored[0], stored[1])
            actual = tuple(t[0] for t in self.db.execute(
                """SELECT token FROM dragon_discovery_facet_terms
                   WHERE owner=? AND source=? ORDER BY token""",
                (owner, sid),
            ))
            if actual != tokens and (
                    claimed_source == stored[1] and
                    claimed_receipts == current_receipts):
                raise ValueError("facet postings are inconsistent with current evidence")
            if (claimed_source != stored[1] or
                    claimed_receipts != current_receipts or
                    claimed_tokens != canonical_digest(tokens) or actual != tokens):
                stale_sources.append(sid)
            else:
                verified += 1
        return {
            "owner": owner,
            "audited": min(len(rows), limit),
            "current": verified,
            "stale": len(stale_sources),
            "stale_source_ids": stale_sources,
            "next_source": rows[limit - 1][0] if len(rows) > limit else None,
            "independent_content_verified": False,
            "index_is_advisory": True,
            "training_authorized": False,
        }

    def health(self, owner: str, *, authorized: bool) -> dict:
        """Counts materialization gaps and source-digest drift, not knowledge truth."""
        _auth(owner, authorized)
        total = self.db.execute(
            """SELECT COUNT(*) FROM dragon_almanac_sources s
               JOIN dragon_almanac_jobs j ON j.owner=s.owner AND j.source=s.source
               WHERE s.owner=? AND j.stage=0 AND j.state IN ('pending','blocked')""",
            (owner,),
        ).fetchone()[0]
        covered = self.db.execute(
            """SELECT COUNT(*) FROM dragon_almanac_sources s
               JOIN dragon_almanac_jobs j ON j.owner=s.owner AND j.source=s.source
               JOIN dragon_discovery_facet_records i
                 ON i.owner=s.owner AND i.source=s.source AND i.source_digest=s.digest
               LEFT JOIN dragon_discovery_facet_dirty d
                 ON d.owner=s.owner AND d.source=s.source
               WHERE s.owner=? AND j.stage=0 AND j.state IN ('pending','blocked')
               AND d.source IS NULL
               AND j.input_digest=s.digest""",
            (owner,),
        ).fetchone()[0]
        stale_job_inputs = self.db.execute(
            """SELECT COUNT(*) FROM dragon_almanac_sources s
               JOIN dragon_almanac_jobs j ON j.owner=s.owner AND j.source=s.source
               WHERE s.owner=? AND j.stage=0 AND j.state IN ('pending','blocked')
               AND j.input_digest!=s.digest""", (owner,)
        ).fetchone()[0]
        return {
            "owner": owner, "policy_stage_sources": total,
            "stale_job_inputs": stale_job_inputs,
            "source_digest_current_indexed": covered,
            "unindexed_or_changed": total-covered,
            "coverage_complete": covered == total,
            "provenance_may_require_refresh": True,
            "training_authorized": False,
        }

    def matching_rows(self, owner: str, tokens: frozenset[str], *,
                      authorized: bool, limit: int, topic: str | None = None,
                      weights: dict[str,int] | None = None
                      ) -> tuple[list[tuple],dict]:
        """Use the inverted index across the entire materialized corpus.

        Every returned hit is still validated in the canonical scout. Index
        health explicitly discloses partial coverage.
        """
        _auth(owner, authorized)
        _integer(limit, "indexed scout limit", 1, 10_001)
        if topic is not None:
            _id(topic, "mission topic")
            if not self.db.execute(
                    "SELECT 1 FROM dragon_almanac_topics WHERE owner=? AND topic=?",
                    (owner, topic)).fetchone():
                raise ValueError("unknown owner topic")
        if not tokens or len(tokens) > 256 or any(
                not isinstance(t, str) or not TERMS.fullmatch(t) for t in tokens):
            raise ValueError("bounded token query required")
        if weights is None:
            weights = {token: 1 for token in tokens}
        if (not isinstance(weights, dict) or set(weights) != tokens
                or any(type(v) is not int or not 1 <= v <= 1_000_000
                       for v in weights.values())):
            raise ValueError("invalid bounded mission term weights")
        mission_terms = sorted(weights.items())
        bound_terms = ",".join("(?,?)" for _ in mission_terms)
        condition = (
            "AND EXISTS(SELECT 1 FROM dragon_almanac_members m WHERE "
            "m.owner=s.owner AND m.source=s.source AND m.topic=?)"
            if topic is not None else ""
        )
        sql = (
            "WITH mission_terms(token,weight) AS (VALUES " + bound_terms + ") "
            "SELECT s.source,s.body,s.digest,j.stage,j.state,j.input_digest "
            "FROM mission_terms q "
            "JOIN dragon_discovery_facet_terms t ON t.token=q.token "
            "JOIN dragon_discovery_facet_records i "
            "ON i.owner=t.owner AND i.source=t.source "
            "JOIN dragon_almanac_sources s ON s.owner=i.owner "
            "AND s.source=i.source AND s.digest=i.source_digest "
            "JOIN dragon_almanac_jobs j ON j.owner=s.owner AND j.source=s.source "
            "LEFT JOIN dragon_discovery_facet_dirty d "
            "ON d.owner=s.owner AND d.source=s.source "
            "WHERE s.owner=? AND d.source IS NULL AND j.stage=0 "
            "AND j.state IN ('pending','blocked') AND j.input_digest=s.digest "
            + condition + " GROUP BY s.source "
            "ORDER BY SUM(q.weight) DESC,s.source LIMIT ?"
        )
        params = [v for term,weight in mission_terms for v in (term,weight)]
        params.append(owner)
        if topic is not None:
            params.append(topic)
        params.append(limit)
        return self.db.execute(sql, params).fetchall(), self.health(
            owner, authorized=True)
