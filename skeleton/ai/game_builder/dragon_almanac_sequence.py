"""Sequential, resumable source-processing receipts in the canonical library.

This is a bounded application workflow projection, not a network executor.
Only externally authenticated workers may submit completion receipts. Crawler
DNS/redirect/robots/terms checks and the resource governor remain mandatory.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from secrets import token_hex

from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import DragonAlmanacs, _auth
from .reviewed_knowledge import _id, _digest, _integer

STAGES = ("policy", "fetch", "extract", "analyze", "canonical_review")


@dataclass(frozen=True, slots=True)
class AlmanacClaim:
    owner: str
    source_id: str
    stage: str
    token: str
    expires_at: int
    input_digest: str
    url: str
    attempt: int


class SequentialAlmanacWorker:
    def __init__(self, almanacs: DragonAlmanacs):
        if not isinstance(almanacs, DragonAlmanacs):
            raise TypeError("canonical almanac projection required")
        self.almanacs, self.db = almanacs, almanacs.db
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS dragon_almanac_jobs (
          owner TEXT NOT NULL, source TEXT NOT NULL, stage INTEGER NOT NULL DEFAULT 0,
          state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
          token TEXT, expires INTEGER, input_digest TEXT NOT NULL, started INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(owner,source));
        CREATE TABLE IF NOT EXISTS dragon_almanac_steps (
          owner TEXT NOT NULL, source TEXT NOT NULL, stage INTEGER NOT NULL,
          body TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(owner,source,stage));
        CREATE TABLE IF NOT EXISTS dragon_almanac_archived_steps (
          owner TEXT NOT NULL, source TEXT NOT NULL, body TEXT NOT NULL,
          digest TEXT NOT NULL, archived_at INTEGER NOT NULL, PRIMARY KEY(owner,digest));
        """)
        if "started" not in {r[1] for r in self.db.execute("PRAGMA table_info(dragon_almanac_jobs)")}:
            self.db.execute("ALTER TABLE dragon_almanac_jobs ADD COLUMN started INTEGER NOT NULL DEFAULT 0")

    def seed(self, owner: str, *, authorized: bool) -> int:
        _auth(owner, authorized)
        cur = self.db.execute("""INSERT OR IGNORE INTO dragon_almanac_jobs
          (owner,source,input_digest) SELECT owner,source,digest
          FROM dragon_almanac_sources WHERE owner=?""", (owner,))
        return cur.rowcount

    def _verify_prefix(self, owner, source, stage, input_digest, url, source_digest, now):
        """Verify the complete bounded lineage before granting or advancing work.

        Digests detect corruption; they are not worker authentication. The caller
        still owns identity, network policy, rights review and resource admission.
        Older receipts retain their original digest and require no migration.
        """
        _integer(stage, "job stage", 0, len(STAGES) - 1)
        _digest(input_digest, "stage input")
        rows = self.db.execute("""SELECT stage,
          CASE WHEN length(CAST(body AS BLOB))<=32768 THEN body ELSE NULL END,digest
          FROM dragon_almanac_steps WHERE owner=? AND source=? ORDER BY stage LIMIT ?""",
          (owner, source, len(STAGES) + 1)).fetchall()
        if len(rows) != stage:
            raise ValueError("missing or extra acquisition lineage")
        expected = source_digest
        previous_time = 0
        policy_expiry = None
        for index, (stored_stage, raw, digest) in enumerate(rows):
            if not isinstance(raw, str):
                raise ValueError("acquisition receipt exceeds storage budget")
            body = json.loads(raw)
            if not isinstance(body, dict) or canonical_digest(body) != digest:
                raise ValueError("acquisition receipt integrity invalid")
            evidence = body.get("evidence")
            at = body.get("at")
            _integer(at, "receipt clock", previous_time, now)
            output = body.get("output_digest")
            _digest(output, "receipt output")
            if (stored_stage != index or body.get("stage") != STAGES[index]
                    or body.get("owner") != owner or body.get("source_id") != source
                    or body.get("input_digest") != expected
                    or body.get("training_authorized") is not False
                    or not isinstance(evidence, dict)
                    or evidence.get("url") != url
                    or evidence.get("input_digest") != expected
                    or evidence.get("output_digest") != output):
                raise ValueError("acquisition receipt lineage mismatch")
            self._validate_stage_evidence(STAGES[index], evidence, at)
            if index == 0:
                policy_expiry = evidence["expires_at"]
            elif index == 1 and at >= policy_expiry:
                raise ValueError("historical fetch occurred after policy expiry")
            expected, previous_time = output, at
        if expected != input_digest:
            raise ValueError("acquisition input differs from current source lineage")
        return previous_time

    @staticmethod
    def _validate_stage_evidence(stage, evidence, at):
        if stage == "policy":
            if (any(evidence.get(k) is not True for k in ("robots_permitted", "terms_permitted", "reference_use_permitted", "ssrf_checked"))
                    or type(evidence.get("expires_at")) is not int or not at < evidence["expires_at"] <= at + 86400):
                raise ValueError("current explicit crawler policy evidence required")
        elif stage == "fetch":
            if type(evidence.get("http_status")) is not int or evidence["http_status"] != 200 or evidence.get("redirects_rechecked") is not True:
                raise ValueError("successful checked fetch required")
            _integer(evidence.get("body_bytes"), "fetched bytes", 1, 16_000_000)
        elif stage == "extract":
            _id(evidence.get("parser_version"), "parser identity")
            _digest(evidence.get("span_map_digest"), "span map")
        elif stage == "analyze":
            if evidence.get("derived_claims_are_unreviewed") is not True:
                raise ValueError("machine inference cannot self-approve")
            _integer(evidence.get("claim_count"), "claim count", 0, 256)

    def claim(self, owner: str, *, now: int, authorized: bool, trusted_worker: bool,
              ttl: int = 120) -> AlmanacClaim | None:
        _auth(owner, authorized)
        if trusted_worker is not True:
            raise PermissionError("authenticated worker boundary required")
        _integer(now, "clock", 0, 4_102_444_800); _integer(ttl, "lease TTL", 1, 3600)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            # Exactly one active job per owner gives sequential processing.
            if self.db.execute("SELECT 1 FROM dragon_almanac_jobs WHERE owner=? AND state='leased' AND expires>?", (owner, now)).fetchone():
                self.db.execute("COMMIT")
                return None
            self.db.execute("UPDATE dragon_almanac_jobs SET state='blocked',token=NULL WHERE owner=? AND state='leased' AND expires<=? AND attempts>=3", (owner, now))
            row = self.db.execute("""SELECT j.source,j.stage,j.input_digest,j.attempts,s.body,s.digest
              FROM dragon_almanac_jobs j JOIN dragon_almanac_sources s
              ON s.owner=j.owner AND s.source=j.source
              WHERE j.owner=? AND j.attempts<3 AND
              (j.state='pending' OR (j.state='leased' AND j.expires<=?))
              ORDER BY j.stage DESC,j.source LIMIT 1""", (owner, now)).fetchone()
            if row is None:
                self.db.execute("COMMIT")
                return None
            source, stage, input_digest, attempts, raw, source_digest = row
            source_body = json.loads(raw)
            if canonical_digest(source_body) != source_digest:
                raise ValueError("discovery metadata corrupt")
            self._verify_prefix(owner, source, stage, input_digest,
                                source_body["url"], source_digest, now)
            token = token_hex(32)
            self.db.execute("UPDATE dragon_almanac_jobs SET state='leased',attempts=attempts+1,token=?,expires=?,started=? WHERE owner=? AND source=?",
                            (token, now + ttl, now, owner, source))
            self.db.execute("COMMIT")
            return AlmanacClaim(owner, source, STAGES[stage], token, now + ttl,
                                input_digest, source_body["url"], attempts + 1)
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def finish(self, claim: AlmanacClaim, *, now: int, output_digest: str,
               evidence: dict, authorized: bool, trusted_worker: bool) -> str:
        if not isinstance(claim, AlmanacClaim):
            raise TypeError("typed fenced claim required")
        _auth(claim.owner, authorized)
        if trusted_worker is not True:
            raise PermissionError("authenticated executor receipts required")
        _integer(now, "clock", 0, 4_102_444_800); _digest(output_digest, "output digest")
        if not isinstance(evidence, dict) or len(canonical_json(evidence)) > 16_384:
            raise ValueError("bounded execution evidence required")
        if evidence.get("url") != claim.url or evidence.get("input_digest") != claim.input_digest:
            raise ValueError("receipt not bound to exact source and stage input")
        if evidence.get("output_digest") != output_digest:
            raise ValueError("output evidence mismatch")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT stage,state,token,expires,input_digest,started FROM dragon_almanac_jobs WHERE owner=? AND source=?", (claim.owner, claim.source_id)).fetchone()
            if (row is None or row[1] != "leased" or row[2] != claim.token or row[3] <= now
                    or row[3] != claim.expires_at or row[4] != claim.input_digest
                    or type(row[0]) is not int or not 0 <= row[0] < len(STAGES)
                    or STAGES[row[0]] != claim.stage or now < row[5]):
                raise ValueError("expired, replayed or mismatched job claim")
            source = self.db.execute("SELECT body,digest FROM dragon_almanac_sources WHERE owner=? AND source=?", (claim.owner, claim.source_id)).fetchone()
            if not source or canonical_digest(json.loads(source[0])) != source[1] or json.loads(source[0])["url"] != claim.url:
                raise ValueError("claim URL differs from source registry")
            self._verify_prefix(claim.owner, claim.source_id, row[0], row[4],
                                claim.url, source[1], now)
            self._validate_stage_evidence(claim.stage, evidence, now)
            if claim.stage == "fetch":
                policy = self.db.execute("SELECT body,digest FROM dragon_almanac_steps WHERE owner=? AND source=? AND stage=0", (claim.owner, claim.source_id)).fetchone()
                if not policy or canonical_digest(json.loads(policy[0])) != policy[1] or json.loads(policy[0])["evidence"]["expires_at"] <= now:
                    raise ValueError("fetch policy stale or corrupt")
            elif claim.stage == "canonical_review":
                fetch = self.db.execute("SELECT body,digest FROM dragon_almanac_steps WHERE owner=? AND source=? AND stage=1", (claim.owner, claim.source_id)).fetchone()
                if not fetch or canonical_digest(json.loads(fetch[0])) != fetch[1]:
                    raise ValueError("missing or corrupt fetch lineage")
                fetched_body_digest = json.loads(fetch[0])["output_digest"]
                matches = [r for r in self.almanacs.library._rows(claim.owner)
                           if r["source_id"] == claim.source_id and r["source_url"] == claim.url
                           and r["revision_digest"] == output_digest and r["status"] == "active"
                           and "design_reference" in r["allowed_scopes"]
                           and r["source_text_digest"] == fetched_body_digest]
                if len(matches) != 1:
                    raise ValueError("current canonical reviewed admission required")
            body = {"owner": claim.owner, "source_id": claim.source_id, "stage": claim.stage,
                    "input_digest": claim.input_digest, "output_digest": output_digest,
                    "evidence": evidence, "at": now, "training_authorized": False}
            digest = canonical_digest(body)
            self.db.execute("INSERT INTO dragon_almanac_steps VALUES(?,?,?,?,?)", (claim.owner, claim.source_id, row[0], canonical_json(body), digest))
            state = "reviewed" if row[0] == len(STAGES) - 1 else "pending"
            self.db.execute("UPDATE dragon_almanac_jobs SET stage=stage+1,state=?,attempts=0,token=NULL,expires=NULL,input_digest=? WHERE owner=? AND source=?",
                            (state, output_digest, claim.owner, claim.source_id))
            self.db.execute("COMMIT")
            return digest
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def block(self, claim: AlmanacClaim, *, now: int, authorized: bool) -> bool:
        _auth(claim.owner, authorized); _integer(now, "clock", 0, 4_102_444_800)
        result = self.db.execute("UPDATE dragon_almanac_jobs SET state='blocked',token=NULL WHERE owner=? AND source=? AND token=? AND expires>?",
                                (claim.owner, claim.source_id, claim.token, now))
        return result.rowcount == 1

    def restart_blocked(self, owner: str, source_id: str, *, expected_input_digest: str,
                        now: int, authorized: bool, trusted_worker: bool) -> None:
        """Recheck policy from scratch, preserving prior completion receipts."""
        _auth(owner, authorized); _id(source_id, "source"); _digest(expected_input_digest, "expected input")
        _integer(now, "clock", 0, 4_102_444_800)
        if trusted_worker is not True:
            raise PermissionError("authenticated recovery operator required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT state,input_digest,started FROM dragon_almanac_jobs WHERE owner=? AND source=?", (owner, source_id)).fetchone()
            if row is None or row[0] != "blocked" or row[1] != expected_input_digest or row[2] > now:
                raise ValueError("recovery needs current blocked-job identity")
            steps = self.db.execute("SELECT body,digest FROM dragon_almanac_steps WHERE owner=? AND source=?", (owner, source_id)).fetchall()
            for raw, digest in steps:
                if canonical_digest(json.loads(raw)) != digest or json.loads(raw)["at"] > now:
                    raise ValueError("cannot archive corrupt or future step")
                self.db.execute("INSERT OR IGNORE INTO dragon_almanac_archived_steps VALUES(?,?,?,?,?)", (owner, source_id, raw, digest, now))
            current = self.db.execute("SELECT body,digest FROM dragon_almanac_sources WHERE owner=? AND source=?", (owner, source_id)).fetchone()
            if current is None or canonical_digest(json.loads(current[0])) != current[1]:
                raise ValueError("source registry integrity invalid")
            self.db.execute("DELETE FROM dragon_almanac_steps WHERE owner=? AND source=?", (owner, source_id))
            self.db.execute("UPDATE dragon_almanac_jobs SET stage=0,state='pending',attempts=0,token=NULL,expires=NULL,input_digest=?,started=? WHERE owner=? AND source=?", (current[1], now, owner, source_id))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def status(self, owner: str, *, authorized: bool) -> dict:
        _auth(owner, authorized)
        counts = dict(self.db.execute("SELECT state,COUNT(*) FROM dragon_almanac_jobs WHERE owner=? GROUP BY state", (owner,)).fetchall())
        return {"owner": owner, "jobs": counts, "total": sum(counts.values()),
                "network_executor_attached": False, "neural_training_executed": False}
