from __future__ import annotations

import json

import pytest
from zipfile import ZipFile

from core.gameforge_artifact_builder import build_source_artifact, build_web_artifact
from skeleton.artifact_plane.usage import ArtifactUsageMeter
from skeleton.intelligence.admission import (
    AdmissionError,
    AdmissionRequest,
    ResourceBudget,
    UsageEstimate,
)
from skeleton.intelligence.admission_runtime import AdmissionRuntime
from skeleton.intelligence.quota import TenantQuota, TenantQuotaLedger


def _artifact_runtime(
    *,
    max_artifact_bytes: int,
) -> tuple[AdmissionRuntime, ArtifactUsageMeter]:
    ledger = TenantQuotaLedger()
    ledger.configure(
        "tenant-artifact",
        TenantQuota(
            window_id="artifact-window",
            max_operations=10,
            max_input_tokens=10_000,
            max_output_tokens=10_000,
            max_cost_usd=10.0,
            max_tool_calls=100,
            max_artifact_bytes=max_artifact_bytes,
            max_concurrent_operations=4,
        ),
    )
    runtime = AdmissionRuntime(quota_ledger=ledger)
    return runtime, ArtifactUsageMeter(runtime)


def _admit_artifact_operation(
    runtime: AdmissionRuntime,
    operation_id: str,
    *,
    max_artifact_bytes: int,
) -> None:
    runtime.admit(
        AdmissionRequest(
            operation_id=operation_id,
            tenant_id="tenant-artifact",
            capability="artifact-build",
            budget=ResourceBudget(
                max_input_tokens=10_000,
                max_output_tokens=10_000,
                max_cost_usd=10.0,
                max_wall_seconds=30.0,
                max_provider_attempts=1,
                max_tool_calls=10,
                max_artifact_bytes=max_artifact_bytes,
                max_concurrency=4,
                max_queue_depth=10,
            ),
            estimate=UsageEstimate(),
        ),
        now_wall=10.0,
    )


def test_web_artifact_escapes_html_and_contains_runtime_payload(tmp_path):
    result = build_web_artifact(
        "<img onerror=x>",
        files=[
            {
                "filename": "<b>main.js</b>",
                "metadata": {"kind": "<script>"},
                "content": "console.log('ok')",
            }
        ],
        artifacts_root=tmp_path,
        build_token="web-test",
    )

    assert result["ok"] is True
    assert result["kind"] == "web"
    assert len(result["sha256"]) == 64

    with ZipFile(tmp_path / result["filename"]) as archive:
        html = archive.read("index.html").decode("utf-8")
        payload = json.loads(archive.read("game_data.json"))

    assert "<img onerror=x>" not in html
    assert "&lt;img onerror=x&gt;" in html
    assert "\\u003cimg onerror=x\\u003e" in html
    assert "<b>main.js</b>" not in html
    assert "&lt;b&gt;main.js&lt;/b&gt;" in html
    assert payload["files"][0]["content"] == "console.log('ok')"


def test_source_artifact_flattens_traversal_and_deduplicates_names(tmp_path):
    result = build_source_artifact(
        "demo",
        files=[
            {"filename": "../../evil.py", "content": "first"},
            {"filename": r"..\\..\\evil.py", "content": "second"},
            {"filename": "", "content": "fallback"},
        ],
        artifacts_root=tmp_path,
        build_token="source-test",
    )

    with ZipFile(tmp_path / result["filename"]) as archive:
        names = archive.namelist()
        manifest = json.loads(archive.read("manifest.json"))

    assert "../" not in "\n".join(names)
    assert "gamefiles/evil.py" in names
    assert "gamefiles/evil-1.py" in names
    assert "gamefiles/file-2.txt" in names
    assert manifest["file_count"] == 3


def test_deterministic_build_token_reuses_same_artifact_identity(tmp_path):
    first = build_source_artifact(
        "demo",
        files=[{"filename": "main.py", "content": "print(1)"}],
        artifacts_root=tmp_path,
        build_token="operation-123",
        built_at=1_700_000_000,
    )
    second = build_source_artifact(
        "demo",
        files=[{"filename": "main.py", "content": "print(1)"}],
        artifacts_root=tmp_path,
        build_token="operation-123",
        built_at=1_700_000_000,
    )

    assert second["build_id"] == first["build_id"]
    assert second["filename"] == first["filename"]
    assert second["sha256"] == first["sha256"]

def test_source_artifact_meters_exact_committed_archive_bytes(tmp_path):
    runtime, meter = _artifact_runtime(max_artifact_bytes=1_000_000)
    _admit_artifact_operation(
        runtime,
        "artifact-op",
        max_artifact_bytes=1_000_000,
    )

    result = build_source_artifact(
        "metered",
        files=[{"filename": "main.py", "content": "print('metered')"}],
        artifacts_root=tmp_path,
        build_token="metered-build",
        built_at=1_700_000_000,
        usage_meter=meter,
        operation_id="artifact-op",
        write_id="archive-v1",
    )

    final_path = tmp_path / result["filename"]
    completion = runtime.complete(
        "artifact-op",
        UsageEstimate(),
        now_wall=11.0,
    )

    assert final_path.is_file()
    assert result["size_bytes"] == final_path.stat().st_size
    assert completion.quota_completion is not None
    assert (
        completion.quota_completion.actual.artifact_bytes
        == final_path.stat().st_size
    )


def test_quota_rejection_does_not_replace_existing_artifact(tmp_path):
    original = build_source_artifact(
        "metered",
        files=[{"filename": "main.py", "content": "print('original')"}],
        artifacts_root=tmp_path,
        build_token="stable-build",
        built_at=1_700_000_000,
    )
    final_path = tmp_path / original["filename"]
    before = final_path.read_bytes()

    runtime, meter = _artifact_runtime(max_artifact_bytes=1)
    _admit_artifact_operation(
        runtime,
        "artifact-reject",
        max_artifact_bytes=1_000_000,
    )

    with pytest.raises(AdmissionError, match="artifact_bytes"):
        build_source_artifact(
            "metered",
            files=[{"filename": "main.py", "content": "print('replacement')"}],
            artifacts_root=tmp_path,
            build_token="stable-build",
            built_at=1_700_000_001,
            usage_meter=meter,
            operation_id="artifact-reject",
            write_id="archive-replacement",
        )

    assert final_path.read_bytes() == before
    assert list(tmp_path.glob("*.pending")) == []
