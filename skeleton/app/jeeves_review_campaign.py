"""Restart-safe, operator-authored local reasoning DAGs.

This is a controller over canonical chat SQLite and the existing deliberation
boundary, not a scheduler, provider, or new inference authority. Every step
requires explicit dispatch. Prior generated text is never a subsequent prompt.
A lost running claim is visible and may be abandoned, never silently retried.
"""
from __future__ import annotations

import hashlib
import json
import re

from skeleton.app.jeeves_constraints import normalize_policy
from skeleton.app.offline_grounding import normalized_document_scope
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError

SCHEMA = "skeleton.jeeves.review-campaign.v1"
MAX_NODES = 12
MAX_CAMPAIGNS_PER_SESSION = 8
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_CAMPAIGN_TOKENS = 4096
_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class CampaignRejected(ValueError):
    pass


class CampaignConflict(CampaignRejected):
    pass


def _id(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise CampaignRejected("invalid campaign identifier")
    return value


def _int(value, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise CampaignRejected("invalid campaign numeric bound")
    return value


def _stable(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_stable(value).encode("utf-8")).hexdigest()


def _text_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _shape(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise CampaignRejected("invalid campaign shape")


def normalize_sources(value):
    if type(value) is not list or not 1 <= len(value) <= 8:
        raise CampaignRejected("one to eight explicit source pins required")
    pins = []
    for row in value:
        _shape(row, ("document_id", "sha256"))
        if type(row["sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is None:
            raise CampaignRejected("invalid local document digest")
        pins.append(dict(row))
    try:
        normalized_document_scope([row["document_id"] for row in pins])
    except RuntimeContractError:
        raise CampaignRejected("invalid explicit document scope") from None
    return sorted(pins, key=lambda row: row["document_id"])


def normalize_plan(steps, maximum_reserved_tokens):
    """Closed graph with no tool authority, hidden prompts or executable code."""
    ceiling = _int(maximum_reserved_tokens, 1, MAX_CAMPAIGN_TOKENS)
    if type(steps) is not list or not 1 <= len(steps) <= MAX_NODES:
        raise CampaignRejected("invalid campaign size")
    normalized = []
    seen = set()
    reserved = 0
    for row in steps:
        required = {"id", "depends_on", "message", "max_output_tokens", "adaptive"}
        if type(row) is not dict or not required <= set(row) <= required | {"sources", "history_policy"}:
            raise CampaignRejected("invalid campaign step shape")
        node = _id(row["id"])
        if node in seen:
            raise CampaignRejected("duplicate workflow step")
        seen.add(node)
        dependencies = row["depends_on"]
        if type(dependencies) is not list or len(dependencies) > MAX_NODES:
            raise CampaignRejected("invalid workflow dependencies")
        dependencies = [_id(item) for item in dependencies]
        if node in dependencies or len(set(dependencies)) != len(dependencies):
            raise CampaignRejected("cyclic or duplicate dependency")
        message = row["message"]
        if (type(message) is not str or not message.strip() or "\x00" in message):
            raise CampaignRejected("invalid step question")
        try:
            if len(message.encode("utf-8")) > 1024:
                raise CampaignRejected("step question exceeds byte limit")
        except UnicodeError:
            raise CampaignRejected("invalid Unicode question") from None
        budget = _int(row["max_output_tokens"], 1, 128)
        try:
            policy = normalize_policy(row["adaptive"], budget)
        except (ValueError, TypeError, OverflowError):
            raise CampaignRejected("invalid step reasoning policy") from None
        reserve = min(policy["max_attempts"],
                      policy["maximum_reserved_tokens"] // budget) * budget
        reserved += reserve
        extras = {}
        if "sources" in row:
            extras["sources"] = normalize_sources(row["sources"])
        if "history_policy" in row:
            if row["history_policy"] not in ("recent", "relevance"):
                raise CampaignRejected("invalid review context selection")
            extras["history_policy"] = row["history_policy"]
        if policy["contract"]["kind"] == "source_quotes":
            if len(extras.get("sources", [])) < policy["contract"]["minimum_distinct_sources"]:
                raise CampaignRejected("quote campaign requires sufficiently many explicit source pins")
        normalized.append({"id": node, "depends_on": sorted(dependencies),
                           "message": message.strip(), "max_output_tokens": budget,
                           "adaptive": policy, "reservation": reserve, **extras})
    graph = {row["id"]: set(row["depends_on"]) for row in normalized}
    if any(not parents <= seen for parents in graph.values()):
        raise CampaignRejected("unknown workflow dependency")
    visited = set()
    while len(visited) < len(graph):
        ready = {node for node, parents in graph.items()
                 if node not in visited and parents <= visited}
        if not ready:
            raise CampaignRejected("cyclic workflow graph")
        visited.update(ready)
    if reserved > ceiling:
        raise CampaignRejected("campaign reservation exceeds approved ceiling")
    return {"steps": normalized, "maximum_reserved_tokens": ceiling,
            "worst_case_reserved_tokens": reserved}


class ReviewCampaignStore:
    def __init__(self, store, model_digest, tokenizer_digest, *, knowledge=None):
        self.store = store
        self.model_digest = model_digest
        self.tokenizer_digest = tokenizer_digest
        self.knowledge = knowledge
        with store._transaction():
            store._db.execute("""CREATE TABLE IF NOT EXISTS offline_review_campaigns (
                session_id TEXT NOT NULL REFERENCES offline_sessions(session_id) ON DELETE CASCADE,
                campaign_id TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision >= 0),
                state_json TEXT NOT NULL,
                state_sha256 TEXT NOT NULL,
                PRIMARY KEY(session_id, campaign_id)
            )""")

    def verify_sources(self, pins):
        pins = normalize_sources(pins)
        if self.knowledge is None:
            raise CampaignConflict("local knowledge authority unavailable")
        scope = tuple(row["document_id"] for row in pins)
        try:
            rows, _ = self.knowledge._verified_snapshot(scope)
        except RuntimeContractError:
            raise CampaignConflict("approved campaign source unavailable") from None
        actual = {row[0]: row[2] for row in rows}
        expected = {row["document_id"]: row["sha256"] for row in pins}
        if actual != expected:
            raise CampaignConflict("approved campaign source digest changed")

    def _session(self, sid):
        return self.store.load(sid, self.model_digest, self.tokenizer_digest)

    def _load(self, sid, cid):
        row = self.store._db.execute(
            "SELECT revision,state_json,state_sha256 FROM offline_review_campaigns "
            "WHERE session_id=? AND campaign_id=?", (sid, cid)).fetchone()
        if row is None:
            raise CampaignRejected("unknown local review campaign")
        revision, raw, pin = row
        if type(raw) is not str or len(raw) > MAX_RECORD_BYTES:
            raise CampaignConflict("campaign record integrity failure")
        try:
            if _text_digest(raw) != pin or len(raw.encode("utf-8")) > MAX_RECORD_BYTES:
                raise CampaignConflict("campaign record integrity failure")
            value = json.loads(raw)
            if (_stable(value) != raw or value["schema"] != SCHEMA
                    or value["revision"] != revision or value["session_id"] != sid
                    or value["campaign_id"] != cid
                    or value["model_digest"] != self.model_digest
                    or value["tokenizer_digest"] != self.tokenizer_digest
                    or _digest(value["plan"]) != value["plan_sha256"]):
                raise CampaignConflict("campaign record identity mismatch")
        except (KeyError, TypeError, ValueError, RecursionError, OverflowError):
            raise CampaignConflict("campaign record integrity failure") from None
        return value

    def _write(self, state, old_revision=None):
        raw = _stable(state)
        if len(raw.encode("utf-8")) > MAX_RECORD_BYTES:
            raise CampaignRejected("campaign storage ceiling exceeded")
        pin = _text_digest(raw)
        if old_revision is None:
            self.store._db.execute(
                "INSERT INTO offline_review_campaigns VALUES (?,?,?,?,?)",
                (state["session_id"], state["campaign_id"], state["revision"], raw, pin))
        else:
            cursor = self.store._db.execute(
                "UPDATE offline_review_campaigns SET revision=?,state_json=?,state_sha256=? "
                "WHERE session_id=? AND campaign_id=? AND revision=?",
                (state["revision"], raw, pin, state["session_id"],
                 state["campaign_id"], old_revision))
            if cursor.rowcount != 1:
                raise CampaignConflict("campaign changed concurrently")

    def _view(self, state, session_revision):
        statuses = state["statuses"]
        ready = [row["id"] for row in state["plan"]["steps"]
                 if statuses[row["id"]]["status"] == "pending"
                 and all(statuses[p]["status"] == "complete" for p in row["depends_on"])]
        stale = state["session_revision"] != session_revision
        unresolved = any(row["status"] == "running" for row in statuses.values())
        return {**state, "ready_steps": [] if stale or unresolved else ready,
                "session_snapshot_stale": stale,
                "all_steps_complete": all(r["status"] == "complete" for r in statuses.values()),
                "generation_automatic": False, "dependency_output_injected": False,
                "tool_execution_authorized": False, "transcript_committed": False}

    def create(self, sid, cid, expected_session_revision, steps, maximum_reserved_tokens):
        cid = _id(cid)
        rev = _int(expected_session_revision, 0, 2**63-1)
        plan = normalize_plan(steps, maximum_reserved_tokens)
        with self.store._transaction():
            current = self._session(sid)
            exists = self.store._db.execute(
                "SELECT 1 FROM offline_review_campaigns WHERE session_id=? AND campaign_id=?",
                (sid, cid)).fetchone()
            if exists:
                old = self._load(sid, cid)
                if old["plan"] != plan or old["session_revision"] != rev:
                    raise CampaignConflict("campaign identifier reused with different input")
                return self._view(old, current.revision), False
            if current.revision != rev:
                raise CampaignConflict("session revision changed before campaign creation")
            for spec in plan["steps"]:
                if spec.get("sources"):
                    self.verify_sources(spec["sources"])
            count = self.store._db.execute(
                "SELECT COUNT(*) FROM offline_review_campaigns WHERE session_id=?", (sid,)).fetchone()[0]
            if count >= MAX_CAMPAIGNS_PER_SESSION:
                raise CampaignRejected("campaign count ceiling reached")
            state = {"schema": SCHEMA, "session_id": sid, "campaign_id": cid,
                     "session_revision": rev, "revision": 0,
                     "model_digest": self.model_digest, "tokenizer_digest": self.tokenizer_digest,
                     "plan": plan, "plan_sha256": _digest(plan), "reserved_tokens": 0,
                     "statuses": {row["id"]: {"status": "pending"} for row in plan["steps"]}}
            self._write(state)
            return self._view(state, rev), True

    def inspect(self, sid, cid):
        cid = _id(cid)
        with self.store.read_snapshot():
            current = self._session(sid)
            return self._view(self._load(sid, cid), current.revision)

    def claim(self, sid, cid, node, operation_id, expected_revision):
        cid, node, operation_id = map(_id, (cid, node, operation_id))
        revision = _int(expected_revision, 0, 2**63-1)
        with self.store._transaction():
            current = self._session(sid)
            state = self._load(sid, cid)
            statuses = state["statuses"]
            if node not in statuses:
                raise CampaignRejected("unknown campaign step")
            for other, row in statuses.items():
                if row.get("operation_id") == operation_id:
                    if other != node:
                        raise CampaignConflict("operation identifier reused for another step")
                    if row["status"] == "running":
                        raise CampaignConflict("step may be in flight; inspect or explicitly abandon")
                    return self._view(state, current.revision), None
            if state["revision"] != revision or current.revision != state["session_revision"]:
                raise CampaignConflict("campaign or conversation revision changed")
            if any(row["status"] == "running" for row in statuses.values()):
                raise CampaignConflict("another campaign step has an unresolved claim")
            if node not in self._view(state, current.revision)["ready_steps"]:
                raise CampaignConflict("step is not ready or was already dispatched")
            spec = next(row for row in state["plan"]["steps"] if row["id"] == node)
            if spec.get("sources"):
                self.verify_sources(spec["sources"])
            if state["reserved_tokens"] + spec["reservation"] > state["plan"]["maximum_reserved_tokens"]:
                raise CampaignConflict("campaign token budget exhausted")
            statuses[node] = {"status": "running", "operation_id": operation_id,
                              "reservation": spec["reservation"]}
            state["reserved_tokens"] += spec["reservation"]
            state["revision"] += 1
            self._write(state, revision)
            return self._view(state, current.revision), spec

    def settle(self, sid, cid, node, operation_id, report=None):
        """Settle one claim; failure retains reservation and never retries."""
        cid, node, operation_id = map(_id, (cid, node, operation_id))
        with self.store._transaction():
            current = self._session(sid)
            state = self._load(sid, cid)
            existing = state["statuses"].get(node)
            if not existing or existing["status"] != "running" or existing["operation_id"] != operation_id:
                raise CampaignConflict("campaign claim withdrawn or already settled")
            revision = state["revision"]
            result = {**existing, "status": "execution_unconfirmed"}
            if report is not None:
                if current.revision != state["session_revision"]:
                    raise CampaignConflict("conversation changed during campaign")
                spec = next(row for row in state["plan"]["steps"] if row["id"] == node)
                if spec.get("sources"):
                    self.verify_sources(spec["sources"])
                if (type(report) is not dict
                        or report.get("schema") != "skeleton.jeeves.adaptive-review.v1"
                        or report.get("model_digest") != self.model_digest
                        or report.get("tokenizer_digest") != self.tokenizer_digest
                        or report.get("session_revision") != state["session_revision"]
                        or report.get("question_sha256") != _text_digest(spec["message"])
                        or report.get("history_policy", "recent") != spec.get("history_policy", "recent")
                        or report.get("require_full_history") is not (spec.get("history_policy", "recent") == "recent")
                        or report.get("transcript_committed") is not False
                        or report.get("tool_execution_authorized") is not False
                        or report.get("memory_saved") is not False
                        or report.get("generation_performed") is not True
                        or type(report.get("reserved_total_output_tokens")) is not int
                        or not 1 <= report["reserved_total_output_tokens"] <= existing["reservation"]
                        or report.get("adaptive", {}).get("policy") != spec["adaptive"]
                        or type(report.get("adaptive", {}).get("contract_passed")) is not bool
                        or _digest({k: v for k, v in report.items() if k != "report_sha256"})
                        != report.get("report_sha256")):
                    raise CampaignConflict("campaign result lacks bound execution receipt")
                if spec.get("sources"):
                    expected = {row["document_id"]: row["sha256"] for row in spec["sources"]}
                    receipts = report.get("evidence_sources")
                    if not isinstance(receipts, list) or not receipts or any(
                            not isinstance(row, dict) or expected.get(row.get("document_id")) != row.get("document_sha256")
                            for row in receipts):
                        raise CampaignConflict("campaign result lacks approved source bindings")
                elif report.get("grounding_context_sha256") is not None:
                    raise CampaignConflict("unapproved grounded campaign execution")
                passed = report["adaptive"]["contract_passed"]
                completed = spec["adaptive"]["contract"]["kind"] == "review" or passed
                result.update({"status": "complete" if completed else "contract_not_met",
                               "report": report, "contract_passed": passed})
            state["statuses"][node] = result
            state["revision"] += 1
            self._write(state, revision)
            return self._view(state, current.revision)

    def abandon(self, sid, cid, node, operation_id, expected_revision):
        cid, node, operation_id = map(_id, (cid, node, operation_id))
        revision = _int(expected_revision, 0, 2**63-1)
        with self.store._transaction():
            current = self._session(sid)
            state = self._load(sid, cid)
            row = state["statuses"].get(node)
            if (state["revision"] != revision or not row or row["status"] != "running"
                    or row["operation_id"] != operation_id):
                raise CampaignConflict("campaign claim or revision changed")
            # This records uncertainty, not process cancellation. No reset.
            row["status"] = "abandoned_unconfirmed"
            state["revision"] += 1
            self._write(state, revision)
            return self._view(state, current.revision)

    def delete(self, sid, cid, expected_revision):
        cid = _id(cid)
        revision = _int(expected_revision, 0, 2**63-1)
        with self.store._transaction():
            self._session(sid)
            state = self._load(sid, cid)
            if state["revision"] != revision or any(
                    row["status"] == "running" for row in state["statuses"].values()):
                raise CampaignConflict("campaign changed or has an unresolved running claim")
            self.store._db.execute(
                "DELETE FROM offline_review_campaigns WHERE session_id=? AND campaign_id=?",
                (sid, cid))
            return {"deleted_campaign_id": cid, "transcript_deleted": False}
