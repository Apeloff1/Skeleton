"""Source-only hostile qualification of synthetic Mongo writer-epoch CAS.

Tests never create containers, connect to Mongo, read application actor IDs,
grant epoch migration, or mutate production source stores. The integration
harness proves the optional check executes at the intended Docker failover
boundary and cannot turn forged evidence into a successful receipt.
"""
from __future__ import annotations

import copy
import inspect
import json

import pytest

from scripts import local_ai_synthetic_epoch_fence as e
from scripts import qualify_local_ai_mongo_quorum_docker as q
from skeleton.testing.test_local_ai_mongo_quorum_docker import (
    _pipeline, _qualify, IDS,
)

NONCE = "a" * 32
CID = IDS[0]


@pytest.mark.parametrize("nonce", [
    "", "abc", "A" * 32, "g" * 32, "a" * 33, None, True,
])
def test_synthetic_nonce_never_accepts_untrusted_actor_reference(nonce):
    with pytest.raises(e.SyntheticEpochError):
        e._hex(nonce)


@pytest.mark.parametrize("actor", [-1, 2, True, "0", None])
def test_synthetic_actor_outside_fixed_two_actor_test_scope_denied(actor):
    with pytest.raises(e.SyntheticEpochError):
        e._key(NONCE, actor)


@pytest.mark.parametrize("writer", [-1, 4, True, "1", None])
def test_synthetic_writer_identity_is_exact_numeric_test_only(writer):
    with pytest.raises(e.SyntheticEpochError):
        e._token(NONCE, writer)


def test_disposable_actor_keys_tokens_are_deterministic_but_separated():
    assert e._key(NONCE, 0) == e._key(NONCE, 0)
    assert e._key(NONCE, 0) != e._key(NONCE, 1)
    assert e._token(NONCE, 0) != e._token(NONCE, 1)
    assert len(e._token(NONCE, 0)) == 64
    assert "tenant" not in e._key(NONCE, 0)
    assert "owner" not in e._key(NONCE, 1)


def _cas_answer(*, changed=True, epoch=3, phase="writing",
                token_matches=True, concern_error=False, ok=True):
    return {
        "ok": ok, "changed": changed, "epoch": epoch,
        "phase": phase, "token_matches": token_matches,
        "concern_error": concern_error,
    }


@pytest.mark.parametrize("bad", [
    {"ok": False},
    {"changed": False},
    {"epoch": 4},
    {"epoch": True},
    {"phase": "stable"},
    {"token_matches": False},
    {"concern_error": True},
    {"extra": "raw payload"},
])
def test_majority_cas_requires_exact_ack_and_matched_owner_fields(bad):
    response = {**_cas_answer(), **bad}
    with pytest.raises(e.SyntheticEpochError):
        e._expect(response, updated=True, epoch=3,
                  phase="writing", matching_token=True)


def test_negative_cas_must_return_no_value_not_forged_write():
    e._expect(_cas_answer(changed=False, epoch=-1, phase="absent",
                          token_matches=False),
              updated=False, epoch=-1, phase="absent",
              matching_token=False)
    with pytest.raises(e.SyntheticEpochError):
        e._expect(_cas_answer(changed=True, epoch=-1, phase="absent",
                              token_matches=False),
                  updated=False, epoch=-1, phase="absent",
                  matching_token=False)


@pytest.mark.parametrize("before,phase,old,after,new", [
    (1, "stable", None, "writing", "a" * 64),
    (2, "writing", "a" * 64, "stable", None),
    (3, "stable", None, "writing", "a" * 64),
    (2, "stable", "a" * 64, "writing", "b" * 64),
    (3, "writing", "a" * 64, "stable", "b" * 64),
    (2, "stable", None, "stable", None),
    (True, "stable", None, "writing", "a" * 64),
])
def test_no_bad_odd_even_writer_epoch_can_reach_mongo(
        monkeypatch, before, phase, old, after, new):
    calls = []
    monkeypatch.setattr(e, "_shell", lambda *args, **kwargs:
                        calls.append(args) or _cas_answer())
    with pytest.raises(e.SyntheticEpochError, match="transition"):
        e._cas(CID, NONCE, 0,
               prior_epoch=before, prior_phase=phase,
               prior_token=old, next_phase=after,
               next_token=new, token_to_match=None,
               expect_changed=True)
    assert calls == []


