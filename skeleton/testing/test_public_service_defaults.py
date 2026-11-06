"""Public service endpoints must remain available with default host ports.

These are source-level contract tests; they do not certify a live installation.
"""
from dataclasses import replace
from pathlib import Path

import pytest

from skeleton.app.assembly import load_manifest, public_service_urls, runtime_manifest


def test_default_public_endpoints_are_returned_without_port_overrides(tmp_path: Path):
    manifest = load_manifest()
    urls = public_service_urls(tmp_path, manifest=manifest, environ={})
    for name in ("frontend", "backend", "skeleton"):
        assert urls[name] == manifest.service(name).public_url
        assert urls[name]


def test_single_override_does_not_hide_other_services(tmp_path: Path):
    manifest = load_manifest()
    urls = public_service_urls(tmp_path, manifest=manifest, environ={"FRONTEND_PORT": "31999"})
    assert urls["frontend"].endswith(":31999")
    for name in ("backend", "skeleton"):
        assert urls[name] == manifest.service(name).public_url


def test_port_collision_remains_fail_closed(tmp_path: Path):
    with pytest.raises(ValueError, match="must differ"):
        public_service_urls(
            tmp_path, manifest=load_manifest(),
            environ={"FRONTEND_PORT": "8001", "BACKEND_PORT": "8001"},
        )


def test_missing_public_url_is_not_exposed(tmp_path: Path):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url="") if service.name == "frontend" else service
        for service in manifest.services
    )
    urls = public_service_urls(tmp_path, manifest=replace(manifest, services=services), environ={})
    assert "frontend" not in urls
    assert urls["backend"] == manifest.service("backend").public_url


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("CHROMA_PORT", "3000"),
        ("CHROMA_PORT", "8001"),
        ("CHROMA_PORT", "8010"),
        ("CHROMA_PORT", "27017"),
        ("FRONTEND_PORT", "8000"),
        ("BACKEND_PORT", "8000"),
        ("SKELETON_PORT", "8000"),
        ("MONGO_PORT", "8000"),
    ],
)
def test_chroma_host_port_collisions_fail_closed(tmp_path: Path, key: str, value: str):
    with pytest.raises(ValueError, match="must differ"):
        public_service_urls(tmp_path, manifest=load_manifest(), environ={key: value})


def test_independent_chroma_port_override_is_visible(tmp_path: Path):
    manifest = load_manifest()
    urls = public_service_urls(tmp_path, manifest=manifest, environ={"CHROMA_PORT": "31998"})
    assert urls["chroma"].endswith(":31998")
    for name in ("frontend", "backend", "skeleton"):
        assert urls[name] == manifest.service(name).public_url


@pytest.mark.parametrize(
    "public_url",
    [
        "http://operator@localhost:3000",
        "http://localhost:3000/?token=secret",
        "http://localhost:3000/#private",
        "https://user:pass@127.0.0.1:3000",
        "http://localhost:3000/redirect",
        "http://localhost:3000/%2e%2e/",
    ],
)
def test_port_override_rejects_credential_or_fragment_url(tmp_path: Path, public_url: str):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=public_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    with pytest.raises(ValueError, match="non-local public URL"):
        public_service_urls(
            tmp_path,
            manifest=replace(manifest, services=services),
            environ={"FRONTEND_PORT": "31999"},
        )


@pytest.mark.parametrize(
    "public_url",
    [
        "http://localhost:invalid/",
        "http://localhost:99999/",
        "http://localhost/",
        "http://[::1]:invalid/",
        "http://127.0.0.1:0/",
    ],
)
def test_port_override_rejects_invalid_manifest_authority(
    tmp_path: Path, public_url: str
):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=public_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    with pytest.raises(ValueError, match="public URL port"):
        public_service_urls(
            tmp_path,
            manifest=replace(manifest, services=services),
            environ={"FRONTEND_PORT": "31999"},
        )


