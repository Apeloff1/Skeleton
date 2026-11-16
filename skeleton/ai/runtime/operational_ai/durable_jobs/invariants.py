"""Independent full-store recovery qualification from typed audit replay."""
from __future__ import annotations

from .audit import verify_audit
from .canonical import require_int
from .errors import deny
from .event_projection import verify_projection
from .store import JobStore


def verify_store(store: JobStore, *, max_jobs: int = 100000) -> dict:
    if type(store) is not JobStore:
        deny("invariants-store")
    require_int(max_jobs, 1, 100000, "invariants-cap")
    with store.tx.exclusive() as db:
        event_proof = verify_audit(db)
        if db.execute("""SELECT 1 FROM ai_job_audit a
            LEFT JOIN ai_durable_jobs j ON a.job_id=j.job_id
            WHERE j.job_id IS NULL LIMIT 1""").fetchone() is not None:
            deny("invariants-orphan-audit")
        rows = db.execute(
            "SELECT job_id FROM ai_durable_jobs ORDER BY job_id LIMIT ?",
            (max_jobs+1,),
        ).fetchall()
        if len(rows) > max_jobs:
            deny("invariants-volume")
        terminal = pending = held = unbound_leases = 0
        for job_id, in rows:
            row = store._row(db, job_id)
            spec = store._bound_spec(db, row)
            projection = verify_projection(db, row, spec)
            parents = store._dependency_rows(db, row)
            if projection.state in ("completed", "failed", "cancelled"):
                terminal += 1
            elif projection.state == "pending":
                pending += 1
            elif projection.state == "held":
                held += 1
            if projection.state == "completed":
                store._verified_result(db, row, spec)
            if projection.state in ("running", "cancel_requested", "completed"):
                if any(parent[13] != "completed" for parent in parents):
                    deny("invariants-dependency-not-completed")
            if projection.state in ("running", "cancel_requested") and projection.token_sha is None:
                unbound_leases += 1
        return {
            "schema": "skeleton.ai.jobs.integrity.v1",
            "verified": True, "jobs": len(rows), "terminal": terminal,
            "pending": pending, "held": held,
            "legacy_unbound_active_leases": unbound_leases,
            "dispatch_qualified": unbound_leases == 0,
            "audit_events": event_proof["events"], "audit_sha": event_proof["head"],
            "native_model_qualified": False,
        }