def test_find_and_modify_uses_w_majority_j_true_and_exact_cas(monkeypatch):
    messages = []
    token = e._token(NONCE, 0)
    monkeypatch.setattr(e, "_shell", lambda cid, js:
                        messages.append((cid, js)) or _cas_answer())
    e._cas(CID, NONCE, 0, prior_epoch=2,
           prior_phase="stable", prior_token=None,
           next_phase="writing", next_token=token,
           token_to_match=token, expect_changed=True)
    assert len(messages) == 1
    command = messages[0][1]
    assert "findAndModify" in command
    assert "epoch:2" in command
    assert 'phase:"stable"' in command
    assert "writer_token:null" in command
    assert "$inc:{epoch:1}" in command
    assert 'w:"majority",j:true,wtimeout:10000' in command
    assert "maxTimeMS:15000" in command
    assert e._key(NONCE, 0) in command
    assert messages[0][0] == CID
    assert "skeleton_guarded_source" not in command


def test_unique_synthetic_document_creation_requires_majority_journal_ack(
        monkeypatch):
    captured = []
    monkeypatch.setattr(e, "_shell", lambda cid, js:
                        captured.append(js) or {
                            "ok": True, "inserted": True,
                            "write_error": False, "concern_error": False,
                        })
    e._create(CID, NONCE, 1)
    assert len(captured) == 1
    assert 'insert:"synthetic_canonical_epoch"' in captured[0]
    assert 'w:"majority",j:true' in captured[0]
    assert e.DB in captured[0]
    assert "production" not in captured[0].lower()


@pytest.mark.parametrize("reply", [
    {}, {"ok": True, "inserted": True, "write_error": False,
         "concern_error": True},
    {"ok": True, "inserted": False, "write_error": False,
     "concern_error": False},
    {"ok": True, "inserted": True, "write_error": False,
     "concern_error": False, "host": "secret"},
])
def test_initialization_cannot_accept_unacknowledged_or_extra_proof(
        monkeypatch, reply):
    monkeypatch.setattr(e, "_shell", lambda *args: reply)
    with pytest.raises(e.SyntheticEpochError):
        e._create(CID, NONCE, 0)


def test_primary_linearizable_read_proves_exact_actor_token(monkeypatch):
    observed = []
    monkeypatch.setattr(e, "_shell", lambda cid, js:
                        observed.append(js) or {
                            "ok": True, "exactly_one": True,
                            "epoch_matches": True, "phase_matches": True,
                            "token_matches": True,
                        })
    e._linearizable(CID, NONCE, 0,
                    epoch=5, phase="writing",
                    token=e._token(NONCE, 2))
    assert len(observed) == 1
    assert 'readConcern:{level:"linearizable"}' in observed[0]
    assert "maxTimeMS:5000" in observed[0]
    assert "getSiblingDB" in observed[0]


@pytest.mark.parametrize("reply", [
    {"ok": True, "exactly_one": True, "epoch_matches": True,
     "phase_matches": True, "token_matches": False},
    {"ok": True, "exactly_one": True, "epoch_matches": False,
     "phase_matches": True, "token_matches": True},
    {"ok": True, "exactly_one": True, "epoch_matches": True,
     "phase_matches": False, "token_matches": True},
    {"ok": True, "exactly_one": False, "epoch_matches": True,
     "phase_matches": True, "token_matches": True},
    {"ok": False, "exactly_one": True, "epoch_matches": True,
     "phase_matches": True, "token_matches": True},
    {"ok": True, "exactly_one": True, "epoch_matches": True,
     "phase_matches": True, "token_matches": True, "unexpected": 1},
])
def test_linearizable_witness_rejects_partial_or_forged_replay(
        monkeypatch, reply):
    monkeypatch.setattr(e, "_shell", lambda *args: reply)
    with pytest.raises(e.SyntheticEpochError):
        e._linearizable(CID, NONCE, 0, epoch=2,
                        phase="stable", token=None)


