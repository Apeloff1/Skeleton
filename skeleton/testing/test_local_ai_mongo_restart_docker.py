"""No-Docker source tests for disposable physical Mongo crash/restart harness.

Pure source tests verify the exact Docker argv, private scratch admission,
untrusted metadata denial, synthetic SIGKILL/restart/recreate sequencing,
cleanup and hostile failure receipts. No Docker daemon, Mongo, network,
production volume, API credential or real model is used by these tests.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

import pytest

from scripts import qualify_local_ai_mongo_restart_docker as probe


SCOPE = "skl-mongo-r-1a2b3c4d5e6f7890"
IMAGE = "sha256:" + "a" * 64
CID1 = "b" * 64
CID2 = "c" * 64
DIGEST = "d" * 64


@pytest.fixture
def scratch():
    folder = probe._scratch(SCOPE)
    yield folder
    if folder.exists():
        shutil.rmtree(folder)


def _inspect_doc(root, cid=CID1, *, running=True, image=IMAGE,
                 scope=SCOPE):
    uid, gid = os.getuid(), os.getgid()
    tmpfs = {
        path: f"rw,nosuid,nodev,uid={uid},gid={gid},mode=0700,size=16777216"
        for path in ("/tmp", "/data/configdb")
    }
    return {
        "Id": cid, "Name": "/" + scope + "-node", "Image": image,
        "Config": {
            "Image": image, "User": f"{uid}:{gid}",
            "Labels": {"skeleton.synthetic-mongo-recovery": scope},
            "ExposedPorts": {"27017/tcp": {}},
        },
        "HostConfig": {
            "ReadonlyRootfs": True,
            "NetworkMode": "none", "PortBindings": {},
            "CapDrop": ["ALL"], "CapAdd": None,
            "SecurityOpt": ["no-new-privileges"],
            "Privileged": False,
            "Memory": 805306368, "MemorySwap": 805306368,
            "NanoCpus": 1000000000, "PidsLimit": 192,
            "Tmpfs": tmpfs,
        },
        "Mounts": [{
            "Type": "bind", "Source": str(root / "data"),
            "Destination": "/data/db", "RW": True,
        }],
        "State": {"Running": running},
        "NetworkSettings": {
            "Networks": {"none": {}},
            "Ports": {"27017/tcp": None},
        },
    }


def test_actual_generated_scope_root_private_identity_and_nonproduction(scratch):
    assert scratch.parent == Path("/tmp")
    assert scratch.name.startswith(SCOPE + "-")
    probe._validate_scratch(scratch, SCOPE)
    assert (scratch / "data").is_dir()
    assert (scratch / ".owner").read_text() == SCOPE
    assert (scratch.stat().st_mode & 0o077) == 0
    assert ((scratch / "data").stat().st_mode & 0o077) == 0


def test_exact_immutable_docker_run_has_one_generated_bind_and_no_network(scratch):
    argv = probe._run_argv(SCOPE, IMAGE, scratch)
    probe._admit(argv, scope=SCOPE, image=IMAGE, root=scratch)
    assert argv[0:5] == ["docker", "run", "-d", "--pull", "never"]
    assert argv[argv.index("--network")+1] == "none"
    assert argv[argv.index("--read-only")] == "--read-only"
    assert "--cap-drop" in argv and "ALL" in argv
    assert "--security-opt" in argv
    assert "no-new-privileges" in argv
    assert "--memory" in argv and "--memory-swap" in argv
    assert "--cpus" in argv and "--pids-limit" in argv
    assert argv.count("--mount") == 1
    assert argv[argv.index("--mount")+1] == (
        f"type=bind,source={scratch / 'data'},target=/data/db"
    )
    assert "--volume" not in argv and "-v" not in argv
    assert "--publish" not in argv and "-p" not in argv
    assert "--env-file" not in argv
    assert "--privileged" not in argv
    assert argv[-1] == "diagnosticDataCollectionEnabled=false"
    assert len(argv) <= 64


@pytest.mark.parametrize("mutation", [
    lambda x: x.__setitem__(x.index("none"), "host"),
    lambda x: x.__setitem__(x.index("never"), "always"),
    lambda x: x.__setitem__(x.index(IMAGE), "mongo:latest"),
    lambda x: x.__setitem__(x.index("--read-only"), "--privileged"),
    lambda x: x.__setitem__(x.index("--mount")+1,
                          "type=bind,source=/var/lib/docker/volumes/production,target=/data/db"),
    lambda x: x.extend(["-p", "27017:27017"]),
    lambda x: x.extend(["--env-file", "/home/user/.env"]),
    lambda x: x.__setitem__(x.index("--pids-limit")+1, "unlimited"),
    lambda x: x.__setitem__(x.index("--memory")+1, "0"),
])
def test_hostile_docker_run_argv_refused_without_subprocess(scratch, mutation):
    argv = probe._run_argv(SCOPE, IMAGE, scratch)
    mutation(argv)
    with pytest.raises(probe.SyntheticRestartError):
        probe._admit(argv, scope=SCOPE, image=IMAGE, root=scratch)


@pytest.mark.parametrize("argv", [
    ["docker", "pull", "mongo:latest"],
    ["docker", "volume", "rm", "production"],
    ["docker", "network", "connect", "host", CID1],
    ["docker", "run", "--network", "host", IMAGE],
    ["docker", "rm", "--force", "unsafe-container"],
    ["docker", "kill", "--signal=KILL", "unsafe"],
    ["docker", "inspect", "production"],
])
def test_unrelated_docker_commands_are_never_admitted(scratch, argv):
    with pytest.raises(probe.SyntheticRestartError):
        probe._admit(argv, scope=SCOPE, image=IMAGE, root=scratch)


def test_live_container_inspection_has_exact_synthetic_mount(scratch, monkeypatch):
    monkeypatch.setattr(probe, "_call", lambda *a, **kw:
                        json.dumps(_inspect_doc(scratch)))
    probe._inspect(CID1, scope=SCOPE, image=IMAGE, root=scratch, running=True)
    with pytest.raises(probe.SyntheticRestartError):
        probe._inspect(CID1, scope=SCOPE, image=IMAGE, root=scratch, running=False)


@pytest.mark.parametrize("poison", [
    {"Image": "sha256:" + "f" * 64},
    {"Name": "/production-mongo"},
    {"Config": {"Image": IMAGE, "User": "0:0", "Labels": {}}},
    {"HostConfig": {"NetworkMode": "host"}},
    {"Mounts": [{"Type": "volume", "Name": "prod-volume"}]},
    {"NetworkSettings": {"Networks": {"host": {}}, "Ports": {}}},
    {"State": {"Running": False}},
])
def test_forged_docker_inspect_cannot_admit_synthetic_container(
        scratch, monkeypatch, poison):
    doc = {**_inspect_doc(scratch), **poison}
    monkeypatch.setattr(probe, "_call", lambda *a, **kw: json.dumps(doc))
    with pytest.raises(probe.SyntheticRestartError):
        probe._inspect(CID1, scope=SCOPE, image=IMAGE, root=scratch, running=True)


@pytest.mark.parametrize("field,bad", [
    ("Memory", 0), ("MemorySwap", 0), ("NanoCpus", 0), ("PidsLimit", 0),
    ("Memory", 1_000_000_000), ("NanoCpus", 2_000_000_000),
    ("PidsLimit", 1024),
])
def test_mutated_cgroup_limit_cannot_pass_inspect(
        scratch, monkeypatch, field, bad):
    doc = _inspect_doc(scratch)
    doc["HostConfig"][field] = bad
    monkeypatch.setattr(probe, "_call", lambda *a, **kw: json.dumps(doc))
    with pytest.raises(probe.SyntheticRestartError):
        probe._inspect(CID1, scope=SCOPE, image=IMAGE, root=scratch, running=True)


@pytest.mark.parametrize("mutation", [
    lambda d: d["HostConfig"]["Tmpfs"].update({"/unlisted": "rw"}),
    lambda d: d["HostConfig"]["Tmpfs"].update(
        {"/tmp": "rw,nosuid,nodev,uid=99999,gid=99999,mode=0700,size=16777216"}),
    lambda d: d["HostConfig"]["Tmpfs"].update(
        {"/tmp": "rw,nosuid,nodev,mode=0700,size=16777216"}),
    lambda d: d["HostConfig"]["Tmpfs"].update(
        {"/tmp": "rw,nosuid,nodev,uid=99999,gid=99999,mode=0700,size=999"}),
])
def test_tmpfs_owner_or_extra_mount_must_not_drift(
        scratch, monkeypatch, mutation):
    doc = _inspect_doc(scratch)
    mutation(doc)
    monkeypatch.setattr(probe, "_call", lambda *a, **kw: json.dumps(doc))
    with pytest.raises(probe.SyntheticRestartError):
        probe._inspect(CID1, scope=SCOPE, image=IMAGE, root=scratch, running=True)


def test_cleanup_only_accepts_exact_scoped_image_and_scratch(scratch):
    good = _inspect_doc(scratch)
    assert probe._owned_inspection(
        good, cid=CID1, scope=SCOPE, image=IMAGE, root=scratch
    ) is True
    for poisoned in (
        {"Image": "sha256:"+"f"*64},
        {"Name": "/other"},
        {"Mounts": [{"Type":"bind", "Source": "/home/user/production",
                     "Destination": "/data/db", "RW": True}]},
        {"HostConfig": {"NetworkMode": "host"}},
    ):
        doc = {**good, **poisoned}
        assert not probe._owned_inspection(
            doc, cid=CID1, scope=SCOPE, image=IMAGE, root=scratch
        )


def test_mongosh_command_receipts_are_bounded_and_do_not_echo_token(
        scratch, monkeypatch):
    calls = []
    def shell(argv, **kwargs):
        calls.append(argv[-1])
        if "documents:" in argv[-1]:
            return 'SKLPROBE:{"ack":true}'
        if "firstBatch" in argv[-1]:
            return 'SKLPROBE:{"ok":true,"count":1,"matched":true}'
        return 'SKLPROBE:{"ready":true}'
    monkeypatch.setattr(probe, "_call", shell)
    token = "f"*32
    probe._write(CID1, token, scope=SCOPE, image=IMAGE, root=scratch)
    probe._read(CID1, token, scope=SCOPE, image=IMAGE, root=scratch)
    assert len(calls) == 2
    assert "w:1,j:true" in calls[0]
    assert "readConcern:{level:'local'}" in calls[1]


def test_raw_subprocess_error_is_redacted(scratch, monkeypatch):
    class Failed:
        returncode = 42
        stdout = ""
        stderr = "mongodb://real-user:PRIVATE@production-host"
    monkeypatch.setattr(probe.subprocess, "run", lambda *a, **kw: Failed())
    with pytest.raises(probe.SyntheticRestartError) as error:
        probe._call(
            probe._run_argv(SCOPE, IMAGE, scratch),
            scope=SCOPE, image=IMAGE, root=scratch,
        )
    assert "PRIVATE" not in str(error.value)


def test_private_scratch_world_readable_or_foreign_marker_denied(scratch):
    marker = scratch / ".owner"
    marker.write_text("wrong")
    with pytest.raises(probe.SyntheticRestartError):
        probe._validate_scratch(scratch, SCOPE)
    marker.write_text(SCOPE)
    marker.chmod(0o600)
    (scratch / "data").chmod(0o755)
    with pytest.raises(probe.SyntheticRestartError):
        probe._validate_scratch(scratch, SCOPE)


def test_generated_scratch_does_not_delete_user_added_unexpected_root_member(scratch):
    injected = scratch / "private-unexpected"
    injected.write_text("SYNTHETIC TEST FILE")
    with pytest.raises(probe.SyntheticRestartError):
        probe._validate_scratch(scratch, SCOPE)


def _fake_runtime(monkeypatch, *, fail_second_read=False):
    receipts = {
        "images": [{"service": "mongo", "image_id": IMAGE}],
        "all_four_image_ids_installed": True,
        "actual_overlay_render_verified": True,
    }
    monkeypatch.setattr(probe.binding, "verify_binding",
                        lambda *a, **kw: copy.deepcopy(receipts))
    monkeypatch.setattr(probe.quorum, "_local_daemon", lambda: None)
    state = {"nodes": {}, "created": [], "root": None,
             "token": None, "reads": 0, "events": []}

    def fake_call(argv, *, scope, image, root, **kwargs):
        probe._admit(argv, scope=scope, image=image, root=root)
        state["root"] = root
        op = argv[1]
        state["events"].append(op)
        if op == "run":
            cid = CID1 if not state["created"] else CID2
            state["created"].append(cid)
            state["nodes"][cid] = True
            return cid
        if op == "inspect":
            cid = argv[-1]
            if cid not in state["nodes"]:
                return ""
            return json.dumps(_inspect_doc(
                root, cid=cid, running=state["nodes"][cid],
                image=image, scope=scope,
            ))
        if op == "exec":
            cmd = argv[-1]
            if "db.adminCommand({hello:1})" in cmd:
                return 'SKLPROBE:{"ready":true}'
            if "documents:" in cmd:
                match = re.search("token:'([a-f0-9]{32})'", cmd)
                assert match
                state["token"] = match.group(1)
                return 'SKLPROBE:{"ack":true}'
            if "firstBatch" in cmd:
                match = re.search("a\\[0\\]\\.token==='([a-f0-9]{32})'", cmd)
                assert match and match.group(1) == state["token"]
                state["reads"] += 1
                if fail_second_read and state["reads"] == 2:
                    return 'SKLPROBE:{"ok":true,"count":0,"matched":false}'
                return 'SKLPROBE:{"ok":true,"count":1,"matched":true}'
            pytest.fail("unreviewed synthetic JavaScript executed")
        if op == "kill":
            state["nodes"][argv[-1]] = False
            return argv[-1]
        if op == "start":
            state["nodes"][argv[-1]] = True
            return argv[-1]
        if op == "rm":
            del state["nodes"][argv[-1]]
            return argv[-1]
        if op == "ps":
            return "\n".join(state["nodes"])
        pytest.fail("unreviewed Docker action " + op)

    monkeypatch.setattr(probe, "_call", fake_call)
    return state


def _run_with_mock():
    return probe.qualify_physical_synthetic_restart(
        "cpu", Path("/synthetic-bundle"), Path("/synthetic-overlay"),
        expected_receipt_sha256=DIGEST,
        allow_synthetic_writes=True, allow_private_bind=True,
    )


def test_exact_crash_restart_and_container_recreate_on_same_scratch(
        monkeypatch):
    state = _fake_runtime(monkeypatch)
    receipt = _run_with_mock()
    assert state["created"] == [CID1, CID2]
    assert state["reads"] == 3
    assert not state["nodes"]
    assert state["events"].count("run") == 2
    assert state["events"].count("kill") == 1
    assert state["events"].count("start") == 1
    assert state["events"].count("rm") == 2
    assert state["token"] and len(state["token"]) == 32
    assert not state["root"].exists()
    assert receipt["schema"] == probe.SCHEMA
    assert receipt["synthetic_marker_survived_sigkill_and_restart"] is True
    assert receipt["synthetic_marker_survived_new_container_same_scratch"] is True
    assert receipt["private_scratch_cleanup_completed"] is True
    for flag in (
        "production_mongo_data_read_or_written",
        "production_volumes_attached",
        "actual_replica_majority_tested",
        "independent_physical_failure_domain_proven",
        "real_app_mongo_wiredtiger_recovery_qualified",
        "cross_store_snapshot_atomic",
        "protected_jeeves_chat_qualified",
        "release_authorized",
    ):
        assert receipt[flag] is False


def test_failed_replay_never_qualifies_and_still_cleans_private_scratch(
        monkeypatch):
    state = _fake_runtime(monkeypatch, fail_second_read=True)
    with pytest.raises(probe.SyntheticRestartError, match="failed"):
        _run_with_mock()
    assert state["reads"] == 2
    assert not state["nodes"]
    assert state["root"] is not None
    assert not state["root"].exists()


@pytest.mark.parametrize("writes,binding", [(False, True), (True, False)])
def test_explicit_dual_opt_in_required_before_source_or_docker(
        monkeypatch, writes, binding):
    monkeypatch.setattr(probe.binding, "verify_binding", lambda *a, **kw:
                        pytest.fail("missing approval touched image bundle"))
    with pytest.raises(probe.SyntheticRestartError, match="both synthetic"):
        probe.qualify_physical_synthetic_restart(
            "cpu", Path("/synthetic-bundle"), Path("/synthetic-overlay"),
            expected_receipt_sha256=DIGEST,
            allow_synthetic_writes=writes,
            allow_private_bind=binding,
        )


def test_forged_pinned_image_receipt_denied_before_scratch_creation(
        monkeypatch):
    monkeypatch.setattr(probe.binding, "verify_binding",
                        lambda *a, **kw: {
                            "images": [{"service": "mongo",
                                        "image_id": "mongo:latest"}],
                            "all_four_image_ids_installed": True,
                            "actual_overlay_render_verified": True,
                        })
    monkeypatch.setattr(probe, "_scratch", lambda *a, **kw:
                        pytest.fail("invalid image created host scratch"))
    with pytest.raises(probe.SyntheticRestartError):
        _run_with_mock()


def test_mongosh_missing_or_poisoned_ack_refused(scratch, monkeypatch):
    monkeypatch.setattr(probe, "_call", lambda *a, **kw:
                        'SKLPROBE:{"ack":false}')
    with pytest.raises(probe.SyntheticRestartError, match="not acknowledged"):
        probe._write(
            CID1, "f"*32, scope=SCOPE, image=IMAGE, root=scratch,
        )
    monkeypatch.setattr(probe, "_call", lambda *a, **kw:
                        'SKLPROBE:{"ok":true,"count":2,"matched":true}')
    with pytest.raises(probe.SyntheticRestartError, match="did not survive"):
        probe._read(
            CID1, "f"*32, scope=SCOPE, image=IMAGE, root=scratch,
        )


def test_unexpected_synthetic_cleanup_container_is_never_removed(
        scratch, monkeypatch):
    foreign = "e"*64
    calls = []
    def fake(argv, *, scope, image, root, **kw):
        calls.append(argv)
        if argv[1] == "ps":
            return foreign
        if argv[1] == "inspect":
            return json.dumps(_inspect_doc(
                root, cid=foreign, image="sha256:"+"f"*64,
                scope=scope,
            ))
        pytest.fail("foreign container was removed: " + str(argv))
    monkeypatch.setattr(probe, "_call", fake)
    with pytest.raises(probe.SyntheticRestartError, match="cleanup incomplete"):
        probe._cleanup(SCOPE, IMAGE, scratch, set())
    assert scratch.exists()
    assert not any(argv[1] == "rm" for argv in calls)


def test_source_contains_no_production_volume_or_network_fallbacks():
    import inspect
    content = inspect.getsource(probe)
    assert '"--pull", "never"' in content
    assert '"--network", "none"' in content
    assert '"--read-only"' in content
    assert '"--privileged"' not in content
    assert '"--publish"' not in content
    assert '"docker", "volume", "rm"' not in content
