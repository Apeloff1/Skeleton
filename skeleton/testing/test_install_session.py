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
        session.begin_phase("setup-runtime")
        phase=InstallPhase("setup-runtime",True,"existing")
        session.complete_phase(phase)
        session.begin_phase("start")
        started=InstallPhase("start",True,"started")
        session.complete_phase(started)
        session.finish(InstallReceipt(root,(phase,started)))
    result=s.inspect_session(directory,"one")
    assert result["outcome"]=="passed" and not result["active_or_interrupted"]
    assert result["attempt"]==2 and result["runtime_requalified"] is False
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
