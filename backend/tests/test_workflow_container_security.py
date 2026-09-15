from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_container_security import violations


DIGEST = "a" * 64


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_accepts_digest_pinned_service_image(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{contents: read}}\njobs:\n  test:\n    services:\n      mongodb:\n        image: mongo@sha256:{DIGEST}\n    steps:\n      - run: echo safe\n",
    )
    assert findings == []


def test_rejects_mutable_service_tag(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions: {contents: read}\njobs:\n  test:\n    services:\n      mongodb:\n        image: mongo:7.0\n    steps:\n      - run: echo unsafe\n",
    )
    assert any("must be pinned to an immutable sha256 digest" in finding for finding in findings)


def test_rejects_mutable_job_container_tag(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions: {contents: read}\njobs:\n  test:\n    container: python:3.11\n    steps:\n      - run: python --version\n",
    )
    assert any("python:3.11" in finding for finding in findings)


def test_accepts_mapping_job_container_digest(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{contents: read}}\njobs:\n  test:\n    container:\n      image: ghcr.io/example/runtime@sha256:{DIGEST}\n    steps:\n      - run: echo safe\n",
    )
    assert findings == []


def test_rejects_dynamic_container_reference(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions: {contents: read}\njobs:\n  test:\n    container: ${{ matrix.image }}\n    steps:\n      - run: echo unsafe\n",
    )
    assert any("matrix.image" in finding for finding in findings)


def test_rejects_flow_style_mutable_service_image(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions: {contents: read}\njobs:\n  test:\n    services: {mongodb: {image: mongo:7.0}}\n    steps:\n      - run: echo unsafe\n",
    )
    assert any("mongo:7.0" in finding for finding in findings)


def test_accepts_flow_style_digest_service_image(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{contents: read}}\njobs:\n  test:\n    services: {{mongodb: {{image: mongo@sha256:{DIGEST}}}}}\n    steps:\n      - run: echo safe\n",
    )
    assert findings == []


def test_rejects_privileged_service(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{contents: read}}\njobs:\n  test:\n    services:\n      db:\n        image: mongo@sha256:{DIGEST}\n        options: --privileged\n    steps:\n      - run: echo unsafe\n",
    )
    assert any("privileged container mode" in finding for finding in findings)


def test_rejects_flow_style_privileged_service(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{contents: read}}\njobs:\n  test:\n    services: {{db: {{image: mongo@sha256:{DIGEST}, options: --privileged}}}}\n    steps:\n      - run: echo unsafe\n",
    )
    assert any("privileged container mode" in finding for finding in findings)


def test_rejects_block_scalar_options_to_prevent_parser_bypass(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{contents: read}}\njobs:\n  test:\n    container:\n      image: ubuntu@sha256:{DIGEST}\n      options: >-\n        --privileged\n    steps:\n      - run: echo unsafe\n",
    )
    assert any("block-scalar GitHub Actions container options are forbidden" in finding for finding in findings)


def test_rejects_host_namespace_options(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{contents: read}}\njobs:\n  test:\n    container:\n      image: ubuntu@sha256:{DIGEST}\n      options: --network=host --pid host --ipc=host\n    steps:\n      - run: echo unsafe\n",
    )
    assert any("host network namespace" in finding for finding in findings)
    assert any("host PID namespace" in finding for finding in findings)
    assert any("host IPC namespace" in finding for finding in findings)


def test_rejects_device_capability_and_socket_mounts(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{contents: read}}\njobs:\n  test:\n    container:\n      image: ubuntu@sha256:{DIGEST}\n      options: --device /dev/kvm --cap-add SYS_ADMIN -v /var/run/docker.sock:/var/run/docker.sock\n    steps:\n      - run: echo unsafe\n",
    )
    assert any("device passthrough" in finding for finding in findings)
    assert any("Linux capability elevation" in finding for finding in findings)
    assert any("Docker daemon socket mount" in finding for finding in findings)


def test_rejects_unconfined_security_profile(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions: {{contents: read}}\njobs:\n  test:\n    container:\n      image: ubuntu@sha256:{DIGEST}\n      options: --security-opt seccomp=unconfined\n    steps:\n      - run: echo unsafe\n",
    )
    assert any("unconfined security profile" in finding for finding in findings)
