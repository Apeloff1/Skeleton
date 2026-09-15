from __future__ import annotations

from services.import_export_svc import ImportExportService


def test_html_export_escapes_language_and_code_metadata() -> None:
    service = ImportExportService()
    payload = service._code_to_html(
        '<script>alert("code")</script>',
        '</div><script>alert("language")</script><div>',
        {"theme": "dark"},
    )

    assert '<script>alert("code")</script>' not in payload
    assert '<script>alert("language")</script>' not in payload
    assert "&lt;script&gt;alert(&quot;code&quot;)&lt;/script&gt;" in payload
    assert "&lt;/div&gt;&lt;script&gt;alert(&quot;language&quot;)&lt;/script&gt;&lt;div&gt;" in payload


def test_html_export_keeps_only_fixed_style_values() -> None:
    service = ImportExportService()
    payload = service._code_to_html("print('ok')", "python", {"theme": "</style><script>x</script>"})

    assert "</style><script>x</script>" not in payload
    assert "background: #FFFFFF" in payload
