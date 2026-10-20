"""Durable, replay-verifiable quality evidence journal with project/source CAS.

SQLite is a host-selected local authority for the audit log only. It does not
grant model, editor, legal or production-release authority.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from .production_quality import QualityGateError, _digest
from .production_deep_gates import _sha

_SCHEMA = "game.quality_history.v1"
_GENESIS = "0" * 64
_MAX_REPORT_BYTES = 4_000_000


def _encode(report: Mapping) -> str:
    try:
        result = json.dumps(report, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise QualityGateError("quality report must be canonical JSON") from exc
    if len(result.encode()) > _MAX_REPORT_BYTES:
        raise QualityGateError("quality report exceeds storage limit")
    return result


class QualityHistoryStore:
    """Append-only source-bound evidence; caller supplies authorized local path."""

    def __init__(self, path: Path):
        if not isinstance(path, Path) or not path.parent.is_dir():
            raise QualityGateError("quality journal requires host-owned existing directory")
        self.path = path
        self.db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS quality_evidence(
              project_id TEXT NOT NULL,
              generation INTEGER NOT NULL CHECK(generation > 0),
              source_sha256 TEXT NOT NULL,
              previous_sha256 TEXT NOT NULL,
              receipt_sha256 TEXT NOT NULL,
              report_json TEXT NOT NULL,
              PRIMARY KEY(project_id, generation)
            )
        """)
        self.db.execute("CREATE INDEX IF NOT EXISTS quality_source_idx ON quality_evidence(project_id,source_sha256)")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS quality_operator_review(
              project_id TEXT NOT NULL,
              generation INTEGER NOT NULL CHECK(generation > 0),
              report_head_sha256 TEXT NOT NULL,
              reviewer_id TEXT NOT NULL,
              decision TEXT NOT NULL,
              reason_sha256 TEXT NOT NULL,
              previous_sha256 TEXT NOT NULL,
              receipt_sha256 TEXT NOT NULL,
              PRIMARY KEY(project_id, generation)
            )
        """)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        self.db.close()

    @staticmethod
    def _project(key: str) -> str:
        if (type(key) is not str or not 1 <= len(key) <= 128 or
                not all(c.isalnum() or c in "._-" for c in key) or
                key.startswith(".")):
            raise QualityGateError("quality evidence requires exact canonical project id")
        return key

    def _rows(self, project: str) -> list[tuple]:
        return self.db.execute(
            "SELECT generation,source_sha256,previous_sha256,receipt_sha256,report_json "
            "FROM quality_evidence WHERE project_id=? ORDER BY generation", (project,)
        ).fetchall()

    @staticmethod
    def _verify(project: str, rows: list[tuple], *, expected_head: str | None = None) -> dict:
        prev = _GENESIS
        source = None
        for offset, (gen, sha, parent, receipt, raw) in enumerate(rows, 1):
            if (gen != offset or parent != prev or
                    (source is not None and source != sha)):
                raise QualityGateError("journal generation/chain/source was modified")
            _sha(sha, "history source")
            _sha(receipt, "history receipt")
            obj = json.loads(raw)
            if not isinstance(obj, dict) or obj.get("source_digest") != sha:
                raise QualityGateError("quality journal report source changed")
            if obj.get("schema") not in (
                    "game.candidate.deep_quality.v1",
                    "game.candidate.frontier_quality.v1",
            ):
                raise QualityGateError("wrong report authority schema")
            if obj.get("release_certified") is not False:
                raise QualityGateError("quality review cannot manufacture production approval")
            expected_gates = (
                "world", "canon", "assets", "replay", "performance", "rights",
                "traceability", "quests", "accessibility", "controls",
                "resources", "session", "package",
            )
            if obj["schema"] == "game.candidate.frontier_quality.v1":
                expected_gates += (
                    "lineage", "continuity", "routes", "physics", "lod",
                    "localization", "comparison",
                )
            gates = obj.get("gates")
            if (type(gates) is not list or len(gates) != len(expected_gates) or
                    tuple(g.get("name") for g in gates if type(g) is dict) != expected_gates):
                raise QualityGateError("journal requires its canonical complete gate ledger")
            merged_findings = []
            for gate in gates:
                if (type(gate.get("passed")) is not bool or
                        type(gate.get("findings")) is not list or
                        type(gate.get("evidence_digest")) is not str or
                        len(gate["evidence_digest"]) != 64 or
                        gate["passed"] is not (not gate["findings"])):
                    raise QualityGateError("individual source gate status is malformed")
                merged_findings.extend(gate["findings"])
            if obj.get("findings") != merged_findings:
                raise QualityGateError("journal findings differ from component evidence")
            if obj.get("evidence_digest") != _digest(gates):
                raise QualityGateError("reported gates and evidence digest conflict")
            if type(obj.get("candidate_passed")) is not bool or (
                    obj["candidate_passed"] is not (not merged_findings)):
                raise QualityGateError("quality reviewer status differs from gate outcomes")
            if _encode(obj) != raw:
                raise QualityGateError("noncanonical quality journal record")
            actual = _digest({"schema": _SCHEMA, "project_id": project,
                              "generation": gen, "source_sha256": sha,
                              "previous_sha256": prev, "report_sha256": sha256(raw.encode()).hexdigest()})
            if actual != receipt:
                raise QualityGateError("quality record hash chain was modified")
            source, prev = sha, actual
        if expected_head is not None and prev != _sha(expected_head, "external audit anchor"):
            raise QualityGateError("journal head does not match external pinned anchor")
        return {"project_id": project, "generation": len(rows), "source_sha256": source,
                "head": prev, "candidate_only": True}

    def inspect(self, project_id: str, *, expected_head: str | None = None) -> dict:
        project = self._project(project_id)
        report = self._verify(project, self._rows(project), expected_head=expected_head)
        return {"schema": _SCHEMA, **report}

    def append(self, project_id: str, report: Mapping, *,
               expected_generation: int, expected_head: str) -> dict:
        project = self._project(project_id)
        if (type(expected_generation) is not int or not 0 <= expected_generation < 100000 or
                type(report) is not dict):
            raise QualityGateError("quality journal requires exact expected generation and report")
        _sha(expected_head, "expected journal head")
        raw = _encode(report)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            current = self._verify(project, self._rows(project))
            if (current["generation"] != expected_generation or
                    current["head"] != expected_head or
                    current["source_sha256"] not in (None, report.get("source_digest"))):
                raise QualityGateError("stale or foreign-source quality update")
            source = _sha(report.get("source_digest"), "quality report source")
            # Pre-validate the entire new record with the same independent reader.
            generation = expected_generation + 1
            receipt = _digest({
                "schema": _SCHEMA, "project_id": project, "generation": generation,
                "source_sha256": source, "previous_sha256": expected_head,
                "report_sha256": sha256(raw.encode()).hexdigest(),
            })
            proposed = (generation, source, expected_head, receipt, raw)
            self._verify(project, self._rows(project) + [proposed])
            self.db.execute(
                "INSERT INTO quality_evidence VALUES(?,?,?,?,?,?)",
                (project, generation, source, expected_head, receipt, raw)
            )
            self.db.execute("COMMIT")
            return {"schema": _SCHEMA, "project_id": project,
                    "generation": generation, "source_sha256": source,
                    "head": receipt, "candidate_only": True}
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def history(self, project_id: str, *, limit: int = 64) -> dict:
        if type(limit) is not int or not 1 <= limit <= 256:
            raise QualityGateError("history query must be bounded")
        project = self._project(project_id)
        rows = self._rows(project)
        proof = self._verify(project, rows)
        return {**proof, "schema": _SCHEMA, "entries": [
            {"generation": row[0], "source_sha256": row[1],
             "previous_sha256": row[2], "receipt_sha256": row[3],
             "report_sha256": sha256(row[4].encode()).hexdigest()}
            for row in rows[-limit:]
        ]}


    def _review_rows(self, project: str) -> list[tuple]:
        return self.db.execute(
            "SELECT generation,report_head_sha256,reviewer_id,decision,"
            "reason_sha256,previous_sha256,receipt_sha256 "
            "FROM quality_operator_review WHERE project_id=? ORDER BY generation",
            (project,),
        ).fetchall()

    @staticmethod
    def _verify_reviews(project: str, rows: list[tuple]) -> dict:
        parent = _GENESIS
        for index, row in enumerate(rows, 1):
            gen, report_head, actor, decision, reason, prev, receipt = row
            if gen != index or prev != parent:
                raise QualityGateError("operator review has rollback or missing generation")
            for label, digest in (("review head", report_head), ("review reason", reason), ("review receipt", receipt)):
                _sha(digest, label)
            if (type(actor) is not str or not 3 <= len(actor) <= 128 or
                    decision not in ("request_changes", "accept_candidate", "reject_candidate")):
                raise QualityGateError("operator decision actor or state corrupted")
            payload = {"schema": "game.quality_operator_review.v1",
                       "project_id": project, "generation": gen,
                       "report_head_sha256": report_head, "reviewer_id": actor,
                       "decision": decision, "reason_sha256": reason,
                       "previous_sha256": prev, "production_approved": False}
            if receipt != _digest(payload):
                raise QualityGateError("operator review hash receipt forged")
            parent = receipt
        return {"schema": "game.quality_operator_review.v1",
                "project_id": project, "generation": len(rows),
                "head": parent, "production_approved": False}

    def inspect_reviews(self, project_id: str, *, limit: int = 64) -> dict:
        if type(limit) is not int or not 1 <= limit <= 256:
            raise QualityGateError("bounded operator review query required")
        project = self._project(project_id)
        rows = self._review_rows(project)
        proof = self._verify_reviews(project, rows)
        # Also verify the source audit ledger, never silently trust an orphan review.
        evidence = self._verify(project, self._rows(project))
        known_heads = {row[3] for row in self._rows(project)}
        if any(row[1] not in known_heads for row in rows):
            raise QualityGateError("operator review points at absent evidence")
        return {**proof, "evidence_generation": evidence["generation"],
                "entries": [
                    {"generation": row[0], "report_head_sha256": row[1],
                     "reviewer_id": row[2], "decision": row[3],
                     "reason_sha256": row[4], "previous_sha256": row[5],
                     "receipt_sha256": row[6]}
                    for row in rows[-limit:]
                ]}

    def review(self, project_id: str, *, reviewer_id: str, decision: str,
               reason_sha256: str, report_head_sha256: str,
               expected_generation: int, expected_head: str) -> dict:
        """Host-authorized evidence review with durable optimistic concurrency.

        This records candidate-level reviewer decisions ONLY. It is not an
        approval of copyright, trained weights or a production release.
        """
        project = self._project(project_id)
        if (type(reviewer_id) is not str or not 3 <= len(reviewer_id) <= 128 or
                not reviewer_id.isascii() or
                any(not (ch.isalnum() or ch in "._-") for ch in reviewer_id) or
                decision not in ("request_changes", "accept_candidate", "reject_candidate") or
                type(expected_generation) is not int or not 0 <= expected_generation < 100000):
            raise QualityGateError("authorized reviewer identity and decision required")
        for name, value in (("review reason", reason_sha256), ("report head", report_head_sha256),
                            ("expected review head", expected_head)):
            _sha(value, name)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            evidence_rows = self._rows(project)
            evidence = self._verify(project, evidence_rows)
            if (not evidence_rows or evidence["head"] != report_head_sha256):
                raise QualityGateError("review must reference exact latest committed audit")
            current = self._verify_reviews(project, self._review_rows(project))
            if current["generation"] != expected_generation or current["head"] != expected_head:
                raise QualityGateError("operator review stale generation")
            if decision == "accept_candidate":
                report = json.loads(evidence_rows[-1][4])
                if report.get("candidate_passed") is not True:
                    raise QualityGateError("operator cannot accept failing candidate")
            generation = expected_generation + 1
            payload = {
                "schema": "game.quality_operator_review.v1", "project_id": project,
                "generation": generation, "report_head_sha256": report_head_sha256,
                "reviewer_id": reviewer_id, "decision": decision,
                "reason_sha256": reason_sha256, "previous_sha256": expected_head,
                "production_approved": False,
            }
            receipt = _digest(payload)
            self.db.execute(
                "INSERT INTO quality_operator_review VALUES(?,?,?,?,?,?,?,?)",
                (project, generation, report_head_sha256, reviewer_id,
                 decision, reason_sha256, expected_head, receipt),
            )
            self.db.execute("COMMIT")
            return {**payload, "receipt_sha256": receipt}
        except Exception:
            self.db.execute("ROLLBACK")
            raise
