"""Non-destructive Docker recovery inventory and physical volume custody tests."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from unittest import mock

import pytest

from scripts import local_ai_docker as host
from scripts import local_ai_recovery as recovery
from skeleton.testing.test_docker_local_ai import _fake_config


def _topology(root: Path) -> dict:
    config = _fake_config(root)
    config["name"] = "docker"
    config["volumes"] = {
        name: {"name": "docker_" + name}
        for name in (
            "skeleton_data", "backend_data", "mongo_data",
            "mongo_config", "chroma_data",
        )
    }
    return config


def _probe(
    root: Path, *, config: dict | None = None,
    missing: tuple[str, ...] = ("chroma_data",),
    live: tuple[str, ...] = (),
    corrupt: str = "",
    affected: str = "mongo_data",
    vanished: str = "",
):
    topology = _topology(root) if config is None else config
    calls = []
    counters = {}
    def run(args, **kwargs):
        assert kwargs.get("root") == root
        assert kwargs.get("capture") is True
        calls.append(list(args))
        if "config" in args:
            return json.dumps(topology)
        if args[:3] == ["docker", "volume", "ls"]:
            name = args[args.index("--filter") + 1].removeprefix("name=")
            logical = name.removeprefix("docker_")
            counters[name] = counters.get(name, 0) + 1
            if logical in missing or logical == vanished and counters[name] > 1:
                return ""
            if logical == affected and corrupt == "list_bogus":
                return "INVALID VOLUME\n"
            if logical == affected and corrupt == "list_duplicate":
                return name + "\n" + name + "\n"
            return name + "\n"
        if args[:3] == ["docker", "volume", "inspect"]:
            name = args[3]
            logical = name.removeprefix("docker_")
            item = {
                "Name": name, "Driver": "local", "Scope": "local",
                "Mountpoint": "/var/lib/docker/volumes/" + name + "/_data",
                "Options": None,
                "Labels": {
                    "com.docker.compose.project": "docker",
                    "com.docker.compose.volume": logical,
                },
            }
            if logical == affected and corrupt:
                if corrupt == "wrong_name":
                    item["Name"] = "other_vol"
                elif corrupt == "wrong_project":
                    item["Labels"]["com.docker.compose.project"] = "other"
                elif corrupt == "wrong_volume":
                    item["Labels"]["com.docker.compose.volume"] = "other"
                elif corrupt == "remote_driver":
                    item["Driver"] = "nfs"
                elif corrupt == "driver_option":
                    item["Options"] = {"type": "nfs", "device": "server:/data"}
                elif corrupt == "wrong_scope":
                    item["Scope"] = "global"
                elif corrupt == "invalid_mountpoint":
                    item["Mountpoint"] = "relative/path"
                elif corrupt == "multiple":
                    return json.dumps([item, item])
            return json.dumps([item])
        if args[:2] == ["docker", "ps"]:
            volume = args[args.index("--filter") + 1].removeprefix("volume=")
            if volume == "docker_" + affected and corrupt == "malformed_container":
                return "nope\n"
            if volume == "docker_" + affected and corrupt == "duplicate_container":
                return "a" * 64 + "\n" + "a" * 64 + "\n"
            return ("a" * 64 + "\n") if volume in live else ""
        raise AssertionError("unsupported or mutating Docker command: " + str(args))

    with (
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", side_effect=run),
    ):
        yield lambda: recovery.preflight_application_recovery("cpu", root), calls


def test_cold_mandatory_state_is_only_a_read_only_recovery_candidate(tmp_path):
    start = _topology(tmp_path)
    original = deepcopy(start)
    gen = _probe(tmp_path, config=start)
    callable_probe, calls = next(gen)
    receipt = callable_probe()
    assert start == original
    assert receipt == {
        "schema": recovery._SCHEMA,
        "status": "volumes_observed_not_application_recovery_qualified",
        "mode": "cpu",
        "required_volumes_observed": 4,
        "total_application_volumes_observed": 4,
        "optional_chroma_volume_present": False,
        "running_volume_attachments_observed": 0,
        "no_running_attachments_observed": True,
        "exclusive_writer_quiescence_verified": False,
        "database_consistency_verified": False,
        "cross_store_snapshot_atomic": False,
        "credentials_exported": False,
        "content_copied": False,
        "restore_executed": False,
        "recovery_qualified": False,
        "protected_jeeves_qualified": False,
    }
    assert all(args[:2] in (["docker", "compose"], ["docker", "volume"], ["docker", "ps"]) for args in calls)
    assert not any(any(token in args for token in (
        "up", "stop", "down", "cp", "rm", "create", "prune", "tar"
    )) for args in calls)
    assert len([x for x in calls if x[:2] == ["docker", "ps"]]) == 8
    try:
        next(gen)
    except StopIteration:
        pass


def test_optional_chroma_already_present_is_reported_without_activation(tmp_path):
    gen = _probe(tmp_path, missing=())
    fn, _calls = next(gen)
    evidence = fn()
    assert evidence["total_application_volumes_observed"] == 5
    assert evidence["optional_chroma_volume_present"] is True
    assert evidence["recovery_qualified"] is False
    gen.close()


def test_active_mongo_or_engine_volume_attachment_not_equated_with_snapshot_quiescence(tmp_path):
    for running in (("docker_mongo_data",), ("docker_backend_data", "docker_skeleton_data")):
        gen = _probe(tmp_path, live=running)
        fn, _calls = next(gen)
        receipt = fn()
        assert receipt["no_running_attachments_observed"] is False
        assert receipt["running_volume_attachments_observed"] == len(running) * 2
        assert receipt["exclusive_writer_quiescence_verified"] is False
        assert receipt["content_copied"] is False
        gen.close()


@pytest.mark.parametrize("corrupt", [
    "wrong_name", "wrong_project", "wrong_volume", "remote_driver",
    "driver_option", "wrong_scope", "invalid_mountpoint", "multiple",
    "list_bogus", "list_duplicate", "malformed_container", "duplicate_container",
])
def test_docker_volume_ownership_and_attachment_spoofs_are_denied(tmp_path, corrupt):
    gen = _probe(tmp_path, corrupt=corrupt)
    fn, _ = next(gen)
    with pytest.raises(host.LocalDockerError):
        fn()
    gen.close()


def test_volume_disappearing_during_double_inventory_denies_receipt(tmp_path):
    gen = _probe(tmp_path, vanished="mongo_data")
    fn, _ = next(gen)
    with pytest.raises(host.LocalDockerError, match="disappeared"):
        fn()
    gen.close()


@pytest.mark.parametrize("mutate", [
    lambda c: c["volumes"].pop("mongo_data"),
    lambda c: c["volumes"]["backend_data"].update(external=True),
    lambda c: c["volumes"]["backend_data"].update(driver="nfs"),
    lambda c: c["volumes"]["mongo_data"].update(name="docker_backend_data"),
    lambda c: c.update(name="INAPPROPRIATE!"),
    lambda c: c["volumes"].update(extra={"name": "unexpected"}),
    lambda c: c["services"]["mongo"]["volumes"][0].update(target="/etc/passwd"),
    lambda c: c["services"].pop("backend"),
])
def test_unsafe_or_missing_compose_volume_binding_is_denied(tmp_path, mutate):
    config = _topology(tmp_path)
    mutate(config)
    gen = _probe(tmp_path, config=config)
    fn, _ = next(gen)
    with pytest.raises(host.LocalDockerError):
        fn()
    gen.close()


def test_missing_mandatory_docker_volume_not_synthesised_or_created(tmp_path):
    gen = _probe(tmp_path, missing=("mongo_data", "chroma_data"))
    fn, calls = next(gen)
    with pytest.raises(host.LocalDockerError, match="missing"):
        fn()
    assert all("create" not in args and "up" not in args for args in calls)
    gen.close()


def test_invalid_accelerator_mode_rejected_before_docker_access(tmp_path):
    with mock.patch.object(host, "_run") as run:
        with pytest.raises(host.LocalDockerError):
            recovery.preflight_application_recovery("remote-api", tmp_path)
        run.assert_not_called()


def test_recovery_receipt_excludes_sensitive_volume_identifiers_and_mountpoint(tmp_path):
    gen = _probe(tmp_path, missing=())
    fn, _ = next(gen)
    output = json.dumps(fn())
    for sensitive in ("/var/lib/docker", "docker_mongo_data", "docker_backend_data",
                      "fixture_reader", "synthetic_custody_value", "mongodb"):
        assert sensitive not in output
    gen.close()
