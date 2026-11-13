"""Read-only Jeeves native recovery doctor; NO GGUF activation or inference.

May be used when native inference is broken, native Python worker is offline,
or a laptop must be inspected after a crash. Reads the protected SQLite
spine via its descriptor-anchored read-only connection. Reports only scoped
counts and structural custody: no user prompt, model output, source filename,
memory body, license secret, or private system path is disclosed.

An unknown/pending request remains a hold. A correct hash chain proves only
internal consistency against isolated corruption, NOT authenticity against
an administrator who can rewrite every SQLite root and record.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import sys
from typing import Any

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity, identifier,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import (
    SpineDatabase,
)
from .durable_runtime import _CheckpointCodec
from .native_checkpoint_journal import _link, _sha
from .types import AgentPhase


class ColdDoctorHold(ValueError):
    """Protected operator-only recovery evidence is absent or corrupt."""


def _json_read(data: bytes, *, ceiling: int = 1048576) -> object:
    if type(data) is not bytes or not 1 <= len(data) <= ceiling:
        raise ColdDoctorHold("bounded record bytes required")
    try:
        def pairs_hook(pairs):
            record = {}
            for key, value in pairs:
                if key in record:
                    raise ColdDoctorHold("duplicate durable JSON key")
                record[key] = value
            return record
        def reject_constant(value):
            raise ColdDoctorHold("nonfinite JSON constant")
        return json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ColdDoctorHold("durable record is not strict UTF-8 JSON") from exc


def _table(conn: sqlite3.Connection, name: str) -> None:
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name=?",
        (name,),
    ).fetchone()
    if row != ("table",):
        raise ColdDoctorHold("native custody schema missing required table")


def _run(conn, identity: Identity, run_id: str) -> tuple:
    _table(conn, "jeeves_native_runs")
    row = conn.execute(
        "SELECT scope_digest,tenant,subject,model_sha256,"
        "tokenizer_sha256,goal_id,anchor_sequence,anchor_hash,"
        "tip_sequence,tip_hash FROM jeeves_native_runs WHERE run_id=?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise ColdDoctorHold("run is not present in protected custody")
    if tuple(row[1:5]) != (
        identity.tenant, identity.subject,
        identity.model_sha256, identity.tokenizer_sha256,
    ):
        raise ColdDoctorHold("foreign or mismatched native run principal")
    return row


def _checkpoints(conn, run_id: str, row: tuple) -> dict:
    _table(conn, "jeeves_native_checkpoints")
    records = conn.execute(
        "SELECT sequence,payload,payload_sha256,previous_hash,entry_hash "
        "FROM jeeves_native_checkpoints WHERE run_id=? ORDER BY sequence",
        (run_id,),
    ).fetchall()
    if len(records) > 64:
        raise ColdDoctorHold("checkpoint history exceeded protection ceiling")
    prior_seq, prior_hash = row[6], row[7]
    last_checkpoint = None
    for sequence, payload, payload_hash, previous, entry_hash in records:
        if (sequence != prior_seq + 1 or previous != prior_hash
            or type(payload) is not bytes or not 1 <= len(payload) <= 1048576
            or _sha(payload) != payload_hash
            or _link(previous, sequence, payload_hash) != entry_hash):
            raise ColdDoctorHold("checkpoint sequence or integrity chain broken")
        raw = _json_read(payload)
        if (type(raw) is not dict or raw.get("schema") != "jeeves.native_checkpoint.v1"
            or type(raw.get("checkpoint")) is not dict):
            raise ColdDoctorHold("checkpoint envelope contract invalid")
        try:
            checkpoint = _CheckpointCodec.decode(raw["checkpoint"])
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ColdDoctorHold("checkpoint typed restoration failed") from exc
        if (checkpoint.fingerprint != raw.get("checkpoint_fingerprint")
            or checkpoint.run_id != run_id
            or checkpoint.goal_id != row[5]
            or checkpoint.sequence != sequence
            or checkpoint.metadata.get("tenant_id") != row[1]
            or checkpoint.metadata.get("user_id") != row[2]):
            raise ColdDoctorHold("durable checkpoint does not bind run principal")
        prior_seq, prior_hash = sequence, entry_hash
        last_checkpoint = checkpoint
    if (prior_seq != row[8] or prior_hash != row[9] or
        not records and (row[8] != 0 or row[9] != "0" * 64)):
        raise ColdDoctorHold("checkpoint tail missing or tampered")
    return {
        "checkpoint_sequence": row[8],
        "retained_checkpoint_count": len(records),
        "checkpoint_phase": (last_checkpoint.phase.value
                             if last_checkpoint is not None else "admitted"),
        "checkpoint_plan_has_tools": bool(
            last_checkpoint is not None and last_checkpoint.plan is not None
            and any(step.tool for step in last_checkpoint.plan.steps)
        ),
        "checkpoint_running_steps": sum(
            getattr(step.status, "value", None) == "running"
            for step in last_checkpoint.plan.steps
        ) if last_checkpoint is not None and last_checkpoint.plan is not None else 0,
        "checkpoint_model_calls": (
            last_checkpoint.usage.model_calls if last_checkpoint else 0
        ),
        "checkpoint_tool_calls": (
            last_checkpoint.usage.tool_calls if last_checkpoint else 0
        ),
        "last_checkpoint": last_checkpoint,
    }


def _intent(conn, run_id: str, checkpoint_seq: int) -> bool:
    _table(conn, "jeeves_native_inflight")
    row = conn.execute(
        "SELECT admitted_after_sequence FROM jeeves_native_inflight "
        "WHERE run_id=?", (run_id,),
    ).fetchone()
    if row is None:
        return False
    if type(row[0]) is not int or not 0 <= row[0] <= checkpoint_seq:
        raise ColdDoctorHold("in-flight intent points to invalid checkpoint")
    return True


def _terminal(conn, run_id: str, row: tuple, checkpoint: object) -> bool:
    _table(conn, "jeeves_native_terminal_results")
    saved = conn.execute(
        "SELECT checkpoint_sequence,checkpoint_fingerprint,"
        "checkpoint_tip_hash,payload,payload_sha256 "
        "FROM jeeves_native_terminal_results WHERE run_id=?",
        (run_id,),
    ).fetchone()
    if saved is None:
        return False
    seq, saved_fingerprint, tip_hash, payload, checksum = saved
    if (checkpoint is None or seq != checkpoint.sequence
        or checkpoint.phase not in (
            AgentPhase.COMPLETED, AgentPhase.FAILED, AgentPhase.CANCELLED)
        or saved_fingerprint != checkpoint.fingerprint or tip_hash != row[9]
        or type(payload) is not bytes or not 1 <= len(payload) <= 1048576
        or _sha(payload) != checksum):
        raise ColdDoctorHold("terminal answer bytes lack durable checkpoint proof")
    value = _json_read(payload)
    if (type(value) is not dict
        or value.get("schema") != "jeeves.native_terminal_result.v1"
        or value.get("run_id") != run_id
        or value.get("goal_id") != row[5]
        or value.get("model_sha256") != row[3]
        or value.get("tokenizer_sha256") != row[4]
        or type(value.get("success")) is not bool
        or value["success"] != (checkpoint.phase is AgentPhase.COMPLETED)
        or type(value.get("answer")) is not str):
        raise ColdDoctorHold("terminal output ownership or contract mismatch")
    return True


def _memory(conn, run_id: str, row: tuple) -> int:
    _table(conn, "jeeves_native_memories")
    records = conn.execute(
        "SELECT namespace_key,fingerprint,payload,payload_sha256 "
        "FROM jeeves_native_memories WHERE run_id=?",
        (run_id,),
    ).fetchall()
    if len(records) > 256:
        raise ColdDoctorHold("run memory limit violated")
    for namespace_key, recorded_fingerprint, payload, checksum in records:
        if (type(payload) is not bytes or len(payload) > 262144
            or _sha(payload) != checksum):
            raise ColdDoctorHold("run memory checksum or byte ceiling invalid")
        value = _json_read(payload, ceiling=262144)
        if type(value) is not dict or value.get("schema") != "jeeves.native_memory_record.v1":
            raise ColdDoctorHold("unrecognized private memory schema")
        from .native_run_memory import NativeRunMemoryStore
        try:
            record = NativeRunMemoryStore._decode(payload)
        except (ValueError, TypeError, KeyError) as exc:
            raise ColdDoctorHold("run memory typed contract invalid") from exc
        if (record.namespace.tenant_id != row[1]
            or record.namespace.user_id != row[2]
            or record.namespace.key != namespace_key
            or record.fingerprint != recorded_fingerprint):
            raise ColdDoctorHold("run memory principal or provenance mismatch")
    return len(records)


def _principal_requests(conn, identity: Identity) -> dict[str, int]:
    result = dict.fromkeys(("pending", "committed", "held", "cancelled"), 0)
    # A different tenant's sessions, raw prompts and answers must not leak
    # into the operator report or affect its principal-specific decision.
    rows = conn.execute(
        "SELECT r.state,COUNT(*) FROM requests r "
        "JOIN sessions s ON s.session=r.session "
        "WHERE s.principal=? GROUP BY r.state",
        (identity.key(),),
    ).fetchall()
    for state, count in rows:
        if state not in result or type(count) is not int or count < 0:
            raise ColdDoctorHold("unknown native request state")
        result[state] = count
    return result


def _principal_effects(conn, identity: Identity) -> dict[str, int]:
    result = dict.fromkeys(("attempting", "completed", "held"), 0)
    rows = conn.execute(
        "SELECT status,COUNT(*) FROM effects WHERE principal=? GROUP BY status",
        (identity.key(),),
    ).fetchall()
    for state, count in rows:
        if state not in result or type(count) is not int or count < 0:
            raise ColdDoctorHold("unknown side-effect state")
        result[state] = count
    return result


def inspect_cold_state(
    *, state_dir: Path, tenant: str, subject: str,
    model_sha256: str, tokenizer_sha256: str, run_id: str,
) -> dict[str, object]:
    """Perform a bounded, read-only, no-model cold forensic inspection."""
    if not isinstance(state_dir, Path) or not state_dir.is_absolute():
        raise ColdDoctorHold("explicit absolute protected SQLite root required")
    if ".." in state_dir.parts:
        raise ColdDoctorHold("noncanonical state root refused")
    run_id = identifier(run_id, "run")
    identity = Identity(tenant, subject, model_sha256, tokenizer_sha256)
    with SpineDatabase(state_dir, readonly=True) as db:
        with db.snapshot() as conn:
            row = _run(conn, identity, run_id)
            checkpoint = _checkpoints(conn, run_id, row)
            intent = _intent(conn, run_id, checkpoint["checkpoint_sequence"])
            sealed = _terminal(conn, run_id, row, checkpoint["last_checkpoint"])
            memory_count = _memory(conn, run_id, row)
            requests = _principal_requests(conn, identity)
            effects = _principal_effects(conn, identity)
            known_pending = bool(
                intent or requests["pending"] or requests["held"] or
                effects["attempting"] or effects["held"]
            )
            terminal_phase = checkpoint["checkpoint_phase"] in (
                "completed", "failed", "cancelled",
            )
            no_tool_risks = (
                checkpoint["checkpoint_tool_calls"] == 0
                and not checkpoint["checkpoint_plan_has_tools"]
                and checkpoint["checkpoint_running_steps"] == 0
            )
            candidate = bool(
                not terminal_phase and no_tool_risks and not known_pending
                and checkpoint["retained_checkpoint_count"] > 0
            )
            return {
                "schema": "jeeves.native_cold_doctor.v1",
                "status": "inspected-readonly-not-resumed",
                "run_id": run_id,
                "checkpoint_phase": checkpoint["checkpoint_phase"],
                "checkpoint_sequence": checkpoint["checkpoint_sequence"],
                "retained_checkpoints": checkpoint["retained_checkpoint_count"],
                "run_scoped_memory_count": memory_count,
                "terminal_answer_sealed": sealed,
                "unresolved_inference_intent": intent,
                "principal_request_counts": requests,
                "principal_effect_counts": effects,
                "no_automatic_retry": True,
                "operator_resume_structurally_admissible": candidate,
                "resume_requires_same_original_run_inputs": True,
                "native_model_loaded": False,
                "native_model_called": False,
                "physical_device_qualified": False,
                "release_certified": False,
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Readonly Jeeves recovery inspection with NO native model load"
    )
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--tokenizer-sha256", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        record = inspect_cold_state(
            state_dir=args.state_dir, tenant=args.tenant,
            subject=args.subject, model_sha256=args.model_sha256,
            tokenizer_sha256=args.tokenizer_sha256,
            run_id=args.run_id,
        )
        sys.stdout.write(json.dumps(
            record, sort_keys=True, ensure_ascii=False,
        ) + "\n")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        sys.stderr.write(json.dumps({
            "schema": "jeeves.native_cold_doctor.v1",
            "status": "held",
            "error_class": type(exc).__name__,
            "native_model_loaded": False,
            "release_certified": False,
        }, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ColdDoctorHold", "inspect_cold_state", "main"]
