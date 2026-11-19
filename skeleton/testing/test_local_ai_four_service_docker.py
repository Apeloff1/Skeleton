"""Offline Docker four-service physical qualification source contracts.

These source tests never create actual Docker images or containers. Separate
isolated exact-head CI executes the real assembly/Image Import/Compose/bridge
probe only on its disposable random test resources.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts import qualify_local_ai_four_service_docker as physical


_IDS = {
    role: "sha256:" + format(i + 11, "064x")
    for i, role in enumerate(physical.ROLES)
}


def test_exact_four_role_immutable_ids_and_internal_bridge():
    spec = physical._compose_spec("synthetic-research", _IDS)
    assert set(spec["services"]) == set(physical.ROLES)
    assert set(spec["volumes"]) == {role + "_data" for role in physical.ROLES}
    assert spec["networks"]["tutolage"]["internal"] is True
    assert spec["networks"]["tutolage"]["driver"] == "bridge"
    assert all(
        spec["services"][role]["image"] == _IDS[role]
        and spec["services"][role]["read_only"] is True
        and spec["services"][role]["security_opt"] ==
            ["no-new-privileges:true"]
        and spec["services"][role]["cap_drop"] == ["ALL"]
        and spec["services"][role]["pids_limit"] == 64
        and spec["services"][role]["mem_limit"] == "128m"
        and spec["services"][role]["cpus"] == 0.5
        and spec["services"][role]["restart"] == "no"
        and spec["services"][role]["networks"] == ["tutolage"]
        and spec["services"][role]["healthcheck"]["test"] ==
            ["CMD", "/probe", "health"]
        for role in physical.ROLES
    )


@pytest.mark.parametrize("bad", [
    {"mongo": "mongo:latest", **{x: _IDS[x] for x in physical.ROLES if x != "mongo"}},
    {k: v for k, v in _IDS.items() if k != "mongo"},
    {**_IDS, "remote": "sha256:" + "0" * 64},
    {**_IDS, "mongo": "sha256:" + "G" * 64},
    {**_IDS, "mongo": "sha256:" + "1" * 63},
])
def test_refuse_mutable_wrong_or_extra_image_names(bad):
    with pytest.raises(physical.SyntheticDockerError, match="image ID"):
        physical._compose_spec("synthetic-research", bad)


def test_no_externally_resolved_image_or_external_shell_ever_admitted():
    import inspect
    src = inspect.getsource(physical.physical_synthetic_four_service)
    assert 'docker", "image", "import"' in src
    assert '"--no-build"' in src
    assert '"never"' in src
    assert "docker pull" not in src
    assert "curl " not in src
    assert "wget " not in src
    assert "subprocess.Popen" not in src
    assert "shell=True" not in src
    assert '"--remove-orphans"' not in src
    assert '"system prune"' not in src
    assert '"--volumes"' in src


def test_synthetic_elffree_run_has_no_model_or_user_state_dependencies():
    assert "libc" not in physical.ASM.lower()
    assert "execve" not in physical.ASM.lower()
    assert ".global _start" in physical.ASM
    assert "test_egress:" in physical.ASM
    assert "sendto" in physical.ASM or "mov $44, %rax" in physical.ASM
    assert "nanosleep" in physical.ASM or "mov $35, %rax" in physical.ASM
    assert "good:" in physical.ASM and "bad:" in physical.ASM


def test_synthetic_provenance_denies_production_qualification_without_run():
    # No static self-assertion of live Jeeves chat and model readiness.
    import inspect
    src = inspect.getsource(physical.physical_synthetic_four_service)
    for gate in (
        "production_app_images_executed", "licensed_gguf_executed",
        "production_data_volumes_touched", "backend_protected_chat_qualified",
        "database_recovery_qualified", "release_qualified",
    ):
        assert '"' + gate + '": False' in src
    assert physical.SCHEMA.endswith(".v1")


def test_command_admission_denies_arbitrary_shell_and_invalid_argv(tmp_path):
    with pytest.raises(physical.SyntheticDockerError):
        physical._cmd(["docker"], root=tmp_path)
    with pytest.raises(physical.SyntheticDockerError):
        physical._cmd(["docker", ""], root=tmp_path)
    with pytest.raises(physical.SyntheticDockerError):
        physical._cmd(["docker", "x" * 8192], root=tmp_path)
    with pytest.raises(physical.SyntheticDockerError):
        physical._cmd(["docker", "inspect", *["x"] * 26], root=tmp_path)


def test_physical_probe_has_no_persisted_image_tag_or_user_volume_name():
    import inspect
    src = inspect.getsource(physical.physical_synthetic_four_service)
    assert "secrets.token_hex(12)" in src
    assert "skl-physical-four-" in src
    assert "existing" in src
    assert '"docker", "ps", "-a"' in src
    assert '"docker", "image", "rm", tag' in src
    assert "external" not in physical._compose_spec("synthetic", _IDS)["networks"]


def test_concrete_network_probe_is_required_for_every_running_service():
    import inspect
    src = inspect.getsource(physical._live_four)
    assert "launch._attest_internal_bridge" in src
    assert '"docker", "exec", cid, "/probe", "egress"' in src
    assert 'set(nets) != {name}' in src
    assert '"HostConfig"' in src
    assert '"PortBindings"' in src
    assert '"Capabilities"' not in src
