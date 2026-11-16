"""Replay durable job state from admitted audit events, never from row assertions.

The hash chain is local integrity evidence, not authentication of a hostile
database writer able to rewrite every event and anchor. Older claim events
lack token commitments; they can be inspected but not used as live authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import decode, require_int, require_sha
from .errors import deny
from .spec import JobSpec, require_id
from .state_rules import authorize_transition


@dataclass(slots=True)
class Projection:
    state: str = "unadmitted"
    attempt: int = 0
    worker: str | None = None
    token_sha: str | None = None
    lease: int | None = None
    terminal_sha: str | None = None
    failure: str | None = None
    updated: int = -1
    next_eligible: int = 0


def _fields(body: Any, required: set[str], optional: set[str] | None = None) -> None:
    if (type(body) is not dict or not required.issubset(body)
            or set(body) - required - (optional or set())):
        deny("job-audit-event-shape")


def replay_job(db, spec: JobSpec) -> Projection:
    """Build a bounded per-job projection from the already verified global chain."""
    out = Projection(next_eligible=spec.created_ms)
    count = 0
    for kind, raw in db.execute(
        "SELECT kind,event_json FROM ai_job_audit WHERE job_id=? ORDER BY seq",
        (spec.job_id,),
    ):
        count += 1
        if count > 100000:
            deny("job-audit-event-budget")
        body = decode(raw)
        if type(body) is not dict or "at" not in body:
            deny("job-audit-event-shape")
        at = require_int(body["at"], 0, 2**63-1, "audit-clock")
        if at < out.updated:
            deny("job-audit-clock-regressed")
        if kind == "submitted":
            _fields(body, {"at", "spec_sha"})
            if out.state != "unadmitted" or body["spec_sha"] != spec.digest:
                deny("job-admission-binding")
            if not spec.created_ms <= at < spec.expires_ms:
                deny("job-audit-admission-clock")
            out.state = "pending"
        elif out.state == "unadmitted":
            deny("job-audit-admission-missing")
        elif kind == "claimed":
            _fields(body, {"at", "worker", "attempt", "lease_expires_ms"}, {"lease_token_sha"})
            authorize_transition(out.state, "running")
            attempt = require_int(body["attempt"], 1, 20, "audit-attempt")
            until = require_int(body["lease_expires_ms"], 0, 2**63-1, "audit-lease")
            if attempt != out.attempt + 1 or not out.next_eligible <= at < until <= spec.expires_ms:
                deny("job-audit-claim")
            out.attempt = attempt
            out.worker = require_id(body["worker"], "audit-worker")
            out.token_sha = require_sha(body["lease_token_sha"]) if "lease_token_sha" in body else None
            out.lease = until
            out.state = "running"
        elif kind == "heartbeat":
            _fields(body, {"at", "until"})
            until = require_int(body["until"], 0, 2**63-1, "audit-lease")
            if (out.state != "running" or out.lease is None
                    or not at < out.lease < until <= spec.expires_ms):
                deny("job-audit-heartbeat")
            out.lease = until
        elif kind in ("completed", "failed", "held"):
            target = kind
            authorize_transition(out.state, target)
            if out.state not in ("running", "cancel_requested") or out.lease is None or not at < out.lease:
                deny("job-audit-terminal-lease")
            if kind == "completed":
                _fields(body, {"at", "result_sha"})
                out.terminal_sha = require_sha(body["result_sha"])
            else:
                _fields(body, {"at", "code"})
                out.failure = require_id(body["code"], "audit-failure")
                out.lease = None
            out.state = target
        elif kind in ("cancel_requested", "cancelled"):
            _fields(body, {"at"})
            authorize_transition(out.state, kind)
            out.state = kind
        elif kind in ("expired", "dependency_held", "lease_held"):
            _fields(body, {"at"})
            if kind == "expired":
                if out.state != "pending" or at < spec.expires_ms:
                    deny("job-audit-expiration")
                target = "cancelled"
            elif kind == "dependency_held":
                if out.state != "pending" or not spec.dependencies:
                    deny("job-audit-dependency-hold")
                target = "held"
            else:
                if (out.state not in ("running", "cancel_requested") or out.lease is None
                        or at < min(out.lease, spec.expires_ms)):
                    deny("job-audit-lease-hold")
                target = "held"
            authorize_transition(out.state, target)
            out.state, out.failure = target, kind
        elif kind == "manual_resume":
            _fields(body, {"at", "proof_sha", "approved"})
            require_sha(body["proof_sha"])
            if body["approved"] is not True or at >= spec.expires_ms or out.attempt >= 20:
                deny("job-audit-recovery")
            authorize_transition(out.state, "pending", operator=True)
            out.state = "pending"
            out.next_eligible = at
            out.worker = out.token_sha = out.lease = out.failure = None
        else:
            deny("job-audit-event-unknown")
        out.updated = at
    if count == 0 or out.state == "unadmitted":
        deny("job-audit-admission-missing")
    return out


def verify_projection(db, row, spec: JobSpec) -> Projection:
    projected = replay_job(db, spec)
    if ((row[13], row[14], row[16], row[17], row[18], row[20], row[21], row[11])
            != (projected.state, projected.attempt, projected.worker, projected.lease,
                projected.terminal_sha, projected.failure, projected.updated, projected.next_eligible)):
        deny("job-audit-state-binding")
    if projected.token_sha is not None and row[15] != projected.token_sha:
        deny("job-audit-token-binding")
    if projected.worker is None and row[15] is not None:
        deny("job-audit-token-binding")
    if (row[19] is None) != (projected.state != "completed"):
        deny("job-audit-result-presence")
    return projected
