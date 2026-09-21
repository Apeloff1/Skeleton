from __future__ import annotations

import json
from zipfile import ZipFile

from core.gameforge_artifact_builder import build_source_artifact, build_web_artifact


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
    )
    second = build_source_artifact(
        "demo",
        files=[{"filename": "main.py", "content": "print(1)"}],
        artifacts_root=tmp_path,
        build_token="operation-123",
    )

    assert second["build_id"] == first["build_id"]
    assert second["filename"] == first["filename"]
    assert second["sha256"] == first["sha256"]
