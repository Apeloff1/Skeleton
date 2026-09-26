from __future__ import annotations

import hashlib
import io
import json
from types import SimpleNamespace

import pytest
from zipfile import ZipFile

from core.gameforge_artifact_builder import build_source_artifact, build_web_artifact


class ArtifactBudgetExceeded(RuntimeError):
    pass




class FakeGovernedArtifactStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], bytes] = {}
        self.calls: list[dict[str, object]] = []

    def write_bytes(
        self,
        *,
        tenant_id: str,
        artifact_id: str,
        payload: bytes,
        data_class: str = "internal",
        purposes: tuple[str, ...] = ("artifact-delivery",),
        created_at: float | None = None,
        retention_until: float | None = None,
        exportable: bool = True,
    ):
        self.rows[(tenant_id, artifact_id)] = bytes(payload)
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "artifact_id": artifact_id,
                "data_class": data_class,
                "purposes": purposes,
                "created_at": created_at,
                "retention_until": retention_until,
                "exportable": exportable,
            }
        )
        return SimpleNamespace(
            record_id="artifact-record-" + artifact_id,
            source_ref=f"artifact://{tenant_id}/{artifact_id}",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )

    def read_bytes(self, tenant_id: str, artifact_id: str) -> bytes | None:
        return self.rows.get((tenant_id, artifact_id))

class FakeArtifactUsageMeter:
    def __init__(self, *, max_bytes: int | None = None) -> None:
        self.max_bytes = max_bytes
        self.calls: list[tuple[str, str, str, int]] = []

    def meter_artifact(
        self,
        operation_id: str,
        artifact_id: str,
        write_id: str,
        byte_count: int,
        *,
        now_wall: float | None = None,
    ) -> object:
        del now_wall
        if self.max_bytes is not None and byte_count > self.max_bytes:
            raise ArtifactBudgetExceeded("artifact byte budget exceeded")
        self.calls.append(
            (operation_id, artifact_id, write_id, byte_count)
        )
        return object()


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
    meter = FakeArtifactUsageMeter()

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

    assert final_path.is_file()
    assert result["size_bytes"] == final_path.stat().st_size
    assert meter.calls == [
        (
            "artifact-op",
            result["build_id"],
            "archive-v1",
            final_path.stat().st_size,
        )
    ]


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

    meter = FakeArtifactUsageMeter(max_bytes=1)

    with pytest.raises(ArtifactBudgetExceeded, match="artifact byte budget"):
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

def test_governed_source_artifact_is_canonical_without_raw_final_zip(tmp_path):
    store = FakeGovernedArtifactStore()

    result = build_source_artifact(
        "governed",
        files=[{"filename": "main.py", "content": "print('governed')"}],
        artifacts_root=tmp_path,
        build_token="governed-build",
        built_at=1_700_000_000,
        governed_store=store,
        tenant_id="tenant-a",
        data_class="confidential",
        retention_until=1_800_000_000,
    )

    assert result["ok"] is True
    assert result["tenant_id"] == "tenant-a"
    assert result["path"] is None
    assert result["source_ref"] == (
        f"artifact://tenant-a/{result['build_id']}"
    )
    assert result["governance_record_id"] == (
        "artifact-record-" + result["build_id"]
    )
    assert not (tmp_path / result["filename"]).exists()
    assert list(tmp_path.glob("*.pending")) == []

    payload = store.read_bytes("tenant-a", result["build_id"])
    assert payload is not None
    assert hashlib.sha256(payload).hexdigest() == result["sha256"]
    with ZipFile(io.BytesIO(payload)) as archive:
        assert archive.read("gamefiles/main.py") == b"print('governed')"

    assert store.calls == [
        {
            "tenant_id": "tenant-a",
            "artifact_id": result["build_id"],
            "data_class": "confidential",
            "purposes": ("artifact-delivery", "download"),
            "created_at": 1_700_000_000.0,
            "retention_until": 1_800_000_000,
            "exportable": True,
        }
    ]


def test_governed_artifact_requires_tenant_before_canonical_write(tmp_path):
    store = FakeGovernedArtifactStore()

    with pytest.raises(
        ValueError,
        match="tenant_id is required",
    ):
        build_source_artifact(
            "governed",
            files=[{"filename": "main.py", "content": "print('no tenant')"}],
            artifacts_root=tmp_path,
            build_token="missing-tenant",
            governed_store=store,
        )

    assert store.calls == []
    assert list(tmp_path.glob("*.zip")) == []
    assert list(tmp_path.glob("*.pending")) == []

