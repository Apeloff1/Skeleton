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



def test_real_backend_loopback_binding_keeps_internal_only_network():
    spec = physical._compose_spec(
        "synthetic-research", _IDS, backend_host_port=18443,
    )
    backend = spec["services"]["backend"]
    assert backend["command"] == ["serve"]
    assert backend["ports"] == [{
        "target": 8001, "published": "18443",
        "host_ip": "127.0.0.1", "protocol": "tcp",
    }]
    assert set(spec["services"]["skeleton"]) == set(
        physical._compose_spec("synthetic-research", _IDS)["services"]["skeleton"]
    )
    assert all("ports" not in spec["services"][role]
               for role in physical.ROLES if role != "backend")
    assert spec["networks"]["tutolage"]["internal"] is True


@pytest.mark.parametrize("invalid", [
    0, 1023, 65536, True, None if False else "18883", 1.5,
])
def test_real_backend_published_port_never_accepts_invalid_host_port(invalid):
    with pytest.raises(physical.SyntheticDockerError, match="port"):
        physical._compose_spec(
            "synthetic-research", _IDS, backend_host_port=invalid,
        )


def _synthetic_live_inspection(monkeypatch, *, change=None, port=18443):
    import json

    cids = {
        role: format(index + 1, "064x")
        for index, role in enumerate(physical.ROLES)
    }
    observed = []
    project = "physical-verified"

    def run(argv, *, root, timeout=120, may_fail=False):
        observed.append(argv)
        if argv[0:2] == ["docker", "compose"] and "ps" in argv:
            return cids[argv[-1]]
        if argv[:2] == ["docker", "inspect"]:
            role = next(role for role in physical.ROLES
                        if cids[role] == argv[-1])
            ports = (
                {"8001/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(port)}]}
                if role == "backend" else {}
            )
            data = {
                "Image": _IDS[role],
                "Config": {"Labels": {
                    "com.docker.compose.project": project,
                    "com.docker.compose.service": role,
                }},
                "State": {"Running": True, "Health": {"Status": "healthy"}},
                "HostConfig": {
                    "ReadonlyRootfs": True, "Privileged": False,
                    "CapAdd": None, "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges:true"],
                    "PortBindings": ports,
                },
                "NetworkSettings": {
                    "Networks": {project + "_tutolage": {}},
                    "Ports": copy.deepcopy(ports),
                },
            }
            if change:
                change(role, data)
            return json.dumps(data)
        if argv[:2] == ["docker", "exec"]:
            return ""
        raise AssertionError("unexpected Docker operation: " + str(argv))

    monkeypatch.setattr(physical, "_cmd", run)
    monkeypatch.setattr(physical.launch, "_attest_internal_bridge",
                        lambda name, project, root: None)
    return observed, project


def test_actual_inspector_admits_exactly_one_ipv4_backend_binding(
    monkeypatch, tmp_path,
):
    commands, project = _synthetic_live_inspection(monkeypatch)
    result = physical._live_four(
        ["docker", "compose", "-f", "synthetic.json"],
        project, _IDS, tmp_path, backend_host_port=18443,
    )
    assert len(result) == 4
    assert [item["published_ports"] for item in result] == [0, 0, 1, 0]
    assert all(item["external_udp_sendto_denied"] for item in result)
    assert len([args for args in commands if args[:2] == ["docker", "exec"]]) == 4


@pytest.mark.parametrize("change", [
    lambda role, d: (
        d["HostConfig"]["PortBindings"]["8001/tcp"][0].update(
            {"HostIp": "0.0.0.0"})
        if role == "backend" else None
    ),
    lambda role, d: (
        d["HostConfig"]["PortBindings"]["8001/tcp"][0].update(
            {"HostPort": "12345"})
        if role == "backend" else None
    ),
    lambda role, d: (
        d["HostConfig"]["PortBindings"].update(
            {"3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3000"}]})
        if role == "frontend" else None
    ),
    lambda role, d: (
        d["HostConfig"].update({"PortBindings": {}})
        if role == "backend" else None
    ),
    lambda role, d: (
        d["NetworkSettings"]["Ports"]["8001/tcp"][0].update({"HostIp": "0.0.0.0"})
        if role == "backend" else None
    ),
    lambda role, d: (
        d["NetworkSettings"]["Ports"]["8001/tcp"][0].update({"HostPort": "20444"})
        if role == "backend" else None
    ),
    lambda role, d: (
        d["NetworkSettings"]["Ports"].update({
            "3000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3000"}]})
        if role == "frontend" else None
    ),
    lambda role, d: (
        d["NetworkSettings"].update({"Ports": {}})
        if role == "backend" else None
    ),
])
def test_real_container_port_drift_is_rejected(
    monkeypatch, tmp_path, change,
):
    commands, project = _synthetic_live_inspection(
        monkeypatch, change=change,
    )
    with pytest.raises(physical.SyntheticDockerError, match="port"):
        physical._live_four(
            ["docker", "compose", "-f", "synthetic.json"],
            project, _IDS, tmp_path, backend_host_port=18443,
        )


def test_host_local_http_proof_disables_proxy_and_redirects():
    import inspect
    code = inspect.getsource(physical._host_loopback_proof)
    assert 'ProxyHandler({})' in code
    assert '_RefuseHTTPRedirect()' in code
    assert 'http://127.0.0.1:' in code
    assert 'b"SKL-OK!!"' in code
    assert "backend_host_port=backend_port" in inspect.getsource(
        physical.physical_synthetic_four_service
    )
    assert "_host_loopback_proof(backend_port)" in inspect.getsource(
        physical.physical_synthetic_four_service
    )


def test_static_elf_includes_unprivileged_local_http_listener():
    assert "serve_http:" in physical.ASM
    assert "http_accept:" in physical.ASM
    assert "http_response:" in physical.ASM
    assert ".word 0x411f" in physical.ASM
    assert "Content-Length: 8" in physical.ASM
    assert "SKL-OK!!" in physical.ASM
    assert "mov $49, %rax" in physical.ASM  # bind syscall
    assert "mov $43, %rax" in physical.ASM  # accept syscall
