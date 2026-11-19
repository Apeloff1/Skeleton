"""Host cold-copy orchestration must preserve originals and quarantine partials."""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

from scripts import local_ai_docker as host
from scripts import local_ai_cold_backup as cold
from scripts import local_ai_recovery as recovery
from scripts import local_ai_volume_copy as worker
from skeleton.testing.test_local_ai_recovery import _topology

_IMAGE_ID = "sha256:" + "b" * 64


def _destination(tmp_path: Path) -> Path:
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    return parent / "cold-001"


def _setup(tmp_path: Path, *, backend_running: bool = False):
    topology = _topology(tmp_path)
    calls = []
    receipts = {}
    def run(args, **kwargs):
        calls.append(list(args))
        if "config" in args:
            return json.dumps(topology)
        if args[:3] == ["docker", "image", "inspect"]:
            return _IMAGE_ID + "\n"
        raise AssertionError("unapproved Docker command " + str(args))
    def worker_probe(image_id, role, volume, destination, *, action, root,
                     source_mountpoint=None, run_as="0:0"):
        assert image_id == _IMAGE_ID
        assert root == tmp_path
        assert role in recovery._REQUIRED
        assert run_as == f"{__import__('os').getuid()}:{__import__('os').getgid()}"
        if action == "copy":
            assert volume == "docker_" + role
            assert source_mountpoint == (
                "/var/lib/docker/volumes/" + volume + "/_data"
            )
            (destination / role).mkdir(mode=0o700)
        else:
            assert volume is None
            assert source_mountpoint is None
        receipt = worker._receipt(role, count=2, total=100, digest="a" * 64)
        receipts[role] = receipt
        return receipt
    volume_names = lambda name, root: name.removeprefix("docker_") != "chroma_data"
    def observed(mode, root):
        return {
            "no_running_attachments_observed": not backend_running,
            "total_application_volumes_observed": 4,
        }
    ctx = (
        mock.patch.object(host, "compose_command", return_value=["docker", "compose"]),
        mock.patch.object(host, "_run", side_effect=run),
        mock.patch.object(recovery, "preflight_application_recovery", side_effect=observed),
        mock.patch.object(recovery, "_volume_exists", side_effect=volume_names),
        mock.patch.object(
            recovery, "_volume_metadata",
            side_effect=lambda name, *_: (
                "/var/lib/docker/volumes/" + name + "/_data"
            ),
        ),
        mock.patch.object(recovery, "_running_attachments", return_value=0),
        mock.patch.object(cold, "_run_worker", side_effect=worker_probe),
    )
    return ctx, calls, receipts


def test_explicit_cold_copy_seals_all_four_independently_verified_roles(tmp_path):
    target = _destination(tmp_path)
    patches, calls, receipts = _setup(tmp_path)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        result = cold.cold_backup_application(
            "cpu", target, acknowledged_non_atomic=True, root=tmp_path)
        verify = cold.verify_application_cold_backup(target, root=tmp_path)
    assert result == verify
    assert result["volumes_verified"] == 4
    assert result["files_verified"] == 8
    assert result["bytes_verified"] == 400
    assert result["application_recovery_qualified"] is False
    assert result["cross_store_snapshot_atomic"] is False
    assert target.joinpath(cold.RECEIPT).is_file()
    report = cold._read_receipt(target)
    assert report["roles"] == sorted(recovery._REQUIRED)
    assert report["volumes"] == receipts
    assert report["exclusive_writer_quiescence_verified"] is False
    assert report["protected_jeeves_qualified"] is False
    assert len([x for x in calls if x[:3] == ["docker", "image", "inspect"]]) == 1
    assert not any(any(arg in ("stop", "up", "down", "prune", "rm", "create")
                       for arg in command) for command in calls)


def test_explicit_acknowledgement_is_required_before_any_daemon_call(tmp_path):
    target = _destination(tmp_path)
    with mock.patch.object(host, "_run") as run:
        with pytest.raises(host.LocalDockerError, match="acknowledgement"):
            cold.cold_backup_application("cpu", target, root=tmp_path)
    assert not target.exists()
    run.assert_not_called()


def test_active_backend_or_mongo_prevents_copy_and_directory_creation(tmp_path):
    target = _destination(tmp_path)
    patches, _calls, _receipts = _setup(tmp_path, backend_running=True)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        with pytest.raises(host.LocalDockerError, match="running"):
            cold.cold_backup_application(
                "cpu", target, acknowledged_non_atomic=True, root=tmp_path)
    assert not target.exists()