def test_pre_failover_protocol_keeps_unfinished_writer_odd(monkeypatch):
    steps = []
    monkeypatch.setattr(e, "_create", lambda cid, n, actor:
                        steps.append(("create", actor)))
    monkeypatch.setattr(e, "_linearizable",
                        lambda cid, n, actor, **kw:
                        steps.append(("read", actor, kw["epoch"], kw["phase"])))
    monkeypatch.setattr(e, "_cas",
                        lambda cid, n, actor, **kw:
                        steps.append(("cas", actor,
                                      kw["prior_epoch"], kw["expect_changed"])))
    result = e.before_failover(CID, NONCE)
    assert all(value is True for value in result.values())
    assert steps[:2] == [("create", 0), ("create", 1)]
    assert ("cas", 0, 2, False) in steps
    assert ("cas", 0, 3, False) in steps
    assert ("cas", 0, 3, True) in steps
    assert steps[-1] == ("read", 0, 5, "writing")
    assert all(actor != 1 for _, actor, *rest in steps[2:])


def test_post_failover_source_quarantine_and_independent_actor(monkeypatch):
    steps = []
    monkeypatch.setattr(e, "_linearizable",
                        lambda cid, n, actor, **kw:
                        steps.append(("read", actor, kw["epoch"], kw["phase"])))
    monkeypatch.setattr(e, "_cas",
                        lambda cid, n, actor, **kw:
                        steps.append(("cas", actor,
                                      kw["prior_epoch"], kw["expect_changed"])))
    result = e.after_failover(CID, NONCE)
    assert result["synthetic_incomplete_epoch_survived_real_primary_failover"] is True
    assert result["production_backend_and_engine_writers_bound"] is False
    assert result["release_authorized"] is False
    assert ("cas", 0, 4, False) in steps
    assert ("cas", 0, 5, False) in steps
    assert ("cas", 1, 2, True) in steps
    assert ("cas", 1, 3, True) in steps
    assert steps[-1] == ("read", 0, 5, "writing")


def _epoch_before_receipt():
    return {
        "synthetic_writer_stable_to_writing_majority_cas": True,
        "synthetic_competing_writer_refused": True,
        "synthetic_wrong_token_completion_refused": True,
        "synthetic_writer_completed_stable_even_epoch": True,
        "synthetic_unfinished_writer_quarantined_before_failover": True,
    }


def _epoch_after_receipt():
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



def _epoch_final_receipt():
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


def test_quorum_recovery_source_refuses_actor_zero_takeover(
        monkeypatch):
    steps = []
    monkeypatch.setattr(e, "_linearizable",
                        lambda cid, nonce, actor, **kw:
                        steps.append(("read", actor, kw["epoch"], kw["phase"])))
    monkeypatch.setattr(e, "_cas",
                        lambda cid, nonce, actor, **kw:
                        steps.append(("cas", actor,
                                      kw["prior_epoch"], kw["expect_changed"])))
    result = e.after_quorum_recovery(CID, NONCE)
    assert result == _epoch_final_receipt()
    assert steps[0] == ("read", 0, 5, "writing")
    assert ("cas", 0, 4, False) in steps
    assert ("cas", 0, 5, False) in steps
    assert ("cas", 1, 4, True) in steps
    assert ("cas", 1, 5, True) in steps
    assert ("read", 1, 6, "stable") in steps
    assert steps[-1] == ("read", 0, 5, "writing")



