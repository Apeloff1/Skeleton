"""Persistent installer phase custody and restart behavior."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

from skeleton.app import install_session as s
from skeleton.app.installer import InstallPhase,InstallReceipt

pytestmark=pytest.mark.skipif(os.name!="posix",reason="POSIX journal custody")
HEAD="a"*40


def options(**updates):
    result=dict.fromkeys(s._OPTIONS,False)
    result.update(start=True,production=True)
    result.update(updates)
    return result


def fixture(tmp_path,monkeypatch):
    root=tmp_path/"repo"
    root.mkdir()
    state=tmp_path/"custody"
    state.mkdir(mode=0o700)
    monkeypatch.setattr(s,"_current_source",lambda root,head:None)
    # Model private source custody without any credentials in the journal.
    monkeypatch.setattr(s,"_snapshot",lambda root: None if not (root/".env").exists()
                        else s._sha((root/".env").read_bytes()))
    return root,state


def setup(session,root):
    session.begin_phase("setup-runtime")
    (root/".env").write_text("PRIVATE_CONFIGURATION=not-for-receipts")
    phase=InstallPhase("setup-runtime",True,"raw detail not-for-receipts")
    session.complete_phase(phase)
    return phase


def test_interrupt_then_replay_existing_idempotent_pipeline(tmp_path,monkeypatch):
    root,directory=fixture(tmp_path,monkeypatch)
    with s.open_session(root,directory,"one",HEAD,options()) as session:
        setup(session,root)
        session.begin_phase("start")
        assert session.state.pending=="start"
    prior=s.inspect_session(directory,"one")
    assert prior["active_or_interrupted"] and prior["uncertain_phase"]=="start"
    with s.open_session(root,directory,"one",HEAD,options(),resume=True) as session:
        assert session.state.attempt==2
        phases=successful_pipeline(session,root)
        session.finish(InstallReceipt(root,tuple(phases)))
    result=s.inspect_session(directory,"one")
    assert result["outcome"]=="passed" and not result["active_or_interrupted"]
    assert result["attempt"]==2 and result["runtime_requalified"] is False
    assert result["last_interrupted_phase"]=="start"
    assert result["uncertain_phase"] is None
    records=[json.loads(path.read_bytes()) for path in directory.glob("install-one-*.json")]
    assert any(r["kind"]=="ATTEMPT_END" and r["data"]["outcome"]=="interrupted" for r in records)
    assert all("not-for-receipts" not in path.read_text() for path in directory.glob("*.json"))
    with pytest.raises(s.InstallSessionDenied):
        with s.open_session(root,directory,"one",HEAD,options(),resume=True):
            pytest.fail("passed session was replayed")


def test_ambiguous_setup_does_not_regenerate_secrets(tmp_path,monkeypatch):
    root,directory=fixture(tmp_path,monkeypatch)
    with s.open_session(root,directory,"one",HEAD,options()) as session:
        session.begin_phase("setup-runtime")
        (root/".env").write_text("preserve-created-credentials")
    with pytest.raises(s.InstallSessionDenied):
        with s.open_session(root,directory,"one",HEAD,options(),resume=True):
            pytest.fail("unobserved configuration change admitted")
    assert (root/".env").read_text()=="preserve-created-credentials"


@pytest.mark.parametrize("changed",["head","options","configuration","corrupt","missing","linked","wrong_mode"])
def test_changed_session_inputs_fail_closed(tmp_path,monkeypatch,changed):
    root,directory=fixture(tmp_path,monkeypatch)
    with s.open_session(root,directory,"one",HEAD,options()) as session:
        phase=setup(session,root)
        session.finish(InstallReceipt(root,(phase,InstallPhase("runtime-preflight",False,"fail"))))
    head=HEAD
    opts=options()
    paths=sorted(directory.glob("install-one-*.json"))
    if changed=="head":
        head="b"*40
    elif changed=="options":
        opts=options(hot=True)
    elif changed=="configuration":
        (root/".env").write_text("changed")
    elif changed=="corrupt":
        paths[1].write_text("{}")
    elif changed=="missing":
        paths[1].unlink()
    elif changed=="linked":
        target=tmp_path/"outside"
        target.write_bytes(paths[1].read_bytes())
        paths[1].unlink()
        paths[1].symlink_to(target)
    else:
        paths[1].chmod(0o644)
    with pytest.raises(s.InstallSessionDenied):
        with s.open_session(root,directory,"one",head,opts,resume=True):
            pytest.fail("changed session resumed")


def test_concurrent_install_different_session_same_checkout_denied(tmp_path,monkeypatch):
    root,directory=fixture(tmp_path,monkeypatch)
    with s.open_session(root,directory,"one",HEAD,options()):
        with pytest.raises(s.InstallSessionDenied):
            with s.open_session(root,directory,"two",HEAD,options()):
                pytest.fail("concurrent installer admitted")


def test_success_requires_no_unresolved_mutation(tmp_path,monkeypatch):
    root,directory=fixture(tmp_path,monkeypatch)
    with s.open_session(root,directory,"one",HEAD,options()) as session:
        phase=setup(session,root)
        session.begin_phase("start")
        with pytest.raises(s.InstallSessionDenied):
            session.finish(InstallReceipt(root,(phase,)))


def test_phase_fence_checks_source_before_mutation(tmp_path,monkeypatch):
    root,directory=fixture(tmp_path,monkeypatch)
    with s.open_session(root,directory,"one",HEAD,options()) as session:
        setup(session,root)
        (root/".env").write_text("foreign-change")
        with pytest.raises(s.InstallSessionDenied):
            session.begin_phase("start")
        assert session.state.pending is None


def test_partial_record_denies_recovery_instead_of_overwrite(tmp_path,monkeypatch):
    root,directory=fixture(tmp_path,monkeypatch)
    with s.open_session(root,directory,"one",HEAD,options()) as session:
        setup(session,root)
        name=s._filename("one",len(session.rows)+1)
        p=directory/name
        p.write_bytes(b"{")
        p.chmod(0o600)
    with pytest.raises(s.InstallSessionDenied):
        with s.open_session(root,directory,"one",HEAD,options(),resume=True):
            pytest.fail("partial record admitted")
    assert p.read_bytes()==b"{"


def test_no_new_session_when_directory_is_world_accessible(tmp_path,monkeypatch):
    root,directory=fixture(tmp_path,monkeypatch)
    directory.chmod(0o755)
    with pytest.raises(s.InstallSessionDenied):
        with s.open_session(root,directory,"one",HEAD,options()):
            pytest.fail("public journal directory accepted")
    assert not list(directory.iterdir())


def successful_pipeline(session,root,*,strict=False,start=True,python=False,notes=()):
    phases=[
        InstallPhase("preload",True,"host"),
        InstallPhase("setup-runtime",True,"config"),
        *[InstallPhase("configuration-note",True,note,required=False) for note in notes],
        InstallPhase("python-install",True,"python",required=python),
        InstallPhase("runtime-preflight",True,"preflight"),
        InstallPhase("compose-config",True,"compose"),
    ]
    if start:
        phases.extend(InstallPhase(name,True,"live")
                      for name in ("start","readiness","critical-api-routes"))
    if strict:
        phases.append(InstallPhase("strict-live-qualification",True,"strict"))
    for phase in phases:
        if phase.name in s._INTENTS and (phase.name!="python-install" or python):
            session.begin_phase(phase.name)
        if phase.name=="setup-runtime" and not (root/".env").exists():
            (root/".env").write_text("private")
        session.complete_phase(phase)
    return phases


@pytest.mark.parametrize("start,strict,python",[
    (False,False,False),(False,False,True),(True,False,False),
    (True,True,True),(True,True,False),
])
def test_complete_selected_install_path(tmp_path,monkeypatch,start,strict,python):
    root,directory=fixture(tmp_path,monkeypatch)
    opts=options(start=start,require_strict=strict,install_python=python)
    with s.open_session(root,directory,"one",HEAD,opts) as session:
        phases=successful_pipeline(session,root,start=start,strict=strict,python=python,
                                   notes=("redacted", "also redacted"))
        session.finish(InstallReceipt(root,tuple(phases)))
    result=s.inspect_session(directory,"one")
    assert result["outcome"]=="passed"
    assert result["runtime_requalified"] is False
    assert result["release_qualified"] is False


@pytest.mark.parametrize("missing",[
    "preload","setup-runtime","python-install","runtime-preflight",
    "compose-config","start","readiness","critical-api-routes","strict-live-qualification",
])
def test_successful_reducer_rejects_every_missing_required_observation(missing):
    opts=options(require_strict=True,install_python=True)
    names=("preload","setup-runtime","python-install","runtime-preflight",
           "compose-config","start","readiness","critical-api-routes","strict-live-qualification")
    results=tuple((name,True,True) for name in names if name!=missing)
    assert not s._successful_phases(opts,results)


@pytest.mark.parametrize("mutation",["duplicate","out_of_order","downgraded",
                                      "optional_failure","extra","missing_note_authority"])
def test_success_path_refuses_divergent_transcript(mutation):
    opts=options(install_python=True)
    results=[(n,True,True) for n in ("preload","setup-runtime","python-install",
             "runtime-preflight","compose-config","start","readiness","critical-api-routes")]
    if mutation=="duplicate":
        results.insert(1,results[0])
    elif mutation=="out_of_order":
        results[-1],results[-2]=results[-2],results[-1]
    elif mutation=="downgraded":
        results[2]=("python-install",True,False)
    elif mutation=="optional_failure":
        results.insert(2,("configuration-note",False,False))
    elif mutation=="extra":
        results.append(("strict-live-qualification",True,True))
    else:
        results.insert(2,("configuration-note",True,True))
    assert not s._successful_phases(opts,tuple(results))


def test_truncated_positive_receipt_cannot_publish_terminal_success(tmp_path,monkeypatch):
    root,directory=fixture(tmp_path,monkeypatch)
    with s.open_session(root,directory,"one",HEAD,options()) as session:
        phase=setup(session,root)
        with pytest.raises(s.InstallSessionDenied,match="incomplete or inconsistent"):
            session.finish(InstallReceipt(root,(phase,)))
    assert s.inspect_session(directory,"one")["active_or_interrupted"]


def test_empty_receipt_is_not_success(tmp_path):
    assert InstallReceipt(tmp_path,()).ok is False


def test_receipt_must_belong_to_session_checkout(tmp_path,monkeypatch):
    root,directory=fixture(tmp_path,monkeypatch)
    with s.open_session(root,directory,"one",HEAD,options()) as session:
        phases=successful_pipeline(session,root)
        with pytest.raises(s.InstallSessionDenied,match="checkout identity"):
            session.finish(InstallReceipt(tmp_path,tuple(phases)))


def test_interrupted_terminal_retains_uncertain_phase(tmp_path,monkeypatch):
    root,directory=fixture(tmp_path,monkeypatch)
    with s.open_session(root,directory,"one",HEAD,options()) as session:
        setup(session,root)
        session.begin_phase("start")
        session._append("ATTEMPT_END",{"outcome":"interrupted"})
    result=s.inspect_session(directory,"one")
    assert result["outcome"]=="interrupted"
    assert result["uncertain_phase"]=="start"
    assert result["last_interrupted_phase"]=="start"