def test_partial_copy_is_retained_but_never_receipted_or_called_recovery(tmp_path):
    target = _destination(tmp_path)
    patches, _calls, _receipts = _setup(tmp_path)
    number = 0
    def fail_on_second(image_id, role, volume, destination, *, action, root,
                       source_mountpoint=None, run_as="0:0"):
        nonlocal number
        if action == "copy":
            number += 1
            (destination / role).mkdir(mode=0o700)
            if number == 2:
                raise host.LocalDockerError("private backend source unavailable")
        return worker._receipt(role, count=0, total=0, digest="a"*64)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], (
        mock.patch.object(cold, "_run_worker", side_effect=fail_on_second)
    ):
        with pytest.raises(host.LocalDockerError, match="partial archive"):
            cold.cold_backup_application("cpu", target,
                                         acknowledged_non_atomic=True, root=tmp_path)
    assert target.is_dir()
    assert not (target / cold.RECEIPT).exists()
    assert len(list(target.iterdir())) == 2


def test_copy_is_denied_if_a_writer_appears_after_first_copy(tmp_path):
    target = _destination(tmp_path)
    patches, _calls, _receipts = _setup(tmp_path)
    counter = 0
    def attachments(name, root):
        nonlocal counter
        counter += 1
        # Four initial preflight rechecks, then the first before/after copy.
        return 1 if counter >= 6 else 0
    with patches[0], patches[1], patches[2], patches[3], patches[4], (
        mock.patch.object(recovery, "_running_attachments", side_effect=attachments)
    ), patches[6]:
        with pytest.raises(host.LocalDockerError, match="partial archive"):
            cold.cold_backup_application("cpu", target,
                                         acknowledged_non_atomic=True, root=tmp_path)
    assert target.exists()
    assert not (target / cold.RECEIPT).exists()


def test_repeated_copy_does_not_modify_a_completed_archive(tmp_path):
    target = _destination(tmp_path)
    patches, _calls, _receipts = _setup(tmp_path)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        cold.cold_backup_application("cpu", target,
                                     acknowledged_non_atomic=True, root=tmp_path)
        before = (target / cold.RECEIPT).read_bytes()
        with pytest.raises(host.LocalDockerError, match="unused"):
            cold.cold_backup_application("cpu", target,
                                         acknowledged_non_atomic=True, root=tmp_path)
        assert (target / cold.RECEIPT).read_bytes() == before


@pytest.mark.parametrize("relative", [
    Path("relative"), Path("/tmp/../world,unsafe"), Path("/tmp/unsafe=path"),
])
def test_unsafe_host_copy_destinations_refused(relative, tmp_path):
    with pytest.raises(host.LocalDockerError):
        cold._private_root(relative, must_exist=False)


def test_world_readable_archive_parent_is_refused(tmp_path):
    parent = tmp_path / "world"
    parent.mkdir(mode=0o755)
    with pytest.raises(host.LocalDockerError, match="0700"):
        cold._private_root(parent / "cold-001", must_exist=False)


def test_receipt_forgery_or_extra_metadata_cannot_pass_backup_verifier(tmp_path):
    target = _destination(tmp_path)
    patches, _calls, _receipts = _setup(tmp_path)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        cold.cold_backup_application("cpu", target,
                                     acknowledged_non_atomic=True, root=tmp_path)
        receipt = target / cold.RECEIPT
        contents = json.loads(receipt.read_text())
        contents["application_recovery_qualified"] = True
        receipt.write_text(json.dumps(contents))
        with pytest.raises(host.LocalDockerError):
            cold.verify_application_cold_backup(target, root=tmp_path)


def test_verifier_rejects_extra_archive_files_even_with_matching_receipt(tmp_path):
    target = _destination(tmp_path)
    patches, _calls, _receipts = _setup(tmp_path)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        cold.cold_backup_application("cpu", target,
                                     acknowledged_non_atomic=True, root=tmp_path)
        (target / "injected").write_text("not an admitted volume")
        with pytest.raises(host.LocalDockerError, match="undeclared"):
            cold.verify_application_cold_backup(target, root=tmp_path)


