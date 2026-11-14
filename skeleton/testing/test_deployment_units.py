"""systemd / compose renderers for self-host profiles."""

from __future__ import annotations

import pytest

from skeleton.deployment.profile import get_profile
from skeleton.deployment.units import (
    CONTAINER_DATA_DIR,
    CONTAINER_PORT,
    render_compose_service,
    render_systemd_unit,
    server_argv,
    shell_command,
)

TOKEN = "Zq8vT2mX9rL4wB7nK1pD6sF3hJ0cY5gA"


def unit_lines(text: str) -> list[str]:
    return text.splitlines()


def test_server_argv_matches_container_cmd() -> None:
    argv = server_argv(get_profile("selfhost"), python="py")
    assert argv[:5] == ["py", "-m", "uvicorn", "skeleton.api.server:create_app", "--factory"]
    assert argv[argv.index("--host") + 1] == "0.0.0.0"
    assert argv[argv.index("--port") + 1] == "8001"
    assert argv[argv.index("--log-level") + 1] == "info"
    assert "--workers" not in argv


def test_server_argv_workers_and_reload_are_exclusive() -> None:
    profile = get_profile("local").with_overrides(workers=3)
    assert server_argv(profile)[-2:] == ["--workers", "3"]
    reloaded = server_argv(profile, reload=True)
    assert reloaded[-1] == "--reload" and "--workers" not in reloaded


def test_server_argv_overrides() -> None:
    argv = server_argv(get_profile("local"), host="::1", port=1)
    assert argv[argv.index("--host") + 1] == "::1"
    assert argv[argv.index("--port") + 1] == "1"


def test_systemd_unit_is_hardened_and_keeps_token_out() -> None:
    profile = get_profile("selfhost").with_overrides(service_token=TOKEN)
    text = render_systemd_unit(profile)
    lines = unit_lines(text)
    assert lines[0] == "[Unit]"
    assert "[Service]" in lines and "[Install]" in lines
    for directive in ("NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes",
                      "Restart=on-failure", "EnvironmentFile=/etc/skeleton/skeleton.env", "UMask=0027"):
        assert directive in lines
    assert "StateDirectory=skeleton" in lines
    assert "ReadWritePaths=/var/lib/skeleton" in lines
    assert TOKEN not in text
    assert "SKL_ENGINE_SERVICE_TOKEN" not in text
    exec_line = next(line for line in lines if line.startswith("ExecStart="))
    assert "skeleton.api.server:create_app" in exec_line
    assert "Environment=SKL_ENVIRONMENT=production" in lines


def test_systemd_unit_quotes_special_values() -> None:
    text = render_systemd_unit(get_profile("selfhost"))
    assert 'Environment="SKL_ENGINE_ALLOWED_TENANTS_CSV=*"' in text


def test_systemd_unit_home_data_dir_uses_read_only_home() -> None:
    profile = get_profile("local").with_overrides(data_dir="/home/op/skeleton")
    lines = unit_lines(render_systemd_unit(profile))
    assert "ProtectHome=read-only" in lines
    assert "ReadWritePaths=/home/op/skeleton" in lines
    assert not any(line.startswith("StateDirectory=") for line in lines)


def test_systemd_unit_offline_restricts_network_and_privileged_port_grants_cap() -> None:
    offline = render_systemd_unit(get_profile("offline").with_overrides(data_dir="/var/lib/sk"))
    assert "IPAddressDeny=any" in offline and "IPAddressAllow=localhost" in offline
    low = unit_lines(render_systemd_unit(get_profile("selfhost").with_overrides(port=443)))
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in low
    assert "CapabilityBoundingSet=CAP_NET_BIND_SERVICE" in low
    high = unit_lines(render_systemd_unit(get_profile("selfhost")))
    assert "CapabilityBoundingSet=" in high
    assert not any(line.startswith("AmbientCapabilities") for line in high)


def test_systemd_unit_options() -> None:
    text = render_systemd_unit(get_profile("test"), env_file=None, user="svc", group="grp",
                               description="Custom", working_directory="/srv/sk", python="/venv/bin/python")
    lines = unit_lines(text)
    assert "Description=Custom" in lines
    assert "User=svc" in lines and "Group=grp" in lines
    assert "WorkingDirectory=/srv/sk" in lines
    assert not any(line.startswith("EnvironmentFile") for line in lines)
    assert not any(line.startswith("ReadWritePaths") for line in lines)
    assert "ExecStart=/venv/bin/python -m uvicorn" in text


def test_compose_service_parses_as_yaml_and_maps_container_layout() -> None:
    yaml = pytest.importorskip("yaml")
    profile = get_profile("local").with_overrides(port=9001, service_token=TOKEN)
    document = yaml.safe_load(render_compose_service(profile))
    service = document["services"]["skeleton"]
    assert service["ports"] == [f"127.0.0.1:9001:{CONTAINER_PORT}"]
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    env = service["environment"]
    assert env["SKL_SERVER_HOST"] == "0.0.0.0"
    assert env["SKL_SERVER_PORT"] == str(CONTAINER_PORT)
    assert env["SKL_OPERATION_STATE_PATH"] == f"{CONTAINER_DATA_DIR}/operation_state.sqlite"
    assert "SKL_ENGINE_SERVICE_TOKEN" not in env
    assert service["volumes"] == [f"skeleton_data:{CONTAINER_DATA_DIR}"]
    assert "skeleton_data" in document["volumes"]
    assert service["healthcheck"]["test"][0] == "CMD"
    assert "/api/v1/health/live" in service["healthcheck"]["test"][-1]
    assert service["env_file"] == [".env"]
    assert TOKEN not in render_compose_service(profile)


def test_compose_service_public_bind_image_and_memory_profile() -> None:
    yaml = pytest.importorskip("yaml")
    document = yaml.safe_load(render_compose_service(get_profile("test").with_overrides(host="0.0.0.0"),
                                                     image="ghcr.io/x/skeleton:16", env_file=None,
                                                     published_port=80))
    service = document["services"]["skeleton"]
    assert service["image"] == "ghcr.io/x/skeleton:16"
    assert "build" not in service
    assert service["ports"] == [f"80:{CONTAINER_PORT}"]
    assert "volumes" not in service and "volumes" not in document
    assert "env_file" not in service
    assert service["environment"]["SKL_OPERATION_STATE_PATH"] == ":memory:"


def test_compose_output_is_deterministic() -> None:
    profile = get_profile("selfhost")
    assert render_compose_service(profile) == render_compose_service(profile)
    assert f"# profile fingerprint: {profile.fingerprint()}" in render_compose_service(profile)


def test_shell_command_quotes_arguments() -> None:
    assert shell_command(["a", "b c", "d'e"]) == "a 'b c' 'd'\"'\"'e'"
