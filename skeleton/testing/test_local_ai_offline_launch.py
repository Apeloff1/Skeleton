"""Fail-closed first-install offline Docker startup and live container attestation.

All test probes use deterministic, synthetic Docker JSON. No real images,
Docker daemon, GGUF, containers, named volumes or model server are used.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import local_ai_docker as host
from scripts import local_ai_image_bundle as bundle
from scripts import local_ai_offline_compose as binding
from scripts import local_ai_offline_launch as launch

_IDS = {role: "sha256:" + format(i + 1, "064x")
        for i, role in enumerate(bundle.ROLES)}
_CIDS = {role: format(i + 1, "064x")
         for i, role in enumerate(bundle.ROLES)}
_SHA = "f" * 64
_PROJECT = "skeleton-fixture"
_NETWORK = "skeleton-local"
_ARCHIVE = Path("/not-a-real-model/transport")
_OVERLAY = Path("/not-a-real-model/private/offline-bind")


def _topology():
    services = {}
    for role in bundle.ROLES:
        port = {"mongo": (27017, 27017), "skeleton": (8001, 8010),
                "backend": (8001, 8001), "frontend": (3000, 3000)}[role]
        mounts = {
            "mongo": [
                {"type": "volume", "source": "skeleton_fixture_mongo_data",
                 "target": "/data/db", "read_only": False},
                {"type": "volume", "source": "skeleton_fixture_mongo_config",
                 "target": "/data/configdb", "read_only": False},
            ],
            "skeleton": [
                {"type": "bind", "source": "/not-a-real-model/gguf",
                 "target": "/app/local-ai", "read_only": True},
                {"type": "volume", "source": "skeleton_fixture_engine_data",
                 "target": "/app/data", "read_only": False},
            ],
            "backend": [
                {"type": "volume", "source": "skeleton_fixture_backend_data",
                 "target": "/app/data", "read_only": False},
            ],
            "frontend": [],
        }[role]
        services[role] = {
            "image": "locally-pinned:" + role,
            "ports": [{"target": port[0], "published": str(port[1]),
                       "host_ip": "127.0.0.1", "protocol": "tcp"}],
            "volumes": mounts,
            "read_only": role == "skeleton",
            "healthcheck": {"test": ["CMD-SHELL", "true"]},
        }
    return {
        "name": _PROJECT,
        "services": services,
        "networks": {"tutolage": {"name": _NETWORK, "driver": "bridge"}},
    }


def _fake_details(role, source):
    desired = source["services"][role]
    mounts = []
    for item in desired["volumes"]:
        record = {
            "Type": item["type"], "Destination": item["target"],
            "RW": not item["read_only"],
        }
        if item["type"] == "volume":
            record["Name"] = item["source"]
        else:
            record["Source"] = item["source"]
        mounts.append(record)
    published = {
        str(port["target"]) + "/tcp": [{
            "HostIp": "127.0.0.1", "HostPort": str(port["published"]),
        }] for port in desired["ports"]
    }
    return {
        "Image": _IDS[role],
        "Config": {
            "Labels": {"com.docker.compose.project": _PROJECT,
                       "com.docker.compose.service": role},
        },
        "State": {"Running": True, "Pid": 101,
                  "Health": {"Status": "healthy"}},
        "HostConfig": {
            "Privileged": False, "NetworkMode": _NETWORK, "PidMode": "",
            "CapAdd": None,
            "ReadonlyRootfs": role == "skeleton",
            "CapDrop": ["ALL"] if role == "skeleton" else None,
            "SecurityOpt": ["no-new-privileges:true"] if role == "skeleton" else [],
            "Memory": 536870912, "PidsLimit": 64, "PortBindings": published,
        },
        "NetworkSettings": {"Networks": {_NETWORK: {"NetworkID": "fake"}}},
        "Mounts": mounts,
    }


def _fake(tmp_path, monkeypatch, *, existing_volume=False,
          existing_container=False, mutate=None, broken_native=False,
          provider_unavailable=False, poison_after_start=None):
    source = _topology()
    observed = []
    state = {"started": False, "qualified": 0, "volume_checks": 0,
             "provider_calls": 0}
    pinned = {
        "project": _PROJECT, "mode": "cpu", "platform": "linux/amd64",
        "source_receipt_file_sha256": _SHA,
        "images": [{"service": role, "image_id": _IDS[role]}
                   for role in bundle.ROLES],
    }

    def verify(mode, archive, directory, *, expected_receipt_sha256, root):
        assert mode == "cpu" and archive == _ARCHIVE and directory == _OVERLAY
        assert expected_receipt_sha256 == _SHA and root == tmp_path
        return copy.deepcopy(pinned)

    def original(mode, root):
        assert mode == "cpu" and root == tmp_path
        return copy.deepcopy(source)

    def native(mode, archive, directory, *, expected_receipt_sha256, root):
        assert mode == "cpu" and root == tmp_path
        state["qualified"] += 1
        if broken_native:
            raise host.LocalDockerError("model not genuinely loaded")
        return {"model_turn_executed": True,
                "model_sha256": "e" * 64}

    def run(argv, *, root=host.ROOT, capture=False):
        assert root == tmp_path
        argv = list(argv)
        observed.append(argv)
        if argv[:3] == ["docker", "volume", "ls"]:
            state["volume_checks"] += 1
            if existing_volume or (poison_after_start == "volume-after-model"
                                   and state["qualified"]):
                return "skeleton_fixture_mongo_data\n"
            return "unrelated_data_volume\n"
        if "ps" in argv:
            role = argv[-1]
            return (_CIDS[role] + "\n"
                    if state["started"] or existing_container else "")
        if argv[:2] == ["docker", "inspect"]:
            role = next(k for k, v in _CIDS.items() if v == argv[-1])
            data = _fake_details(role, source)
            if mutate:
                mutate(data, role)
            return json.dumps(data)
        if "up" in argv:
            assert state["qualified"] == 1
            state["started"] = True
            return ""
        raise AssertionError("unexpected Docker operation: " + str(argv))

    def provider(mode, root):
        state["provider_calls"] += 1
        if provider_unavailable:
            raise host.LocalDockerError("backend not healthy")
        return {"observed": True, "ready": False}

    monkeypatch.setattr(binding, "verify_binding", verify)
    monkeypatch.setattr(binding, "_original", original)
    monkeypatch.setattr(binding, "qualify_offline_model", native)
    monkeypatch.setattr(host, "compose_command",
                        lambda mode, root: ["docker", "compose", "-f", "base.yml"])
    monkeypatch.setattr(host, "_run", run)
    monkeypatch.setattr(host, "live_ai_status", provider)
    return source, state, observed


def _plan(tmp_path):
    return launch.plan_fresh_offline_launch(
        "cpu", _ARCHIVE, _OVERLAY,
        expected_receipt_sha256=_SHA, root=tmp_path,
    )


def _run(tmp_path, *, permit=True):
    return launch.launch_fresh_offline(
        "cpu", _ARCHIVE, _OVERLAY,
        expected_receipt_sha256=_SHA, root=tmp_path,
        allow_new_app_volumes=permit,
    )


def _attest(tmp_path):
    return launch.attest_running_offline(
        "cpu", _ARCHIVE, _OVERLAY,
        expected_receipt_sha256=_SHA, root=tmp_path,
    )


def test_plan_is_read_only_and_requires_empty_canonical_state(tmp_path, monkeypatch):
    _, state, calls = _fake(tmp_path, monkeypatch)
    plan = _plan(tmp_path)
    assert plan["mode"] == "cpu"
    assert plan["expected_new_volume_count"] == 4
    assert plan["existing_target_containers"] == 0
    assert plan["existing_target_volumes"] == 0
    assert plan["freshness_check_atomic_with_docker"] is False
    assert plan["containers_started"] is False
    assert plan["gguf_executed"] is False
    assert plan["guarded_chat_qualified"] is False
    assert state["qualified"] == 0
    assert not any("up" in command or "load" in command or
                   "run" in command or "tag" in command for command in calls)


def test_explicit_approval_required_before_even_read_only_preflight(
    tmp_path, monkeypatch,
):
    _, state, calls = _fake(tmp_path, monkeypatch)
    with pytest.raises(launch.OfflineLaunchError, match="explicit"):
        _run(tmp_path, permit=False)
    assert not calls and state["qualified"] == 0


def test_fresh_launch_uses_real_model_qualification_before_any_up(
    tmp_path, monkeypatch,
):
    _, state, calls = _fake(tmp_path, monkeypatch)
    report = _run(tmp_path)
    assert report["status"] == "offline_containers_started_not_guarded_chat_qualified"
    assert report["containers_started"] is True
    assert report["native_gguf_one_shot_qualified"] is True
    assert report["backend_provider_status_observed"] is True
    assert report["backend_provider_available"] is False
    assert report["guarded_chat_qualified"] is False
    assert report["independent_reviewer_attested"] is False
    assert report["writer_epoch_qualified"] is False
    assert report["release_qualified"] is False
    assert len(report["containers"]) == 4
    assert state["qualified"] == 1
    assert state["volume_checks"] == 2
    commands = [cmd for cmd in calls if "up" in cmd]
    assert len(commands) == 1
    command = commands[0]
    assert command[-4:] == list(bundle.ROLES)
    assert "--no-build" in command
    assert command[command.index("--pull") + 1] == "never"
    assert "--wait" in command and "--wait-timeout" in command
    assert not any("down" in cmd or "prune" in cmd or
                   "rm" in cmd or "pull" in cmd for cmd in calls)


def test_existing_named_volumes_block_first_install_and_never_create_state(
    tmp_path, monkeypatch,
):
    _, state, calls = _fake(tmp_path, monkeypatch, existing_volume=True)
    with pytest.raises(launch.OfflineLaunchError, match="existing canonical volume"):
        _run(tmp_path)
    assert state["qualified"] == 0 and not state["started"]
    assert not any("up" in cmd for cmd in calls)


def test_existing_stopped_or_running_containers_block_first_install(
    tmp_path, monkeypatch,
):
    _, state, calls = _fake(tmp_path, monkeypatch, existing_container=True)
    with pytest.raises(launch.OfflineLaunchError, match="existing local AI container"):
        _run(tmp_path)
    assert state["qualified"] == 0 and not state["started"]


def test_missing_real_native_model_denies_before_new_volumes(
    tmp_path, monkeypatch,
):
    _, state, calls = _fake(tmp_path, monkeypatch, broken_native=True)
    with pytest.raises(host.LocalDockerError, match="model not genuinely loaded"):
        _run(tmp_path)
    assert not state["started"]
    assert not any("up" in cmd for cmd in calls)


def test_rechecked_volume_race_before_compose_up_denied(tmp_path, monkeypatch):
    _, state, calls = _fake(
        tmp_path, monkeypatch, poison_after_start="volume-after-model",
    )
    with pytest.raises(launch.OfflineLaunchError, match="existing canonical volume"):
        _run(tmp_path)
    assert not state["started"]
    assert not any("up" in cmd for cmd in calls)


def test_native_result_cannot_silently_claim_qualify(tmp_path, monkeypatch):
    _, state, calls = _fake(tmp_path, monkeypatch)
    monkeypatch.setattr(binding, "qualify_offline_model",
                        lambda *args, **kwargs: {"model_turn_executed": False})
    with pytest.raises(launch.OfflineLaunchError, match="real local GGUF"):
        _run(tmp_path)
    assert not state["started"]
    assert not any("up" in cmd for cmd in calls)


def test_offline_inspection_sees_exact_running_image_ids_and_private_mounts(
    tmp_path, monkeypatch,
):
    source, state, calls = _fake(tmp_path, monkeypatch)
    state["started"] = True
    report = _attest(tmp_path)
    assert report["containers_observed"] == 4
    assert report["immutable_image_ids_verified"] is True
    assert report["all_ingress_loopback_only"] is True
    assert report["guarded_chat_qualified"] is False
    assert {row["image_id"] for row in report["containers"]} == set(_IDS.values())
    assert all(row["canonical_mounts_only"] for row in report["containers"])
    assert not any("up" in c for c in calls)


@pytest.mark.parametrize("attack", [
    lambda x: x.update({"Image": "sha256:" + "e" * 64}),
    lambda x: x["State"].update({"Running": False}),
    lambda x: x["Config"]["Labels"].update({"com.docker.compose.project": "other"}),
    lambda x: x["HostConfig"].update({"Privileged": True}),
    lambda x: x["HostConfig"].update({"PidMode": "host"}),
    lambda x: x["HostConfig"].update({"NetworkMode": "host"}),
    lambda x: x["HostConfig"].update({"CapAdd": ["SYS_ADMIN"]}),
    lambda x: x["NetworkSettings"]["Networks"].update({"external": {}}),
    lambda x: x["HostConfig"]["PortBindings"]["8001/tcp"][0].update(
        {"HostIp": "0.0.0.0"}),
    lambda x: x["HostConfig"]["PortBindings"]["8001/tcp"][0].update(
        {"HostPort": "8899"}),
    lambda x: x["HostConfig"].update({"ReadonlyRootfs": False}),
    lambda x: x["HostConfig"].update({"CapDrop": []}),
    lambda x: x["HostConfig"].update({"SecurityOpt": []}),
    lambda x: x["HostConfig"].update({"Memory": 0}),
    lambda x: x["HostConfig"].update({"PidsLimit": 0}),
    lambda x: x["Mounts"][0].update({"RW": True}),
    lambda x: x["Mounts"].append({
        "Type": "bind", "Destination": "/var/run/docker.sock",
        "Source": "/var/run/docker.sock", "RW": True,
    }),
    lambda x: x["State"]["Health"].update({"Status": "unhealthy"}),
])
def test_runtime_rejects_privilege_image_network_port_volume_or_health_drift(
    tmp_path, monkeypatch, attack,
):
    def poison(payload, role):
        if role == "skeleton":
            attack(payload)
    _, state, _ = _fake(tmp_path, monkeypatch, mutate=poison)
    state["started"] = True
    with pytest.raises(launch.OfflineLaunchError):
        _attest(tmp_path)


def test_attestation_failure_never_auto_removes_partially_created_state(
    tmp_path, monkeypatch,
):
    def poison(data, role):
        if role == "skeleton":
            data["Image"] = "sha256:" + "a" * 64
    _, state, calls = _fake(tmp_path, monkeypatch, mutate=poison)
    with pytest.raises(launch.OfflineLaunchError):
        _run(tmp_path)
    assert state["started"] is True
    assert not any("down" in c or "rm" in c or "prune" in c for c in calls)


def test_backend_provider_unavailable_does_not_promote_chat_readiness(
    tmp_path, monkeypatch,
):
    _, state, _ = _fake(tmp_path, monkeypatch, provider_unavailable=True)
    record = _run(tmp_path)
    assert record["containers_started"] is True
    assert record["backend_provider_status_observed"] is False
    assert record["backend_provider_available"] is False
    assert record["guarded_chat_qualified"] is False
    assert state["provider_calls"] == 1


def test_volume_inventory_invalid_name_denies_canonical_state_check(
    tmp_path, monkeypatch,
):
    _, state, calls = _fake(tmp_path, monkeypatch)
    old = host._run
    def hostile(argv, *, root=host.ROOT, capture=False):
        if argv[:3] == ["docker", "volume", "ls"]:
            return "bad volume with spaces\n"
        return old(argv, root=root, capture=capture)
    monkeypatch.setattr(host, "_run", hostile)
    with pytest.raises(launch.OfflineLaunchError, match="malformed"):
        _plan(tmp_path)
    assert state["qualified"] == 0


def test_canonical_invalid_source_volume_name_denies(tmp_path, monkeypatch):
    source, state, _ = _fake(tmp_path, monkeypatch)
    source["services"]["mongo"]["volumes"][0]["source"] = "private volume path"
    with pytest.raises(launch.OfflineLaunchError, match="volume path"):
        _plan(tmp_path)
    assert state["qualified"] == 0


def test_fresh_launch_never_claims_atomicity_or_restored_database_consistency(
    tmp_path, monkeypatch,
):
    _, state, _ = _fake(tmp_path, monkeypatch)
    result = _run(tmp_path)
    assert result["new_state_recovery_rehearsed"] is False
    assert result["volumes_may_contain_application_writes"] is True
    assert result["guarded_chat_qualified"] is False
    assert result["writer_epoch_qualified"] is False


def test_cli_must_require_fresh_state_creation_acknowledgment():
    from scripts import local_ai_docker
    import inspect
    source = inspect.getsource(local_ai_docker.main)
    for token in ("plan-fresh-offline-launch", "launch-fresh-offline",
                  "attest-running-offline", "--allow-new-app-volumes"):
        assert token in source
    assert "--pull" in inspect.getsource(launch.launch_fresh_offline)
    assert '"never"' in inspect.getsource(launch.launch_fresh_offline)
