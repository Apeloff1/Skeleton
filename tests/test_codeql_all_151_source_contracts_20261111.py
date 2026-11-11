"""151 individual alert-to-source qualification checks.

This is structural regression coverage, paired with behavioral tests in the
security branch workflow. Passing is NOT CodeQL reanalysis or evidence that
any alert has been closed or dismissed on the default branch.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/security/codeql-open-151-lineage-2026-11-11.json"
INVENTORY = json.loads(LEDGER.read_text(encoding="utf-8"))
FINDINGS = INVENTORY["findings"]

BEHAVIORAL_REGRESSIONS = {
    "py/stack-trace-exposure": "backend/tests/test_codeql_exception_boundary_20261111.py",
    "py/path-injection": "backend/tests/test_compressed_vault_secure_io.py",
    "py/polynomial-redos": "backend/tests/test_codeql_tts_linear_20261111.py",
    "py/full-ssrf": "backend/tests/test_room_api_egress_admission_20261111.py",
    "py/incomplete-url-substring-sanitization": "backend/tests/test_codeql_origin_guards_20261111.py",
    "py/reflective-xss": "backend/tests/test_share_page_security.py",
    "py/clear-text-storage-sensitive-data": "backend/tests/test_codeql_storage_security_20261111.py",
    "js/insecure-randomness": "frontend/scripts/test-secure-session-identifiers.cjs",
    "js/incomplete-multi-character-sanitization": "frontend/scripts/test-quickwins-prototype-guard.cjs",
    "js/incomplete-sanitization": "frontend/scripts/test-wasm-origin-execution-boundary.cjs",
}


def _source_path(finding: dict) -> Path:
    relative = finding["path"]
    path = ROOT / relative
    if not path.is_file() and relative.startswith("frontend/"):
        path = ROOT / "frontend" / "src" / relative.removeprefix("frontend/")
    assert path.is_file(), f"CodeQL {finding['number']}: missing source {relative}"
    return path


@lru_cache(maxsize=100)
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_route_failure_custody(path: str, source: str) -> bool:
    if path == "backend/gameforge/api/control.py":
        return "install_public_error_handlers(app)" in source
    if path == "backend/routes/gameforge_build.py":
        return "route_class=_PrivateProjectRoute" in source
    if re.search(r"\brouter\s*=\s*project_router\s*\(", source):
        return "class _PrivateProjectRoute(PublicExceptionRoute):" in _read(
            ROOT / "backend/routes/playable_access.py"
        )
    # Includes an APIRouter on server.py and the dedicated hardening_router.
    return (
        "route_class=PublicExceptionRoute" in source
        and "from core.public_exception_route import PublicExceptionRoute" in source
    )


def _has_path_custody(path: str, source: str) -> bool:
    if path == "backend/core/compressed_vault.py":
        required = (
            "anchored_directory", "read_regular", "atomic_write",
            "_safe_name", "_STORAGE_IDENTITY",
        )
    elif path == "backend/routes/build_pipeline.py":
        required = (
            "_storage_build_id", "_owned_binary_build",
            "open_artifact_for_download", "tenant_id", "owner_id",
        )
    elif path == "backend/services/binary_builder.py":
        required = ("_safe_build_id", "anchored_directory", "atomic_write")
    elif path == "backend/gameforge/enterprise/compliance.py":
        required = ("AESGCM", "anchored_directory", "atomic_write")
    else:
        return False
    return all(marker in source for marker in required)


def _has_bounded_regex(path: str, source: str) -> bool:
    if path == "backend/core/expressive_tts.py":
        return (
            "text[:TTS_LIMIT].strip()" in source
            and "emitted: list[str]" in source
            and "casefold()" in source
        )
    if path == "backend/routes/compiler_tools.py":
        return (
            "benchmark_source = request.code[:200_000]" in source
            and 're.findall(r"\bfor\b", benchmark_source)' in source
        )
    return False


def _has_ssrf_custody(path: str, source: str) -> bool:
    if path == "backend/gameforge/knowledge/free_apis.py":
        required = ("_catalog_request_parts", "_pin_public_origin",
                    "is_global", "follow_redirects=False", "trust_env=False")
    elif path == "backend/gameforge/rooms/room_api_gateway.py":
        required = ("_canonical_allowed_host", "_resolve_public_host",
                    "_prepare_external_request", "is_global",
                    "follow_redirects=False", "trust_env=False")
    else:
        return False
    return all(marker in source for marker in required)


@pytest.mark.parametrize(
    "finding", FINDINGS,
    ids=lambda finding: f"CodeQL-{finding['number']}-{finding['rule_id']}",
)
def test_all_151_historical_alerts_have_a_source_boundary(finding):
    source = _read(_source_path(finding))
    rule = finding["rule_id"]
    path = finding["path"]

    if rule == "py/stack-trace-exposure":
        qualified = _has_route_failure_custody(path, source)
    elif rule == "py/path-injection":
        qualified = _has_path_custody(path, source)
    elif rule == "py/polynomial-redos":
        qualified = _has_bounded_regex(path, source)
    elif rule == "py/full-ssrf":
        qualified = _has_ssrf_custody(path, source)
    elif rule == "py/incomplete-url-substring-sanitization":
        helper = (
            "_trusted_build_download_url"
            if "test_final_build.py" in path
            else "_trusted_rust_official_url"
        )
        qualified = helper in source and "urlsplit(" in source
    elif rule == "py/reflective-xss":
        qualified = (
            "html.escape(" in source
            and "script-src 'none'" in source
            and "http-equiv=\"refresh\"" in source
            and "setTimeout(" not in source
            and "img-src 'self'" in source
        )
    elif rule == "py/clear-text-storage-sensitive-data":
        qualified = (
            "_seal_compliance_export" in source
            and "AESGCM(" in source
            and "atomic_write(" in source
        )
    elif rule == "js/insecure-randomness":
        qualified = "Crypto.randomUUID()" in source
    elif rule == "js/incomplete-sanitization":
        qualified = (
            "Isolated compiler runtime unavailable" in source
            and "return refusal(start, language)" in source
            and "runPythonAsync(" not in source
            and "new Function(" not in source
        )
    elif rule == "js/incomplete-multi-character-sanitization":
        qualified = (
            "for (const character of s)" in source
            and "insideTag = false" in source
        )
    else:
        pytest.fail(f"Unexpected unqualified CodeQL rule: {rule}")

    assert qualified, f"CodeQL alert {finding['number']} lacks {rule} custody: {path}"


def test_complete_alert_and_behavioral_contract_inventory():
    assert len(FINDINGS) == len({x["number"] for x in FINDINGS}) == 151
    assert len({x["path"] for x in FINDINGS}) == 65
    assert set(BEHAVIORAL_REGRESSIONS) == {x["rule_id"] for x in FINDINGS}
    assert all((ROOT / test).is_file() for test in BEHAVIORAL_REGRESSIONS.values())
    # No structural marker can legitimately dismiss an alert. Only a new,
    # completed exact-main CodeQL analysis can change its recorded state.
    assert all(x["state_at_inventory"] == "open" for x in FINDINGS)
    assert all(
        x["resolution"] == "requires-current-main-codeql-reanalysis"
        for x in FINDINGS
    )
