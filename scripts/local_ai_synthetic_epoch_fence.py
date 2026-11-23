#!/usr/bin/env python3
"""Synthetic, cross-process Mongo actor epoch CAS/failover qualification.

All writes target ONLY the previously admitted, random, three-member
internal Docker replica set. This module has no production URI, filesystem,
network, Docker creation, or application writer binding controls. The caller
must prove exact image IDs, no-pull container and disposable test isolation.

A successful synthetic actor fence does not prove that backend/engine
production writers are enrolled or that external writers are excluded.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from scripts import qualify_local_ai_mongo_quorum_docker as physical

SCHEMA = "skeleton.local-ai.docker.synthetic-actor-epoch-cas.v1"
HEX = re.compile(r"[0-9a-f]{32}\Z")
PHASES = ("stable", "writing")
DB = "skl_ephemeral_qualification"
COLLECTION = "synthetic_canonical_epoch"


class SyntheticEpochError(physical.SyntheticMongoError):
    """Synthetic actor epoch cannot be independently qualified."""


def _hex(value: object) -> str:
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise SyntheticEpochError("synthetic writer nonce invalid")
    return value


def _key(nonce: str, actor: int) -> str:
    """Stable identity unique to a disposable run, never an app actor ID."""
    _hex(nonce)
    if type(actor) is not int or actor not in (0, 1):
        raise SyntheticEpochError("synthetic actor scope invalid")
    digest = hashlib.sha256(
        ("skeleton.synthetic-mongo-actor-epoch.v1\x00" + nonce + "\x00"
         + str(actor)).encode("ascii")
    ).hexdigest()
    return "skl-test-epoch-" + digest


def _token(nonce: str, writer: int) -> str:
    _hex(nonce)
    if type(writer) is not int or writer not in (0, 1, 2, 3):
        raise SyntheticEpochError("synthetic writer role invalid")
    return hashlib.sha256(
        ("skeleton.synthetic-mongo-writer.v1\x00" + nonce + "\x00"
         + str(writer)).encode("ascii")
    ).hexdigest()


def _expect(value: Any, *, updated: bool, epoch: int, phase: str,
            matching_token: bool) -> None:
    """Accept only the exact acknowledged findAndModify result shape."""
    if (not isinstance(value, dict)
            or set(value) != {"ok", "changed", "epoch", "phase",
                              "token_matches", "concern_error"}
            or value.get("ok") is not True
            or value.get("concern_error") is not False
            or value.get("changed") is not updated
            or type(value.get("epoch")) is not int
            or value.get("epoch") != epoch
            or value.get("phase") != phase
            or value.get("token_matches") is not matching_token):
        raise SyntheticEpochError("synthetic durable CAS evidence invalid")


def _shell(container_id: str, javascript: str) -> dict[str, Any]:
    if (not isinstance(container_id, str) or
            not physical.CID.fullmatch(container_id)
            or not isinstance(javascript, str)
            or not 0 < len(javascript) <= 6000):
        raise SyntheticEpochError("synthetic epoch command outside admitted scope")
    try:
        answer = physical._shell(container_id, javascript)
    except physical.SyntheticMongoError:
        raise SyntheticEpochError("synthetic epoch Mongo command unavailable") from None
    if not isinstance(answer, dict):
        raise SyntheticEpochError("synthetic epoch did not return a structured receipt")
    return answer


def _create(cid: str, nonce: str, actor: int) -> None:
    key = _key(nonce, actor)
    query = (
        'const d=db.getSiblingDB("' + DB + '");'
        'const r=d.runCommand({insert:"' + COLLECTION + '",'
        'documents:[{_id:"' + key + '",phase:"stable",'
        'epoch:2,writer_token:null}],ordered:true,'
        'writeConcern:{w:"majority",j:true,wtimeout:10000},'
        'maxTimeMS:15000});'
        'return {ok:r.ok===1,inserted:r.n===1,'
        'write_error:!!r.writeErrors,concern_error:!!r.writeConcernError};'
    )
    answer = _shell(cid, query)
    if answer != {
        "ok": True, "inserted": True,
        "write_error": False, "concern_error": False,
    }:
        raise SyntheticEpochError("synthetic epoch initialization lacked majority journal ack")


def _cas(cid: str, nonce: str, actor: int, *,
         prior_epoch: int, prior_phase: str, prior_token: str | None,
         next_phase: str, next_token: str | None,
         token_to_match: str | None, expect_changed: bool) -> None:
    """Use the same monotonic odd/even stable/writing transition as source.

    This deliberately uses Mongo's actual majority-journaled findAndModify
    atomic CAS from different shell processes; no mock-only mutation passes.
    """
    key = _key(nonce, actor)
    if (type(prior_epoch) is not int or not 2 <= prior_epoch <= 1024
            or prior_phase not in PHASES or next_phase not in PHASES
            or next_phase == prior_phase
            or prior_epoch % 2 != (0 if prior_phase == "stable" else 1)
            or (prior_phase == "stable" and prior_token is not None)
            or (next_phase == "stable" and next_token is not None)
            or (next_phase == "writing" and next_token is None)
            or type(expect_changed) is not bool):
        raise SyntheticEpochError("synthetic epoch transition invalid")
    for token in (prior_token, next_token, token_to_match):
        if token is not None and (type(token) is not str
                                  or not re.fullmatch(r"[0-9a-f]{64}", token)):
            raise SyntheticEpochError("writer token not from synthetic scope")
    encoded = "null" if prior_token is None else '"' + prior_token + '"'
    update_token = "null" if next_token is None else '"' + next_token + '"'
    matching = "null" if token_to_match is None else '"' + token_to_match + '"'
    expr = (
        'const d=db.getSiblingDB("' + DB + '");'
        'const r=d.runCommand({findAndModify:"' + COLLECTION + '",'
        'query:{_id:"' + key + '",epoch:' + str(prior_epoch)
        + ',phase:"' + prior_phase + '",writer_token:' + encoded + '},'
        'update:{$inc:{epoch:1},$set:{phase:"' + next_phase
        + '",writer_token:' + update_token + '}},new:true,'
        'writeConcern:{w:"majority",j:true,wtimeout:10000},'
        'maxTimeMS:15000});'
        'const x=r.value;'
        'return {ok:r.ok===1,changed:!!x,'
        'epoch:x?x.epoch:-1,phase:x?x.phase:"absent",'
        'token_matches:x?x.writer_token===' + matching + ':false,'
        'concern_error:!!r.writeConcernError};'
    )
    answer = _shell(cid, expr)
    _expect(answer, updated=expect_changed,
            epoch=prior_epoch + 1 if expect_changed else -1,
            phase=next_phase if expect_changed else "absent",
            matching_token=expect_changed)


def _linearizable(cid: str, nonce: str, actor: int, *,
                  epoch: int, phase: str, token: str | None) -> None:
    """Read same actor from the currently elected majority-capable primary."""
    key = _key(nonce, actor)
    if (type(epoch) is not int or not 2 <= epoch <= 1024
            or phase not in PHASES
            or (phase == "stable") != (token is None)
            or epoch % 2 != (0 if phase == "stable" else 1)):
        raise SyntheticEpochError("synthetic epoch expected stable/odd witness invalid")
    if token is not None and not re.fullmatch(r"[0-9a-f]{64}", token):
        raise SyntheticEpochError("synthetic epoch proof token invalid")
    expected_token = "null" if token is None else '"' + token + '"'
    expr = (
        'const d=db.getSiblingDB("' + DB + '");'
        'const r=d.runCommand({find:"' + COLLECTION + '",'
        'filter:{_id:"' + key + '"},limit:1,'
        'readConcern:{level:"linearizable"},maxTimeMS:5000});'
        'const x=((r.cursor||{}).firstBatch||[]);'
        'return {ok:r.ok===1,exactly_one:x.length===1,'
        'epoch_matches:x.length===1&&x[0].epoch===' + str(epoch) + ','
        'phase_matches:x.length===1&&x[0].phase==="' + phase + '",'
        'token_matches:x.length===1&&x[0].writer_token==='
        + expected_token + '};'
    )
    if _shell(cid, expr) != {
        "ok": True, "exactly_one": True, "epoch_matches": True,
        "phase_matches": True, "token_matches": True,
    }:
        raise SyntheticEpochError("synthetic primary linearizable actor epoch changed")


def before_failover(primary_cid: str, nonce: str) -> dict[str, bool]:
    """Create two synthetic actors; quarantine actor 0 in WRITING.

    Validates a complete writer 2→3→4 transition, incorrect token denial,
    new 4→5 admission, competing writer denial and linearizable odd epoch.
    Does not reconcile or auto-recover the deliberately crashed actor.
    """
    _hex(nonce)
    _create(primary_cid, nonce, 0)
    _create(primary_cid, nonce, 1)
    first = _token(nonce, 0)
    stale = _token(nonce, 1)
    quarantined = _token(nonce, 2)
    _linearizable(primary_cid, nonce, 0,
                  epoch=2, phase="stable", token=None)
    _cas(primary_cid, nonce, 0, prior_epoch=2,
         prior_phase="stable", prior_token=None,
         next_phase="writing", next_token=first,
         token_to_match=first, expect_changed=True)
    _cas(primary_cid, nonce, 0, prior_epoch=2,
         prior_phase="stable", prior_token=None,
         next_phase="writing", next_token=stale,
         token_to_match=stale, expect_changed=False)
    _linearizable(primary_cid, nonce, 0,
                  epoch=3, phase="writing", token=first)
    _cas(primary_cid, nonce, 0, prior_epoch=3,
         prior_phase="writing", prior_token=stale,
         next_phase="stable", next_token=None,
         token_to_match=None, expect_changed=False)
    _cas(primary_cid, nonce, 0, prior_epoch=3,
         prior_phase="writing", prior_token=first,
         next_phase="stable", next_token=None,
         token_to_match=None, expect_changed=True)
    _linearizable(primary_cid, nonce, 0,
                  epoch=4, phase="stable", token=None)
    _cas(primary_cid, nonce, 0, prior_epoch=4,
         prior_phase="stable", prior_token=None,
         next_phase="writing", next_token=quarantined,
         token_to_match=quarantined, expect_changed=True)
    _linearizable(primary_cid, nonce, 0,
                  epoch=5, phase="writing", token=quarantined)
    return {
        "synthetic_writer_stable_to_writing_majority_cas": True,
        "synthetic_competing_writer_refused": True,
        "synthetic_wrong_token_completion_refused": True,
        "synthetic_writer_completed_stable_even_epoch": True,
        "synthetic_unfinished_writer_quarantined_before_failover": True,
    }


def after_failover(new_primary_cid: str, nonce: str) -> dict[str, bool]:
    """Prove old writer remains quarantined on a newly elected primary.

    A different actor can still progress independently through 2→3→4.
    No unsafe self-heal, forced token takeover or migration is attempted.
    """
    _hex(nonce)
    quarantined = _token(nonce, 2)
    attacker = _token(nonce, 3)
    _linearizable(new_primary_cid, nonce, 0,
                  epoch=5, phase="writing", token=quarantined)
    _cas(new_primary_cid, nonce, 0, prior_epoch=4,
         prior_phase="stable", prior_token=None,
         next_phase="writing", next_token=attacker,
         token_to_match=attacker, expect_changed=False)
    _cas(new_primary_cid, nonce, 0, prior_epoch=5,
         prior_phase="writing", prior_token=attacker,
         next_phase="stable", next_token=None,
         token_to_match=None, expect_changed=False)
    _linearizable(new_primary_cid, nonce, 0,
                  epoch=5, phase="writing", token=quarantined)
    _linearizable(new_primary_cid, nonce, 1,
                  epoch=2, phase="stable", token=None)
    _cas(new_primary_cid, nonce, 1, prior_epoch=2,
         prior_phase="stable", prior_token=None,
         next_phase="writing", next_token=attacker,
         token_to_match=attacker, expect_changed=True)
    _linearizable(new_primary_cid, nonce, 1,
                  epoch=3, phase="writing", token=attacker)
    _cas(new_primary_cid, nonce, 1, prior_epoch=3,
         prior_phase="writing", prior_token=attacker,
         next_phase="stable", next_token=None,
         token_to_match=None, expect_changed=True)
    _linearizable(new_primary_cid, nonce, 1,
                  epoch=4, phase="stable", token=None)
    _linearizable(new_primary_cid, nonce, 0,
                  epoch=5, phase="writing", token=quarantined)
    return {
        "synthetic_incomplete_epoch_survived_real_primary_failover": True,
        "synthetic_stale_owner_denied_after_election": True,
        "synthetic_automatic_quarantine_takeover_denied": True,
        "synthetic_independent_actor_commit_while_quarantined": True,
        "synthetic_real_linearizable_epoch_reads": True,
        "production_actor_epoch_migration_qualified": False,
        "production_backend_and_engine_writers_bound": False,
        "actual_cross_process_writer_registry_complete": False,
        "protected_jeeves_chat_qualified": False,
        "production_recovery_qualified": False,
        "release_authorized": False,
    }


def after_quorum_recovery(restored_primary_cid: str, nonce: str) -> dict[str, bool]:
    """Independent third physical primary checks actor custody after healing.

    The original WRITING actor remains quarantined across TWO separate
    primary elections and an observed complete loss of quorum. The other
    synthetic actor is independently permitted to complete a further
    monotonic writer epoch, without global auto-fencing bypass.
    """
    _hex(nonce)
    quarantined = _token(nonce, 2)
    stale = _token(nonce, 0)
    independent = _token(nonce, 1)
    _linearizable(restored_primary_cid, nonce, 0,
                  epoch=5, phase="writing", token=quarantined)
    _linearizable(restored_primary_cid, nonce, 1,
                  epoch=4, phase="stable", token=None)
    _cas(restored_primary_cid, nonce, 0,
         prior_epoch=4, prior_phase="stable", prior_token=None,
         next_phase="writing", next_token=stale,
         token_to_match=stale, expect_changed=False)
    _cas(restored_primary_cid, nonce, 0,
         prior_epoch=5, prior_phase="writing", prior_token=stale,
         next_phase="stable", next_token=None,
         token_to_match=None, expect_changed=False)
    _cas(restored_primary_cid, nonce, 1,
         prior_epoch=4, prior_phase="stable", prior_token=None,
         next_phase="writing", next_token=independent,
         token_to_match=independent, expect_changed=True)
    _linearizable(restored_primary_cid, nonce, 1,
                  epoch=5, phase="writing", token=independent)
    _cas(restored_primary_cid, nonce, 1,
         prior_epoch=5, prior_phase="writing", prior_token=independent,
         next_phase="stable", next_token=None,
         token_to_match=None, expect_changed=True)
    _linearizable(restored_primary_cid, nonce, 1,
                  epoch=6, phase="stable", token=None)
    _linearizable(restored_primary_cid, nonce, 0,
                  epoch=5, phase="writing", token=quarantined)
    return {
        "synthetic_quarantine_survived_complete_quorum_loss": True,
        "synthetic_stale_completion_denied_after_majority_restoration": True,
        "synthetic_independent_actor_monotonic_epoch_six": True,
        "synthetic_linearizable_witness_after_third_primary_election": True,
        "production_actor_quarantine_recovered": False,
        "production_migration_authorized": False,
        "actual_writer_registry_qualified": False,
        "release_authorized": False,
    }


__all__ = [
    "SyntheticEpochError", "SCHEMA", "before_failover", "after_failover",
    "after_quorum_recovery",
]
