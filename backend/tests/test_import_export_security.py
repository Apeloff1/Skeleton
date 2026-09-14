from __future__ import annotations

import asyncio

from services.import_export_svc import ImportExportService


def _export(code: str, language: str, format_name: str) -> dict:
    service = ImportExportService()
    return asyncio.run(service.export_file(code, language, format_name))


def test_html_export_escapes_language_metadata_and_code():
    result = _export(
        '<script>alert("code")</script>',
        'python</div><script>alert("lang")</script>',
        "html",
    )
    body = result["content"]

    assert "<script>" not in body
    assert "</div><script>" not in body
    assert '&lt;script&gt;alert(&quot;code&quot;)' in body
    assert "pythondivscriptalertlangscript" in body
    assert "Content-Security-Policy" in body


def test_markdown_export_uses_longer_fence_than_untrusted_code():
    result = _export("before\n```\ninjected\n```\nafter", "python", "md")
    lines = result["content"].splitlines()

    assert lines[0].startswith("````python")
    assert lines[-1] == "````"


def test_markdown_language_info_string_is_restricted():
    result = _export("print('ok')", "python\n<script>alert(1)</script>", "md")
    first_line = result["content"].splitlines()[0]

    assert "\n" not in first_line
    assert "<" not in first_line
    assert ">" not in first_line
    assert first_line.startswith("```python")
