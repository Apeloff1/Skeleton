"""Adversarial source qualification for opt-in disposable Mongo failover.

No Docker daemon, application database, downloaded image or real credentials.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess

import pytest

from scripts import qualify_local_ai_mongo_quorum_docker as q

ARCHIVE = Path("/not-used/validated-archive")
OVERLAY = Path("/not-used/validated-overlay")
SHA = "a" * 64
IMAGE = "sha256:" + "b" * 64
SCOPE = "skl-mongo-q-" + "c" * 16
IDS = {i: chr(100 + i) * 64 for i in range(3)}


def _binding(monkeypatch, *, image=IMAGE, complete=True):
    calls = []
    def verify(mode, archive, overlay_directory, *,
               expected_receipt_sha256, root):
        calls.append((mode, archive, overlay_directory,
                      expected_receipt_sha256))
        return {
            "source_receipt_file_sha256": SHA,
            "images": [
                {"service": "mongo", "image_id": image},
                {"service": "skeleton", "image_id": "sha256:" + "e" * 64},
                {"service": "backend", "image_id": "sha256:" + "f" * 64},
                {"service": "frontend", "image_id": "sha256:" + "1" * 64},
            ],
            "all_four_image_ids_installed": complete,
            "actual_overlay_render_verified": complete,
        }
    monkeypatch.setattr(q.binding, "verify_binding", verify)
    return calls


def _qualify(**kwargs):
    return q.qualify_synthetic_mongo(
        "cpu", ARCHIVE, OVERLAY, expected_receipt_sha256=SHA, **kwargs)


def test_no_synthetic_write_approval_is_inert(monkeypatch):
    calls = _binding(monkeypatch)
    with pytest.raises(q.SyntheticMongoError, match="explicit"):
        _qualify()
    assert calls == []


@pytest.mark.parametrize("image,complete", [
    ("mongo:7", True),
    ("sha256:" + "g" * 64, True),
    ("sha256:" + "b" * 63, True),
    (IMAGE, False),
])
def test_unverified_image_never_invokes_docker(monkeypatch, image, complete):
    calls = _binding(monkeypatch, image=image, complete=complete)
    invoked = []
    monkeypatch.setattr(q, "_local_daemon", lambda: invoked.append("docker"))
    with pytest.raises(q.SyntheticMongoError, match="immutable"):
        _qualify(allow_synthetic_writes=True)
    assert len(calls) == 1 and invoked == []


@pytest.mark.parametrize("raw", [
    "", "[]", "null", "not json", '{"a":1,"a":2}',
    '{"ok":NaN}', "x" * (q.MAX_OUTPUT + 1),
])
def test_json_parser_denies_unbounded_duplicate_and_nonfinite(raw):
    with pytest.raises(q.SyntheticMongoError):
        q._json(raw)


def test_safe_daemon_requires_local_unix_context(monkeypatch):
    monkeypatch.setattr(q.platform, "system", lambda: "Linux")
    for key in ("DOCKER_HOST", "DOCKER_CONTEXT",
                "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
        monkeypatch.delenv(key, raising=False)
    captured = []
    def run(args, **kwargs):
        captured.append(args)
        if "context" in args:
            return json.dumps("unix:///var/run/docker.sock")
        return "linux"
    monkeypatch.setattr(q, "_run", run)
    q._local_daemon()
    assert len(captured) == 2
    monkeypatch.setenv("DOCKER_HOST", "tcp://public:2375")
    with pytest.raises(q.SyntheticMongoError, match="remote-context"):
        q._local_daemon()
    monkeypatch.delenv("DOCKER_HOST")
    monkeypatch.setattr(q, "_run", lambda a, **kw:
                        json.dumps("ssh://anotherhost") if "context" in a else "linux")
    with pytest.raises(q.SyntheticMongoError, match="local Unix"):
        q._local_daemon()


def test_mongo_create_is_pinned_rootless_and_tmpfs_only(monkeypatch):
    observed = []
    monkeypatch.setattr(q, "_run",
                        lambda argv, **kw: observed.append(argv) or IDS[0])
    cid = q._mongo(IMAGE, SCOPE, 0)
    assert cid == IDS[0]
    command = observed[0]
    assert command[:3] == ["docker", "run", "-d"]
    assert command[command.index("--pull") + 1] == "never"
    assert command[command.index("--network") + 1] == SCOPE
    assert command[command.index("--user") + 1] == "999:999"
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert command.count("--tmpfs") == 3
    assert "--read-only" in command
    assert "--privileged" not in command
    assert "--publish" not in command
    assert "-v" not in command
    assert "--volume" not in command
    assert "mongod" in command
    assert IMAGE in command
    assert SCOPE in command
    assert "registry" not in str(command).lower()


def _container_metadata(*, bad_port=False, bad_mount=False,
                        bad_image=False, running=True):
    return {
        "Id": IDS[0],
        "Name": "/" + SCOPE + "-0",
        "Image": ("sha256:" + "9" * 64) if bad_image else IMAGE,
        "Config": {
            "Image": IMAGE,
            "Labels": {"skeleton.synthetic-mongo-quorum": SCOPE},
            "ExposedPorts": {"27017/tcp": {}},
        },
        "HostConfig": {
            "ReadonlyRootfs": True, "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Privileged": False, "NetworkMode": SCOPE,
            "PortBindings": {"27017/tcp": [{"HostIp": "0.0.0.0",
                                            "HostPort": "27017"}]} if bad_port else {},
            "Tmpfs": {key: "rw" for key in
                      ("/data/db", "/data/configdb", "/tmp")},
        },
        "State": {"Running": running},
        "NetworkSettings": {"Networks": {SCOPE: {}}},
        "Mounts": [{"Type": "volume", "Destination": "/data/db"}]
                  if bad_mount else [],
    }


@pytest.mark.parametrize("mutate", [
    {}, {"bad_port": True}, {"bad_mount": True}, {"bad_image": True},
    {"running": False},
])
def test_physical_container_metadata_enforces_no_persistent_writes(
        monkeypatch, mutate):
    row = _container_metadata(**mutate)
    monkeypatch.setattr(q, "_run", lambda argv, **kw: json.dumps(row))
    if not mutate:
        q._inspect_container(IDS[0], SCOPE + "-0", IMAGE, SCOPE)
    else:
        with pytest.raises(q.SyntheticMongoError, match="isolation|mount"):
            q._inspect_container(IDS[0], SCOPE + "-0", IMAGE, SCOPE)


def test_physical_network_must_be_internal_and_labelled(monkeypatch):
    network = {
        "Name": SCOPE, "Internal": True, "Driver": "bridge",
        "Attachable": False, "EnableIPv6": False,
        "Labels": {"skeleton.synthetic-mongo-quorum": SCOPE},
    }
    monkeypatch.setattr(q, "_run",
                        lambda argv, **kw: json.dumps(network))
    q._inspect_network(SCOPE)
    for key, value in [
        ("Internal", False), ("Driver", "overlay"),
        ("Labels", {}), ("Name", "production"),
        ("Attachable", True), ("EnableIPv6", True),
    ]:
        hostile = dict(network)
        hostile[key] = value
        monkeypatch.setattr(q, "_run",
                            lambda argv, data=hostile, **kw: json.dumps(data))
        with pytest.raises(q.SyntheticMongoError):
            q._inspect_network(SCOPE)


def test_real_command_subprocess_has_no_shell_and_bounded_output(monkeypatch):
    observed = []
    def run(argv, **kwargs):
        observed.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")
    monkeypatch.setattr(q.subprocess, "run", run)
    assert q._run(["docker", "info"]) == "ok"
    args, config = observed[0]
    assert config["check"] is False
    assert config["capture_output"] is True
    assert isinstance(config["timeout"], int)
    assert config.get("shell") is None
    with pytest.raises(q.SyntheticMongoError):
        q._run(["/bin/sh", "-c", "docker rm -f $(docker ps -aq)"])


def _pipeline(monkeypatch, *, fail_at=None, cleanup_failure=False):
    calls = []
    _binding(monkeypatch)
    monkeypatch.setattr(q, "_local_daemon", lambda: calls.append("local"))
    monkeypatch.setattr(q.secrets, "token_hex",
                        lambda n: "c" * (n * 2) if n == 8 else "f" * 32)
    def run(argv, **kwargs):
        calls.append(tuple(argv))
        if argv[:3] == ["docker", "network", "create"]:
            return "9" * 64
        if argv[:3] == ["docker", "stop", "--time"]:
            return IDS[0]
        return ""
    monkeypatch.setattr(q, "_run", run)
    monkeypatch.setattr(q, "_inspect_network",
                        lambda scope: calls.append("network-attested"))
    monkeypatch.setattr(q, "_mongo", lambda image, scope, i: IDS[i])
    monkeypatch.setattr(q, "_inspect_container",
                        lambda *args, **kw: calls.append(
                            "stopped" if kw.get("stopped") else "container"))
    monkeypatch.setattr(q, "_await_mongod",
                        lambda nodes: calls.append("listeners-ready"))
    monkeypatch.setattr(q, "_initialize",
                        lambda *args: calls.append("initialized"))
    monkeypatch.setattr(q, "_set_majority_default",
                        lambda cid: calls.append("journal-default"))
    monkeypatch.setattr(q, "_verify_policy",
                        lambda cid, **kw: calls.append(
                            "policy-" + str(kw["minimum_healthy_voters"])))
    monkeypatch.setattr(q, "_primary",
                        lambda nodes, **kw: (0, IDS[0]) if 0 in nodes
                        else (1, IDS[1]))
    def write(cid, nonce, step):
        calls.append("write" + str(step))
        if fail_at == step:
            raise q.SyntheticMongoError("write failure")
    monkeypatch.setattr(q, "_majority_write", write)
    monkeypatch.setattr(q, "_wait_minority_demoted",
                        lambda cid: calls.append("minority-demoted"))
    monkeypatch.setattr(q, "_assert_minority_unacknowledged",
                        lambda cid, nonce: calls.append("minority-denied"))
    monkeypatch.setattr(q, "_restart_attested",
                        lambda *args: calls.append("restarted-original"))
    monkeypatch.setattr(q, "_await_replay",
                        lambda nodes, nonce, step:
                        calls.append("replay" + str(step) + ":" + str(len(nodes))))
    def cleanup(nodes, scope, created):
        calls.append("cleanup")
        assert created is True
        assert set(nodes) == {0, 1, 2}
        if cleanup_failure:
            raise q.SyntheticMongoError("cleanup refused")
    monkeypatch.setattr(q, "_private_cleanup", cleanup)
    return calls


def test_physical_pipeline_requires_majority_failover_and_cleanup(monkeypatch):
    calls = _pipeline(monkeypatch)
    report = _qualify(allow_synthetic_writes=True)
    assert report["schema"] == q.SCHEMA
    assert report["different_primary_elected_with_two_survivors"] is True
    assert report["second_journal_requested_majority_write_acknowledged"] is True
    assert report["second_voter_stopped_and_single_member_left"] is True
    assert report["remaining_member_demoted_without_quorum"] is True
    assert report["synthetic_minority_majority_ack_denied"] is True
    assert report["original_voter_restarted_by_exact_container_id"] is True
    assert report["majority_reestablished_after_quorum_loss"] is True
    assert report["third_majority_ack_verified_after_healing"] is True
    assert report[
        "live_config_and_majority_journal_defaults_reverified_three_times"
    ] is True
    assert report["production_database_read_or_written"] is False
    assert report["production_volumes_mounted"] is False
    assert report["physical_persistent_media_durability_proven"] is False
    assert report["shared_writer_epoch_or_migration_proven"] is False
    assert report["protected_chat_or_recovery_qualified"] is False
    assert report["merge_authorized"] is False
    assert report["release_authorized"] is False
    assert calls.index("initialized") < calls.index("write1")
    assert calls.index("write1") < calls.index("stopped") < calls.index("write2")
    assert "replay1:3" in calls and "replay1:2" in calls
    assert "replay2:2" in calls
    assert "replay3:2" in calls
    assert calls.count("policy-3") == 1
    assert calls.count("policy-2") == 2
    assert calls.index("write2") < calls.index("minority-demoted")
    assert calls.index("minority-demoted") < calls.index("minority-denied")
    assert calls.index("minority-denied") < calls.index("restarted-original")
    assert calls.index("restarted-original") < calls.index("write3")
    assert calls[-1] == "cleanup"
    assert "f" * 32 not in json.dumps(report)
    assert SCOPE not in json.dumps(report)


@pytest.mark.parametrize("failure", [1, 2, 3])
def test_failed_durable_synthetic_ack_cannot_emit_success(monkeypatch, failure):
    calls = _pipeline(monkeypatch, fail_at=failure)
    with pytest.raises(q.SyntheticMongoError, match="failed closed"):
        _qualify(allow_synthetic_writes=True)
    assert calls[-1] == "cleanup"


def test_cleanup_failure_never_claims_success(monkeypatch):
    _pipeline(monkeypatch, cleanup_failure=True)
    with pytest.raises(q.SyntheticMongoError, match="cleanup"):
        _qualify(allow_synthetic_writes=True)



@pytest.mark.parametrize("response,valid", [
    ({"server_answered": True, "ok": False,
      "write_concern_failed": False, "n": False, "code": 10107}, True),
    ({"server_answered": True, "ok": True,
      "write_concern_failed": True, "n": True, "code": 0}, True),
    ({"server_answered": True, "ok": True,
      "write_concern_failed": False, "n": True, "code": 0}, False),
    ({"server_answered": True, "ok": False,
      "write_concern_failed": False, "n": False, "code": 0}, False),
    ({"server_answered": False, "ok": False,
      "write_concern_failed": False, "n": False, "code": 10107}, False),
    ({"server_answered": True, "ok": False,
      "write_concern_failed": False, "n": False, "code": True}, False),
    ({"server_answered": True, "ok": False,
      "write_concern_failed": False, "n": False, "code": 10107,
      "host": "not-admitted"}, False),
])
def test_minority_write_denial_requires_real_structured_server_proof(
        monkeypatch, response, valid):
    calls = []
    monkeypatch.setattr(q, "_shell",
                        lambda cid, expr, **kw: calls.append((cid, expr)) or response)
    if valid:
        q._assert_minority_unacknowledged(IDS[0], "a" * 32)
    else:
        with pytest.raises(q.SyntheticMongoError, match="minority"):
            q._assert_minority_unacknowledged(IDS[0], "a" * 32)
    assert len(calls) == 1
    assert "wtimeout:3000" in calls[0][1]
    assert 'w:"majority"' in calls[0][1]
    assert 'j:true' in calls[0][1]



@pytest.mark.parametrize("fields,passes", [
    ({}, True),
    ({"primary": False}, False),
    ({"set_match": False}, False),
    ({"healthy": 1}, False),
    ({"healthy": 4}, False),
    ({"voters": 2}, False),
    ({"members": 2}, False),
    ({"majority_default": False}, False),
    ({"journal_default": False}, False),
    ({"healthy": True}, False),
    ({"unexpected_field": True}, False),
])
def test_three_phase_policy_requires_real_current_quorum_and_defaults(
        monkeypatch, fields, passes):
    receipt = {
        "all_ok": True, "set_match": True, "primary": True,
        "voters": 3, "healthy": 3, "members": 3,
        "majority_default": True, "journal_default": True,
    }
    receipt.update(fields)
    calls = []
    def shell(cid, expr, **kwargs):
        calls.append(expr)
        return receipt
    monkeypatch.setattr(q, "_shell", shell)
    monkeypatch.setattr(q.time, "sleep", lambda seconds: None)
    if passes:
        q._verify_policy(IDS[0], minimum_healthy_voters=3)
        assert len(calls) == 1
    else:
        with pytest.raises(q.SyntheticMongoError, match="policy"):
            q._verify_policy(IDS[0], minimum_healthy_voters=3)
        assert len(calls) == 20
    assert "getDefaultRWConcern" in calls[0]
    assert "replSetGetConfig" in calls[0]
    assert "replSetGetStatus" in calls[0]
    assert "hello" in calls[0]


def test_policy_two_healthy_voters_admitted_only_when_current_status_proves(
        monkeypatch):
    good = {
        "all_ok": True, "set_match": True, "primary": True,
        "voters": 3, "healthy": 2, "members": 3,
        "majority_default": True, "journal_default": True,
    }
    monkeypatch.setattr(q, "_shell", lambda *a, **kw: good)
    q._verify_policy(IDS[1], minimum_healthy_voters=2)
    monkeypatch.setattr(q.time, "sleep", lambda seconds: None)
    with pytest.raises(q.SyntheticMongoError):
        q._verify_policy(IDS[1], minimum_healthy_voters=3)


def test_minority_demote_refuses_stale_primary_and_accepts_real_loss(
        monkeypatch):
    samples = [
        {"ok": True, "primary": True, "set": True},
        {"ok": True, "primary": True, "set": True},
        {"ok": True, "primary": False, "set": True},
    ]
    monkeypatch.setattr(q, "_hello", lambda cid: samples.pop(0))
    monkeypatch.setattr(q.time, "sleep", lambda seconds: None)
    q._wait_minority_demoted(IDS[2])
    assert samples == []


def test_minority_demote_never_claims_safe_loss_without_confirmation(
        monkeypatch):
    monkeypatch.setattr(q, "_hello", lambda cid: {
        "ok": True, "primary": True, "set": True
    })
    monkeypatch.setattr(q.time, "sleep", lambda seconds: None)
    with pytest.raises(q.SyntheticMongoError, match="demote"):
        q._wait_minority_demoted(IDS[2])


def test_exact_container_restart_is_preceded_and_followed_by_attestation(
        monkeypatch):
    calls = []
    monkeypatch.setattr(q, "_inspect_container",
                        lambda *a, **kw: calls.append(
                            ("inspect", kw.get("stopped", False))))
    monkeypatch.setattr(q, "_run",
                        lambda argv, **kw: calls.append(tuple(argv)) or IDS[0])
    q._restart_attested(IDS[0], SCOPE + "-0", IMAGE, SCOPE)
    assert calls == [
        ("inspect", True),
        ("docker", "start", IDS[0]),
        ("inspect", False),
    ]


def test_unverified_minority_ack_fails_even_with_canonical_cleanup(
        monkeypatch):
    calls = _pipeline(monkeypatch)
    def deny(cid, nonce):
        raise q.SyntheticMongoError("unexpected majority ack")
    monkeypatch.setattr(q, "_assert_minority_unacknowledged", deny)
    with pytest.raises(q.SyntheticMongoError, match="failed closed"):
        _qualify(allow_synthetic_writes=True)
    assert calls[-1] == "cleanup"


@pytest.mark.parametrize("poison", [False, True])
def test_orphaned_partial_mongo_is_cleaned_only_if_exact_label_and_id(
        monkeypatch, poison):
    calls = []
    node = {
        "Id": IDS[0], "Name": "/" + SCOPE + "-0",
        "Config": {"Labels": {
            "skeleton.synthetic-mongo-quorum":
                "an-unrelated-project" if poison else SCOPE,
        }},
    }
    network = {
        "Name": SCOPE, "Internal": True,
        "Labels": {"skeleton.synthetic-mongo-quorum": SCOPE},
    }
    def run(argv, **kwargs):
        calls.append(argv)
        if argv[1:3] == ["ps", "--all"]:
            return IDS[0]
        if argv[1] == "inspect":
            return json.dumps(node)
        if argv[1:3] == ["network", "inspect"]:
            return json.dumps(network)
        return ""
    monkeypatch.setattr(q, "_run", run)
    if poison:
        with pytest.raises(q.SyntheticMongoError, match="cleanup"):
            q._private_cleanup({}, SCOPE, True)
        assert ["docker", "rm", "--force", IDS[0]] not in calls
    else:
        q._private_cleanup({}, SCOPE, True)
        assert ["docker", "rm", "--force", IDS[0]] in calls
        assert ["docker", "network", "rm", SCOPE] in calls
    assert all("prune" not in str(arg) for arg in calls)


def test_cleanup_never_accepts_non_base_or_nonrandom_scope():
    for name in ("mongo", "skl-mongo-q-" + "c" * 16 + "-0",
                 "skl-mongo-q-" + "z" * 16):
        with pytest.raises(q.SyntheticMongoError, match="scope"):
            q._private_cleanup({}, name, True)


def test_synthetic_mongo_scripts_do_not_claim_production_writer_authority():
    import inspect
    source = inspect.getsource(q)
    for banned in ("docker volume prune", "docker system prune",
                   "replSetInitiate", "dropDatabase", "docker pull",
                   "docker exec -u root", "host.docker.internal"):
        assert banned not in source
    assert "--internal" in source
    assert '"--pull", "never"' in source
    assert "--read-only" in source
    assert "majority" in source
