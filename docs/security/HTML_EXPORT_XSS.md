# HTML export escaping boundary

HTML exports are an executable browser surface. Every caller-controlled value inserted into the generated document must be HTML-escaped before interpolation.

The canonical `ImportExportService` escapes both source-code content and the language label. Theme selection is mapped to fixed style values rather than interpolated into CSS.

`backend/tests/test_import_export_html_security.py` pins this boundary and is part of the canonical quality/security gate.
