from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "dependency-security.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _container_job(text: str) -> str:
    start = text.index("  container-audit:")
    return text[start:]


def test_all_deployable_images_are_in_container_security_matrix() -> None:
    job = _container_job(_text())
    for name in ("root", "backend", "frontend"):
        assert f"- name: {name}" in job
        assert f"skeleton-{name}:security-scan" in job


def test_high_and_critical_vulnerabilities_remain_release_blocking() -> None:
    job = _container_job(_text())
    scan = job[job.index("Fail on high or critical container vulnerabilities") :]
    scan = scan[: scan.index("Generate container CycloneDX SBOM")]
    assert "severity: HIGH,CRITICAL" in scan
    assert "ignore-unfixed: false" in scan
    assert "exit-code: 1" in scan
    assert "scan-type: image" in scan
    assert "scan-ref: ${{ matrix.image }}" in scan


def test_each_scanned_image_emits_a_retained_cyclonedx_sbom() -> None:
    job = _container_job(_text())
    assert "Generate container CycloneDX SBOM" in job
    assert "format: cyclonedx" in job
    assert (
        "output: ${{ runner.temp }}/container-${{ matrix.name }}-sbom.cdx.json"
        in job
    )
    assert "Validate generated container SBOM" in job
    assert 'payload.get("bomFormat") != "CycloneDX"' in job
    assert "Retain container SBOM as security evidence" in job
    assert (
        "name: container-${{ matrix.name }}-cyclonedx-sbom-${{ github.sha }}"
        in job
    )
    assert "if-no-files-found: error" in job
    assert "retention-days: 30" in job


def test_sbom_is_generated_only_after_blocking_vulnerability_scan() -> None:
    job = _container_job(_text())
    blocking = job.index("Fail on high or critical container vulnerabilities")
    sbom = job.index("Generate container CycloneDX SBOM")
    upload = job.index("Retain container SBOM as security evidence")
    assert blocking < sbom < upload


def test_supply_chain_actions_remain_immutable_sha_pinned() -> None:
    job = _container_job(_text())
    uses = re.findall(r"^\s*uses:\s*([^\s#]+)", job, flags=re.MULTILINE)
    assert uses
    for action in uses:
        assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), action
