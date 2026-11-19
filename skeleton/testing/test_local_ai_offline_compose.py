"""Source qualification for private, exact-ID, no-pull local Jeeves Compose overlays.

Synthetic service configurations and archive receipts only; no Docker daemon,
user data, model inference or application startup is exercised in this suite.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from unittest import mock

import pytest

from scripts import local_ai_docker as host
from scripts import local_ai_image_bundle as bundle
from scripts import local_ai_image_transfer as transfer
from scripts import local_ai_offline_compose as binding
from skeleton.testing.test_docker_local_ai import _fake_config

_DIGEST = "a" * 64
_IDS = {
    role: "sha256:" + format(index + 1, "064x")
    for index, role in enumerate(bundle.ROLES)
}
_SOURCE = "file:///synthetic/offline-archive"


def _fixtures(tmp_path: Path, monkeypatch, *, altered=None,
              missing=None, require_mode=None):
    base = _fake_config(tmp_path)
    base["name"] = "skeleton-fixture"
    calls = []

    def run(args, *, root=host.ROOT, capture=False):
        argv = list(args)
        calls.append(argv)
        if argv[:3] == ["docker", "image", "inspect"]:
            key = argv[-1]
            if key == missing:
                raise host.LocalDockerError("image missing")
            return key + "\n"
        if "config" in argv:
            actual = copy.deepcopy(base)
            if argv.count("-f") >= 2:
                pos = len(argv) - 1 - list(reversed(argv)).index("-f")
                path = Path(argv[pos + 1])
                assert path.name == binding.FILE
                if not path.is_file():
                    raise AssertionError("overlay was not written")
                overlay = json.loads(path.read_text())
                for name, spec in overlay["services"].items():
                    actual["services"][name].update(spec)
                if altered:
                    altered(actual)
            return json.dumps(actual)
        raise AssertionError("unexpected Docker operation: " + repr(argv))

    def transfer_plan(archive, *, expected_receipt_sha256, mode, root):
        assert archive == Path(_SOURCE)
        assert root == tmp_path
        if expected_receipt_sha256 != _DIGEST:
            raise transfer.TransferError("trusted receipt fingerprint differs")
        if require_mode is not None and mode != require_mode:
            raise transfer.TransferError("offline transfer accelerator differs")
        return {
            "receipt_file_sha256": _DIGEST,
            "platform": "linux/amd64", "mode": mode,
        }

    rows = [{"service": role, "image_id": _IDS[role]}
            for role in bundle.ROLES]
    monkeypatch.setattr(host, "inspect_config", lambda mode, root: {
        "provider": "local", "mode": mode, "image": "skeleton-local-ai:dev",
    })
    monkeypatch.setattr(host, "_validate_config",
                        lambda mode, topology: None)
    monkeypatch.setattr(host, "compose_command",
                        lambda mode, root: ["docker", "compose", "-f", "base.yml"])
    monkeypatch.setattr(host, "_run", run)
    monkeypatch.setattr(transfer, "plan_import", transfer_plan)
    monkeypatch.setattr(bundle, "verify_image_bundle",
                        lambda archive: {"images": copy.deepcopy(rows)})
    return calls, base


def _archive() -> Path:
    return Path(_SOURCE)


def _target(tmp_path: Path) -> Path:
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    return parent / "binding-001"


def _prepare(tmp_path: Path, monkeypatch, **kwargs):
    calls, base = _fixtures(tmp_path, monkeypatch, **kwargs)
    folder = _target(tmp_path)
    response = binding.prepare_binding(
        "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
        root=tmp_path,
    )
    return folder, response, calls


def test_plan_read_only_checks_four_actual_image_ids(tmp_path, monkeypatch):
    calls, _ = _fixtures(tmp_path, monkeypatch)
    response = binding.plan_binding(
        "cpu", _archive(), expected_receipt_sha256=_DIGEST,
        root=tmp_path,
    )
    assert response["mode"] == "cpu"
    assert response["project"] == "skeleton-fixture"
    assert response["platform"] == "linux/amd64"
    assert response["source_effective_compose_admitted"] is True
    assert response["all_four_image_ids_installed"] is True
    assert response["overlay_written"] is False
    assert response["actual_overlay_render_verified"] is False
    assert response["registry_pull_required"] is False
    assert response["guarded_chat_qualified"] is False
    assert response["recovery_qualified"] is False
    assert response["writer_epoch_qualified"] is False
    assert response["containers_started"] is False
    inspect = [cmd for cmd in calls if cmd[:3] == ["docker", "image", "inspect"]]
    assert len(inspect) == 4
    assert {cmd[-1] for cmd in inspect} == set(_IDS.values())
    assert all("up" not in cmd and "pull" not in cmd and
               "load" not in cmd and "tag" not in cmd for cmd in calls)


def test_prepare_and_verify_exact_compose_deep_equality(tmp_path, monkeypatch):
    folder, response, calls = _prepare(tmp_path, monkeypatch)
    assert response["status"] == (
        "four_image_id_compose_render_qualified_not_app_started"
    )
    assert response["actual_overlay_render_verified"] is True
    assert response["offline_up_authorized"] is False
    assert response["source_receipt_file_sha256"] == _DIGEST
    assert {item.name for item in folder.iterdir()} == {
        binding.FILE, binding.RECEIPT,
    }
    assert folder.stat().st_mode & 0o777 == 0o700
    for path in folder.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
    override = json.loads((folder / binding.FILE).read_text())
    assert override == {"services": {
        role: {"image": _IDS[role]} for role in bundle.ROLES
    }}
    assert "mongodb" not in (folder / binding.FILE).read_text().lower()
    assert _DIGEST not in (folder / binding.FILE).read_text()
    sealed = json.loads((folder / binding.RECEIPT).read_text())
    assert response["receipt_sha256"] == sealed["receipt_sha256"]
    assert response["images"] == sealed["images"]
    assert len([x for x in calls if "config" in x and
                binding.FILE in " ".join(x)]) >= 2
    assert not any("up" in cmd or "run" in cmd or "load" in cmd for cmd in calls)
    assert binding.verify_binding(
        "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
        root=tmp_path,
    ) == response


def test_prepare_never_overwrites_existing_binding(tmp_path, monkeypatch):
    folder, _, _ = _prepare(tmp_path, monkeypatch)
    before = (folder / binding.FILE).read_bytes()
    with pytest.raises(binding.OfflineComposeError, match="must not exist"):
        binding.prepare_binding(
            "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
            root=tmp_path,
        )
    assert (folder / binding.FILE).read_bytes() == before


def test_modified_overlay_digest_never_qualifies(tmp_path, monkeypatch):
    folder, _, _ = _prepare(tmp_path, monkeypatch)
    override = folder / binding.FILE
    override.write_bytes(override.read_bytes() + b"\n")
    with pytest.raises(binding.OfflineComposeError, match="bytes differ"):
        binding.verify_binding(
            "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
            root=tmp_path,
        )


def test_modified_receipt_flags_never_qualify(tmp_path, monkeypatch):
    folder, _, _ = _prepare(tmp_path, monkeypatch)
    receipt = folder / binding.RECEIPT
    record = json.loads(receipt.read_text())
    record["guarded_chat_qualified"] = True
    receipt.write_text(json.dumps(record))
    with pytest.raises(binding.OfflineComposeError, match="receipt digest"):
        binding.verify_binding(
            "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
            root=tmp_path,
        )


def test_unexpected_file_or_symlink_denied(tmp_path, monkeypatch):
    folder, _, _ = _prepare(tmp_path, monkeypatch)
    (folder / "secret").write_text("unlisted")
    with pytest.raises(binding.OfflineComposeError, match="undeclared"):
        binding.verify_binding(
            "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
            root=tmp_path,
        )
    (folder / "secret").unlink()
    (folder / binding.FILE).unlink()
    (folder / binding.FILE).symlink_to(folder / binding.RECEIPT)
    with pytest.raises(binding.OfflineComposeError):
        binding.verify_binding(
            "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
            root=tmp_path,
        )


@pytest.mark.parametrize("attack", [
    lambda x: x["services"]["mongo"]["ports"][0].update(
        {"host_ip": "0.0.0.0"}
    ),
    lambda x: x["services"]["skeleton"]["environment"].update(
        {"AI_PROVIDER": "remote"}
    ),
    lambda x: x["services"]["backend"].update({"privileged": True}),
    lambda x: x["networks"].update(
        {"attacker-net": {"name": "external", "driver": "bridge"}}
    ),
    lambda x: x["services"]["skeleton"]["volumes"].append({
        "type": "bind", "source": "/secrets", "target": "/app/secrets",
    }),
    lambda x: x["services"]["frontend"]["build"].update(
        {"target": "unreviewed"}
    ),
])
def test_render_rejects_every_non_image_compose_change(
    tmp_path, monkeypatch, attack,
):
    # Real service, network, credential or mount drift is never an image-only delta.
    calls, base = _fixtures(tmp_path, monkeypatch, altered=attack)
    target = _target(tmp_path)
    with pytest.raises(binding.OfflineComposeError, match="more than four"):
        binding.prepare_binding(
            "cpu", _archive(), target, expected_receipt_sha256=_DIGEST,
            root=tmp_path,
        )
    assert target.exists()
    assert not (target / binding.RECEIPT).exists()


def test_image_missing_denies_before_artifact_created(tmp_path, monkeypatch):
    calls, _ = _fixtures(tmp_path, monkeypatch, missing=_IDS["mongo"])
    target = _target(tmp_path)
    with pytest.raises(host.LocalDockerError):
        binding.prepare_binding(
            "cpu", _archive(), target, expected_receipt_sha256=_DIGEST,
            root=tmp_path,
        )
    assert not target.exists()
    assert not any("up" in cmd or "load" in cmd for cmd in calls)


@pytest.mark.parametrize("bad", [
    "", "b" * 64, "x" * 64, "a" * 63,
    "sha256:" + "a" * 64,
])
def test_out_of_band_fingerprint_required_before_creation(
    tmp_path, monkeypatch, bad,
):
    _fixtures(tmp_path, monkeypatch)
    target = _target(tmp_path)
    with pytest.raises((binding.OfflineComposeError, transfer.TransferError)):
        binding.prepare_binding(
            "cpu", _archive(), target,
            expected_receipt_sha256=bad, root=tmp_path,
        )
    assert not target.exists()


@pytest.mark.parametrize("mode", ["cpu", "nvidia", "rocm"])
def test_source_profile_is_preserved(mode, tmp_path, monkeypatch):
    calls, _ = _fixtures(tmp_path, monkeypatch, require_mode=mode)
    target = _target(tmp_path)
    result = binding.prepare_binding(
        mode, _archive(), target, expected_receipt_sha256=_DIGEST,
        root=tmp_path,
    )
    assert result["mode"] == mode
    assert result["actual_overlay_render_verified"] is True
    assert not any("up" in cmd or "pull" in cmd for cmd in calls)


def test_refuses_insecure_parent_without_writing(tmp_path, monkeypatch):
    _fixtures(tmp_path, monkeypatch)
    parent = tmp_path / "public"
    parent.mkdir(mode=0o755)
    with pytest.raises(bundle.ImageBundleError, match="0700"):
        binding.prepare_binding(
            "cpu", _archive(), parent / "new",
            expected_receipt_sha256=_DIGEST, root=tmp_path,
        )
    assert not (parent / "new").exists()


def test_does_not_follow_symlinked_parent(tmp_path, monkeypatch):
    _fixtures(tmp_path, monkeypatch)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    target = tmp_path / "shortcut"
    target.symlink_to(private, target_is_directory=True)
    with pytest.raises(bundle.ImageBundleError):
        binding.prepare_binding(
            "cpu", _archive(), target / "new",
            expected_receipt_sha256=_DIGEST, root=tmp_path,
        )


def test_partial_artifact_preserved_without_receipt_on_docker_merge_denial(
    tmp_path, monkeypatch,
):
    _fixtures(tmp_path, monkeypatch)
    old_run = host._run
    def rejects_effective_merge(argv, *, root=host.ROOT, capture=False):
        if argv.count("-f") >= 2 and "config" in argv:
            raise host.LocalDockerError("Docker merge denied")
        return old_run(argv, root=root, capture=capture)
    monkeypatch.setattr(host, "_run", rejects_effective_merge)
    target = _target(tmp_path)
    with pytest.raises(binding.OfflineComposeError, match="incomplete"):
        binding.prepare_binding(
            "cpu", _archive(), target, expected_receipt_sha256=_DIGEST,
            root=tmp_path,
        )
    assert target.exists() and (target / binding.FILE).exists()
    assert not (target / binding.RECEIPT).exists()


def test_cli_only_contains_read_only_binding_or_create_only_operator_actions():
    import inspect
    source = inspect.getsource(host.main)
    for name in (
        "plan-offline-compose", "prepare-offline-compose",
        "verify-offline-compose", "--expected-receipt-sha256",
        "--overlay-directory",
    ):
        assert name in source
    assert "offline-up" not in source
    assert "docker compose up" not in source


def test_overlay_bytes_are_only_exact_image_ids():
    contents = binding._overlay_bytes(_IDS)
    assert json.loads(contents) == {"services": {
        role: {"image": _IDS[role]} for role in bundle.ROLES
    }}
    with pytest.raises(binding.OfflineComposeError):
        binding._overlay_bytes({**_IDS, "unexpected": "sha256:" + "0" * 64})
    with pytest.raises(binding.OfflineComposeError):
        binding._overlay_bytes({**_IDS, "mongo": "remote:latest"})


def _model_commands(monkeypatch, *, poison_qualify=None, moved=False,
                    original_image="skeleton-local-ai:dev"):
    """Use actual canonical receipt validator, but never execute real Docker."""
    from skeleton.testing.test_docker_local_ai import _model_receipt
    prior = host._run
    seen = []

    def isolated(mode, action, *, root=host.ROOT, extra=()):
        return [
            "docker", "run", "--rm", "--pull=never", "--network", "none",
            "--read-only", "--cap-drop", "ALL", "--security-opt",
            "no-new-privileges", "--memory", "512m", "--cpus", "2",
            "--pids-limit", "64", "--shm-size", "64m",
            original_image, "python", "-m", "skeleton.app.docker_local_ai",
            action, *extra,
        ]

    def run(argv, *, root=host.ROOT, capture=False):
        if argv[:2] == ["docker", "run"]:
            seen.append(tuple(argv))
            phase = "qualify" if "qualify" in argv else "preflight"
            data = _model_receipt(phase)
            if phase == "qualify" and poison_qualify:
                poison_qualify(data)
            return json.dumps(data)
        return prior(argv, root=root, capture=capture)

    monkeypatch.setattr(host, "_isolated_container", isolated)
    monkeypatch.setattr(host, "_run", run)
    return seen


def test_exact_id_native_model_receipt_is_only_one_shot_not_guarded_chat(
    tmp_path, monkeypatch,
):
    folder, _, _ = _prepare(tmp_path, monkeypatch)
    seen = _model_commands(monkeypatch)
    output = binding.qualify_offline_model(
        "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
        max_output_tokens=24, root=tmp_path,
    )
    assert output["schema"] == "skeleton.local-ai.docker.offline-gguf-one-shot.v1"
    assert output["status"] == "native_offline_model_turn_verified_not_protected_chat"
    assert output["engine_image_id"] == _IDS["skeleton"]
    assert output["model_turn_executed"] is True
    assert output["network_required"] is False
    assert output["backend_guarded_chat_qualified"] is False
    assert output["active_gguf_tokenizer_attested"] is False
    assert output["independent_reviewer_attested"] is False
    assert output["writer_epoch_qualified"] is False
    assert output["release_qualified"] is False
    assert len(seen) == 2
    assert all(_IDS["skeleton"] in command for command in seen)
    assert all("skeleton-local-ai:dev" not in command for command in seen)
    assert all(("--network", "none") == (
        command[command.index("--network")], command[command.index("--network") + 1]
    ) for command in seen)
    assert all("--read-only" in command and "--pull=never" in command
               and "--cap-drop" in command for command in seen)
    assert seen[1][-2:] == ("--max-output-tokens", "24")
    assert not any("up" in command or "pull" in command or "build" in command
                   for command in seen)


@pytest.mark.parametrize("value", [0, -1, 129, 1024, True, None, "32", 1.5])
def test_native_model_output_budget_denies_before_any_runtime_execution(
    tmp_path, monkeypatch, value,
):
    folder, _, _ = _prepare(tmp_path, monkeypatch)
    seen = _model_commands(monkeypatch)
    with pytest.raises(binding.OfflineComposeError, match="token budget"):
        binding.qualify_offline_model(
            "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
            max_output_tokens=value, root=tmp_path,
        )
    assert not seen


def test_model_receipt_mutation_fails_closed_after_real_host_validation(
    tmp_path, monkeypatch,
):
    folder, _, _ = _prepare(tmp_path, monkeypatch)
    seen = _model_commands(monkeypatch, poison_qualify=lambda row: row.update(
        {"model_sha256": "f" * 64},
    ))
    with pytest.raises(host.LocalDockerError):
        binding.qualify_offline_model(
            "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
            root=tmp_path,
        )
    assert len(seen) == 2


def test_runtime_does_not_accept_missing_canonical_isolation(
    tmp_path, monkeypatch,
):
    folder, _, _ = _prepare(tmp_path, monkeypatch)
    seen = _model_commands(monkeypatch)
    monkeypatch.setattr(host, "_isolated_container", lambda mode, action,
                        *, root, extra=(): [
                            "docker", "run", "skeleton-local-ai:dev",
                            "python", "-m", "skeleton.app.docker_local_ai",
                            action,
                        ])
    with pytest.raises(binding.OfflineComposeError, match="isolation"):
        binding.qualify_offline_model(
            "cpu", _archive(), folder, expected_receipt_sha256=_DIGEST,
            root=tmp_path,
        )
    assert seen == []


def test_missing_binding_denies_before_native_model_calls(tmp_path, monkeypatch):
    _fixtures(tmp_path, monkeypatch)
    seen = _model_commands(monkeypatch)
    with pytest.raises((binding.OfflineComposeError, bundle.ImageBundleError)):
        binding.qualify_offline_model(
            "cpu", _archive(), _target(tmp_path),
            expected_receipt_sha256=_DIGEST, root=tmp_path,
        )
    assert seen == []


def test_native_qualification_does_not_resolve_hosted_provider_or_second_runner():
    import inspect
    raw = inspect.getsource(binding.qualify_offline_model)
    assert "host._decode_receipt" in raw
    assert "host._require_same_model" in raw
    assert "verify_binding" in raw
    assert "provider" not in raw
    assert "docker compose up" not in raw


def test_cli_exposes_exact_id_model_qualification_without_unverified_up():
    import inspect
    source = inspect.getsource(host.main)
    assert "qualify-offline-model" in source
    assert "--max-output-tokens" in source
    assert "offline-up" not in source