@pytest.mark.parametrize(
    "public_url",
    [
        "http://operator@localhost:3000",
        "http://localhost:3000/?token=secret",
        "http://localhost:3000/#private",
        "http://remote.example:3000/",
        "http://localhost:invalid/",
        "http://localhost:99999/",
        "http://localhost/",
        "http://127.0.0.1:0/",
        "http://localhost:3000/redirect",
        "file:///tmp/unsafe",
    ],
)
def test_default_public_endpoint_rejects_unsafe_manifest_url(
    tmp_path: Path, public_url: str
):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=public_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    with pytest.raises(ValueError, match="invalid local public URL"):
        public_service_urls(
            tmp_path, manifest=replace(manifest, services=services), environ={}
        )


def test_safe_ipv6_loopback_default_is_retained(tmp_path: Path):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url="http://[::1]:3000/")
        if service.name == "frontend" else service
        for service in manifest.services
    )
    urls = public_service_urls(
        tmp_path, manifest=replace(manifest, services=services), environ={}
    )
    assert urls["frontend"] == "http://[::1]:3000/"


@pytest.mark.parametrize("public_url", [
    " http://localhost:3000/",
    "\thttp://localhost:3000/",
    "http://localhost:3000/\n",
    "http://localhost:3000/\r",
    "http://localhost:3000/\x7f",
])
def test_default_public_endpoint_rejects_url_controls(tmp_path: Path, public_url: str):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=public_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    with pytest.raises(ValueError, match="invalid local public URL"):
        public_service_urls(tmp_path, manifest=replace(manifest, services=services), environ={})


@pytest.mark.parametrize("public_url", [
    " http://localhost:3000/",
    "\thttp://localhost:3000/",
    "http://localhost:3000/\n",
    "http://localhost:3000/\x7f",
])
def test_override_rejects_url_controls_before_rewriting(tmp_path: Path, public_url: str):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=public_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    with pytest.raises(ValueError, match="non-local public URL"):
        public_service_urls(
            tmp_path, manifest=replace(manifest, services=services),
            environ={"FRONTEND_PORT": "31999"},
        )


@pytest.mark.parametrize("public_url", [
    "http://remote.example:3000/",
    "http://operator@localhost:3000/",
    "http://localhost:3000/?token=secret",
    "http://localhost:3000/redirect",
    "http://localhost:99999/",
    "http://localhost:3000/\\n",
])
def test_direct_runtime_manifest_rejects_untrusted_public_urls(
    tmp_path: Path, public_url: str
):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=public_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    with pytest.raises(ValueError, match="invalid local public URL"):
        runtime_manifest(
            replace(manifest, services=services), root=tmp_path, environ={}
        )


def test_direct_runtime_manifest_preserves_valid_loopback_url(tmp_path: Path):
    manifest = load_manifest()
    resolved = runtime_manifest(manifest, root=tmp_path, environ={})
    assert resolved.service("frontend").public_url == manifest.service("frontend").public_url


@pytest.mark.parametrize("public_url", [
    "http://localhost:3000/\u200b",
    "http://localhost:3000/\u202e",
    "http://localhost:3000/\u00a0",
    "http://localhost:3000/\u0085",
    "http://localhost:3000/\u2060",
])
def test_invisible_unicode_url_characters_fail_closed_in_all_consumers(
    tmp_path: Path, public_url: str
):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=public_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    poisoned = replace(manifest, services=services)
    with pytest.raises(ValueError, match="invalid local public URL"):
        runtime_manifest(poisoned, root=tmp_path, environ={})
    with pytest.raises(ValueError, match="invalid local public URL"):
        public_service_urls(tmp_path, manifest=poisoned, environ={})


@pytest.mark.parametrize("public_url", [
    "http://localhost:3000/\u200b",
    "http://localhost:3000/\u202e",
    "http://localhost:3000/\u00a0",
])
def test_invisible_unicode_url_characters_rejected_before_port_override(
    tmp_path: Path, public_url: str
):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=public_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    with pytest.raises(ValueError, match="non-local public URL"):
        runtime_manifest(
            replace(manifest, services=services),
            root=tmp_path,
            environ={"FRONTEND_PORT": "31999"},
        )


