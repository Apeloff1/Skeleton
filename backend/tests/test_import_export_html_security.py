from __future__ import annotations

import pytest

from services.import_export_svc import ImportExportService


@pytest.mark.asyncio
async def test_html_export_escapes_code_and_language_and_emits_csp() -> None:
    service = ImportExportService()
    hostile_code = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
    hostile_language = '"><svg/onload=alert(2)>'

    exported = await service.export_file(hostile_code, hostile_language, "html")
    document = exported["content"]

    assert exported["mime_type"] == "text/html"
    assert exported["extension"] == ".html"
    assert "<script>" not in document
    assert "<img src=x" not in document
    assert "<svg/onload" not in document
    assert "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;" in document
    assert "&lt;svg/onload=alert(2)&gt;" in document
    assert "default-src 'none'" in document
    assert "style-src 'unsafe-inline'" in document
    assert "base-uri 'none'" in document
    assert "form-action 'none'" in document
    assert "frame-ancestors 'none'" in document


def test_html_export_defaults_empty_language_label_to_text() -> None:
    service = ImportExportService()

    document = service._code_to_html("print('ok')", "", {})

    assert "Language: text | Exported from CodeDock v9.0.0" in document