def test_host_opt_in_epoch_protocol_between_real_elections_and_cleanup(
        monkeypatch):
    steps = _pipeline(monkeypatch)
    monkeypatch.setattr(e, "before_failover",
                        lambda cid, n: steps.append("epoch-before") or
                        _epoch_before_receipt())
    monkeypatch.setattr(e, "after_failover",
                        lambda cid, n: steps.append("epoch-after") or
                        _epoch_after_receipt())
    monkeypatch.setattr(e, "after_quorum_recovery",
                        lambda cid, n: steps.append("epoch-final") or
                        _epoch_final_receipt())
    result = _qualify(allow_synthetic_writes=True, exercise_writer_epoch=True)
    assert result["synthetic_actor_epoch_cas_executed"] is True
    assert result["synthetic_cross_process_stale_writer_denied"] is True
    assert result["synthetic_incomplete_epoch_quarantined_across_failover"] is True
    assert result["synthetic_quarantined_actor_survived_full_quorum_loss"] is True
    assert result["synthetic_healed_independent_actor_epoch_six"] is True
    assert result["independent_synthetic_actor_epoch_completed"] is True
    assert result["production_writer_epoch_enrollment_qualified"] is False
    assert steps.index("journal-default") < steps.index("epoch-before")
    assert steps.index("epoch-before") < steps.index("write1")
    assert steps.index("write1") < steps.index("epoch-after")
    assert steps.index("epoch-after") < steps.index("write2")
    assert steps.index("write3") < steps.index("epoch-final")
    assert steps.index("epoch-final") < steps.index("cleanup")
    assert steps[-1] == "cleanup"


def test_host_without_explicit_epoch_flag_does_not_access_extra_source(
        monkeypatch):
    steps = _pipeline(monkeypatch)
    monkeypatch.setattr(e, "before_failover", lambda *args:
                        pytest.fail("opt-in synthetic epoch is not requested"))
    monkeypatch.setattr(e, "after_failover", lambda *args:
                        pytest.fail("opt-in synthetic epoch is not requested"))
    monkeypatch.setattr(e, "after_quorum_recovery", lambda *args:
                        pytest.fail("opt-in synthetic epoch is not requested"))
    result = _qualify(allow_synthetic_writes=True, exercise_writer_epoch=False)
    assert result["synthetic_actor_epoch_cas_executed"] is False
    assert result["production_writer_epoch_enrollment_qualified"] is False
    assert steps[-1] == "cleanup"


@pytest.mark.parametrize("poison", [
    {"synthetic_writer_stable_to_writing_majority_cas": False},
    {"synthetic_wrong_token_completion_refused": "yes"},
    {"extra": "unsafe"},
])
def test_host_cannot_accept_forged_pre_failover_epoch_receipt(
        monkeypatch, poison):
    steps = _pipeline(monkeypatch)
    monkeypatch.setattr(e, "before_failover", lambda *args:
                        {**_epoch_before_receipt(), **poison})
    with pytest.raises(q.SyntheticMongoError, match="failed closed"):
        _qualify(allow_synthetic_writes=True, exercise_writer_epoch=True)
    assert steps[-1] == "cleanup"


@pytest.mark.parametrize("poison", [
    {"synthetic_stale_owner_denied_after_election": False},
    {"production_backend_and_engine_writers_bound": True},
    {"protected_jeeves_chat_qualified": True},
    {"extra": "unsafe"},
])
def test_host_rejects_forged_post_failover_epoch_authority(
        monkeypatch, poison):
    steps = _pipeline(monkeypatch)
    monkeypatch.setattr(e, "before_failover", lambda *args:
                        _epoch_before_receipt())
    monkeypatch.setattr(e, "after_failover", lambda *args:
                        {**_epoch_after_receipt(), **poison})
    with pytest.raises(q.SyntheticMongoError, match="failed closed"):
        _qualify(allow_synthetic_writes=True, exercise_writer_epoch=True)
    assert steps[-1] == "cleanup"


def test_synthetic_epoch_has_no_production_endpoint_or_unsafe_lease_takeover():
    source = inspect.getsource(e)
    for forbidden in (
        "MONGO_URL", "SKL_MONGO_URI", "MongoClient(", "replSetInitiate",
        "docker volume", "dropDatabase", "update_many(", "replace_one(",
        "findOneAndReplace", "production_writer_bound=True",
    ):
        assert forbidden not in source
    assert "majority" in source
    assert "linearizable" in source
    assert "findAndModify" in source
    assert "wtimeout:10000" in source