@pytest.mark.parametrize("public_url", [
    "http://localhost:3000/?",
    "http://localhost:3000/#",
    "http://localhost:3000/?#",
    "http://localhost:3000/#?",
])
def test_empty_query_and_fragment_delimiters_are_not_silently_normalized(
    tmp_path: Path, public_url: str
):
    manifest = load_manifest()
    services = tuple(
        replace(service, public_url=public_url) if service.name == "frontend" else service
        for service in manifest.services
    )
    poisoned = replace(manifest, services=services)
    with pytest.raises(ValueError, match="invalid local public URL"):
        runtime_manifest(poisoned, root=tmp_path, environ={})
    with pytest.raises(ValueError, match="invalid local public URL"):
        public_service_urls(tmp_path, manifest=poisoned, environ={})
    with pytest.raises(ValueError, match="non-local public URL"):
        runtime_manifest(poisoned, root=tmp_path, environ={"FRONTEND_PORT": "31999"})


@pytest.mark.parametrize("port", [
    "9" * 5000,
    "000001",
    "65536",
    "0",
    "１２３４",
])
def test_host_port_input_is_bounded_before_integer_conversion(tmp_path: Path, port: str):
    """Malformed operator input fails with the documented error, not an int overflow."""
    with pytest.raises(ValueError, match="FRONTEND_PORT must be an integer from 1 to 65535"):
        runtime_manifest(load_manifest(), root=tmp_path, environ={"FRONTEND_PORT": port})


def test_manifest_rejects_direct_dependency_cycle():
    from skeleton.app.assembly import parse_manifest
    import json
    from skeleton.app.assembly import _manifest_bytes

    payload = json.loads(_manifest_bytes().decode("utf-8"))
    services = {service["name"]: service for service in payload["services"]}
    services["backend"]["depends_on"] = ["skeleton"]
    services["skeleton"]["depends_on"] = ["backend"]
    with pytest.raises(ValueError, match="dependency cycle"):
        parse_manifest(payload)


def test_manifest_rejects_optional_service_dependency_cycle():
    from skeleton.app.assembly import parse_manifest, _manifest_bytes
    import json

    payload = json.loads(_manifest_bytes().decode("utf-8"))
    services = payload["services"]
    services.append({
        "name": "optional_cycle_a", "role": "test", "path": ".", "kind": "service",
        "depends_on": ["optional_cycle_b"],
    })
    services.append({
        "name": "optional_cycle_b", "role": "test", "path": ".", "kind": "service",
        "depends_on": ["optional_cycle_a"],
    })
    with pytest.raises(ValueError, match="dependency cycle"):
        parse_manifest(payload)


def test_deep_dependency_chain_is_iterative():
    from skeleton.app.assembly import parse_manifest, _manifest_bytes
    import json
    payload = json.loads(_manifest_bytes().decode("utf-8"))
    for index in range(1200):
        payload["services"].append({
            "name": f"deep_service_{index}", "role": "test",
            "path": ".", "kind": "service",
            "depends_on": [f"deep_service_{index - 1}"] if index else [],
        })
    assert "deep_service_1199" in parse_manifest(payload).service_names


def test_deep_dependency_cycle_fails_closed():
    from skeleton.app.assembly import parse_manifest, _manifest_bytes
    import json
    payload = json.loads(_manifest_bytes().decode("utf-8"))
    for index in range(1200):
        payload["services"].append({
            "name": f"cycle_service_{index}", "role": "test",
            "path": ".", "kind": "service",
            "depends_on": [f"cycle_service_{index + 1}"] if index < 1199 else ["cycle_service_0"],
        })
    with pytest.raises(ValueError, match="dependency cycle"):
        parse_manifest(payload)


@pytest.mark.parametrize("port", [
    True, False, 0, -1, 65536, 3.5, "8000", "9" * 5000, [],
])
def test_manifest_rejects_noninteger_or_out_of_range_container_port(port):
    from skeleton.app.assembly import ServiceSpec
    with pytest.raises(ValueError, match="container_port must be an integer from 1 to 65535"):
        ServiceSpec.from_mapping({
            "name": "hostile", "role": "test", "path": ".", "kind": "service",
            "depends_on": [], "container_port": port,
        })


def test_manifest_accepts_bounded_integer_container_port():
    from skeleton.app.assembly import ServiceSpec
    for port in (1, 8000, 65535):
        service = ServiceSpec.from_mapping({
            "name": "valid", "role": "test", "path": ".", "kind": "service",
            "depends_on": [], "container_port": port,
        })
        assert service.container_port == port