def test_worker_command_uses_network_none_readonly_source_and_digest_pinned_image(tmp_path):
    target = _destination(tmp_path)
    commands = []
    def run(args, **kwargs):
        commands.append(args)
        return json.dumps({"ok": True, **worker._receipt(
            "mongo_data", count=1, total=21, digest="a"*64,
        )})
    with mock.patch.object(host, "_run", side_effect=run):
        copied = cold._run_worker(
            _IMAGE_ID, "mongo_data", "docker_mongo_data", target,
            action="copy", root=tmp_path,
            source_mountpoint="/var/lib/docker/volumes/docker_mongo_data/_data")
        verified = cold._run_worker(
            _IMAGE_ID, "mongo_data", None, target,
            action="verify", root=tmp_path)
    assert copied == verified
    assert len(commands) == 2
    for command in commands:
        assert command[:3] == ["docker", "run", "--rm"]
        assert "--pull=never" in command and "--network=none" in command
        assert "--read-only" in command and "--cap-drop=ALL" in command
        assert "--security-opt=no-new-privileges" in command
        assert "--pids-limit=96" in command and "--user=0:0" in command
        assert _IMAGE_ID in command
    assert any(
        "type=bind" in arg and
        "source=/var/lib/docker/volumes/docker_mongo_data/_data" in arg
        and "readonly" in arg for arg in commands[0]
    )
    assert not any("type=volume" in arg for arg in commands[0])
    assert not any("docker_mongo_data" in arg for arg in commands[1])
    assert any(arg.endswith(",readonly") and "target=/archive" in arg
               for arg in commands[1])


@pytest.mark.parametrize("change", [
    {"ok": False},
    {"application_restore_qualified": True},
    {"cross_store_snapshot_atomic": True},
    {"protected_jeeves_qualified": True},
    {"private_file": "example"},
    {"manifest_sha256": "invalid"},
    {"bytes": True},
    {"files": -1},
])
def test_worker_receipt_must_not_promote_unverified_data(tmp_path, change):
    sample = {"ok": True, **worker._receipt(
        "mongo_data", count=1, total=21, digest="b"*64,
    )}
    sample.update(change)
    with mock.patch.object(host, "_run", return_value=json.dumps(sample)):
        with pytest.raises(host.LocalDockerError):
            cold._run_worker(
                _IMAGE_ID, "mongo_data", "docker_mongo_data",
                tmp_path, action="copy", root=tmp_path,
                source_mountpoint="/var/lib/docker/volumes/docker_mongo_data/_data",
            )


def test_missing_daemon_bind_source_is_denied_without_docker_launch(tmp_path):
    target = _destination(tmp_path)
    for unsafe in (
        None, "", "/etc/passwd", "/var/lib/docker/volumes/other/_data",
        "/var/lib/docker/volumes/docker_mongo_data/../_data",
        "/var/lib/docker/volumes/docker_mongo_data/_data,readonly=false",
        "/var/lib/docker/volumes/docker_mongo_data/_data\n--privileged",
    ):
        with mock.patch.object(host, "_run") as run:
            with pytest.raises(host.LocalDockerError):
                cold._run_worker(
                    _IMAGE_ID, "mongo_data", "docker_mongo_data", target,
                    action="copy", root=tmp_path, source_mountpoint=unsafe,
                )
            run.assert_not_called()


def test_verify_worker_cannot_accidentally_bind_a_live_source(tmp_path):
    target = _destination(tmp_path)
    with mock.patch.object(host, "_run") as run:
        with pytest.raises(host.LocalDockerError):
            cold._run_worker(
                _IMAGE_ID, "mongo_data", "docker_mongo_data", target,
                action="verify", root=tmp_path,
                source_mountpoint="/var/lib/docker/volumes/docker_mongo_data/_data",
            )
        run.assert_not_called()


@pytest.mark.parametrize("identity", [
    "", "root", "--privileged", "0:0:0", "0:-1", "-1:0",
    "99999999999:0", "2147483648:0", "0:2147483648",
    "1:2 --mount=type=bind", "0:0\n--network=host",
])
def test_invalid_worker_uid_denied_before_any_docker_execution(tmp_path, identity):
    with mock.patch.object(host, "_run") as run:
        with pytest.raises(host.LocalDockerError, match="user identity"):
            cold._run_worker(_IMAGE_ID, "mongo_data", None, tmp_path,
                             action="verify", root=tmp_path, run_as=identity)
        run.assert_not_called()


def test_private_archive_worker_uses_owning_numeric_user_and_no_capabilities(tmp_path):
    identity = f"{__import__('os').getuid()}:{__import__('os').getgid()}"
    commands = []
    receipt = worker._receipt("mongo_data", count=1, total=9, digest="a" * 64)
    with mock.patch.object(host, "_run", side_effect=lambda args, **kwargs: (
        commands.append(list(args)) or json.dumps({"ok": True, **receipt})
    )):
        cold._run_worker(
            _IMAGE_ID, "mongo_data", "docker_mongo_data", tmp_path,
            action="copy", root=tmp_path, run_as=identity,
            source_mountpoint="/var/lib/docker/volumes/docker_mongo_data/_data",
        )
    command = commands[0]
    assert "--user=" + identity in command
    assert "--cap-drop=ALL" in command
    assert "--security-opt=no-new-privileges" in command
    assert "--network=none" in command
    assert not any("type=volume" in arg for arg in command)