@pytest.mark.parametrize("bad_cid", [
    "", "0" * 63, "0" * 65, "g" * 64, "docker", None,
])
def test_epoch_shell_denies_container_substitution_before_docker(
        monkeypatch, bad_cid):
    calls = []
    monkeypatch.setattr(e.physical, "_shell",
                        lambda *args: calls.append(args) or {})
    with pytest.raises(e.SyntheticEpochError, match="scope"):
        e._shell(bad_cid, "return {ok:true};")
    assert calls == []


def test_epoch_shell_uses_exact_docker_identity_and_denies_driver_raw_error(
        monkeypatch):
    seen = []
    def fail(cid, js):
        seen.append(cid)
        raise q.SyntheticMongoError("private URI TOKEN")
    monkeypatch.setattr(e.physical, "_shell", fail)
    with pytest.raises(e.SyntheticEpochError) as error:
        e._shell(CID, "return {ok:true};")
    assert seen == [CID]
    assert "private URI" not in str(error.value)
    assert "TOKEN" not in str(error.value)


@pytest.mark.parametrize("bad", [False, True, "1", 1, None, [], {}])
def test_writer_epoch_extended_approval_does_not_accept_truthiness(
        monkeypatch, bad):
    monkeypatch.setattr(q.binding, "verify_binding",
                        lambda *a, **kw: pytest.fail(
                            "invalid approval reached Docker/source archive"))
    with pytest.raises(q.SyntheticMongoError):
        _qualify(allow_synthetic_writes=True, exercise_writer_epoch=bad)


def test_synthetic_epoch_cas_never_logs_tokens_or_production_identity(
        monkeypatch, capsys):
    token = e._token(NONCE, 0)
    recorded = []
    monkeypatch.setattr(e, "_shell", lambda cid, command:
                        recorded.append(command) or _cas_answer())
    e._cas(CID, NONCE, 0, prior_epoch=2,
           prior_phase="stable", prior_token=None,
           next_phase="writing", next_token=token,
           token_to_match=token, expect_changed=True)
    output = capsys.readouterr()
    assert output.out == output.err == ""
    assert len(recorded) == 1
    assert token in recorded[0]
    assert "mongodb://" not in recorded[0]
    assert "MONGO_URL" not in recorded[0]


def test_host_epoch_fail_closed_when_real_source_command_fails(monkeypatch):
    steps = _pipeline(monkeypatch)
    def fail(*args):
        raise e.SyntheticEpochError("synthetic epoch unavailable")
    monkeypatch.setattr(e, "before_failover", fail)
    with pytest.raises(q.SyntheticMongoError, match="failed closed"):
        _qualify(allow_synthetic_writes=True, exercise_writer_epoch=True)
    assert steps[-1] == "cleanup"


def test_source_protocol_is_disposable_quarantine_not_actor_migration():
    before_source = inspect.getsource(e.before_failover)
    after_source = inspect.getsource(e.after_failover)
    assert "next_phase=\"writing\"" in before_source
    assert "_linearizable" in after_source
    assert "phase=\"writing\"" in after_source
    assert "next_phase=\"stable\"" in after_source
    assert "provision_migration_epoch" not in (before_source + after_source)
    assert "delete" not in (before_source + after_source)
    assert "retryWrites" not in (before_source + after_source)

@pytest.mark.parametrize("poison", [
    {"synthetic_quarantine_survived_complete_quorum_loss": False},
    {"synthetic_independent_actor_monotonic_epoch_six": "yes"},
    {"production_migration_authorized": True},
    {"production_actor_quarantine_recovered": True},
    {"extra": "untrusted"},
])
def test_host_rejects_forged_healed_quorum_epoch_receipt(
        monkeypatch, poison):
    steps = _pipeline(monkeypatch)
    monkeypatch.setattr(e, "before_failover", lambda *args:
                        _epoch_before_receipt())
    monkeypatch.setattr(e, "after_failover", lambda *args:
                        _epoch_after_receipt())
    monkeypatch.setattr(e, "after_quorum_recovery", lambda *args:
                        {**_epoch_final_receipt(), **poison})
    with pytest.raises(q.SyntheticMongoError, match="failed closed"):
        _qualify(allow_synthetic_writes=True, exercise_writer_epoch=True)
    assert steps[-1] == "cleanup"
