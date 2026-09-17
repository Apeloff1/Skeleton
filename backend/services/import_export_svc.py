"""
services/import_export_svc.py — ImportExport service.

Extracted from server.py (Feb 2026 Phase-7). Self-contained: re-implements
the original ImportExportService class with **identical public surface**
and **identical singleton name** (``import_export``). Server.py keeps a
back-compat shim so callers that do ``from server import import_export``
work unchanged.
"""
from __future__ import annotations

import html
import re
from datetime import datetime


class ImportExportService:
    """Handle file import/export in multiple formats."""

    SUPPORTED_IMPORT_FORMATS = ["py", "js", "ts", "jsx", "tsx", "html", "css", "json", "md", "txt", "yaml", "yml", "xml", "csv"]
    SUPPORTED_EXPORT_FORMATS = ["txt", "html", "md", "json"]

    def import_file(self, filename: str, content: str) -> dict:
        """Import a file and return parsed metadata."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
        language_map = {
            "py": "python", "js": "javascript", "ts": "typescript",
            "jsx": "javascript", "tsx": "typescript", "html": "html",
            "css": "css", "json": "json", "md": "markdown",
            "yaml": "yaml", "yml": "yaml", "xml": "xml", "csv": "csv",
            "txt": "plaintext",
        }
        return {
            "filename": filename,
            "language": language_map.get(ext, "plaintext"),
            "content": content,
            "size": len(content),
            "lines": len(content.splitlines()),
            "imported_at": datetime.utcnow().isoformat(),
            "metadata": self._analyze_content(content, language_map.get(ext, "plaintext")),
        }

    def export_file(self, content: str, language: str, format: str = "txt", options: dict | None = None) -> dict:
        """Export content in the requested format."""
        options = options or {}
        if format == "html":
            exported = self._code_to_html(content, language, options)
            mime = "text/html"
        elif format == "md":
            exported = self._code_to_markdown(content, language)
            mime = "text/markdown"
        elif format == "json":
            import json
            exported = json.dumps({"language": language, "content": content}, indent=2)
            mime = "application/json"
        else:
            exported = content
            mime = "text/plain"
        return {"content": exported, "mime_type": mime, "format": format}

    def _code_to_markdown(self, code: str, language: str) -> str:
        return f"```{language}\n{code}\n```"

    def _analyze_content(self, content: str, language: str) -> dict:
        lines = content.splitlines()
        metadata = {
            "line_count": len(lines),
            "char_count": len(content),
            "functions": [],
            "classes": [],
            "comments_ratio": 0,
        }
        comment_lines = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("#", "//", "/*", "*")):
                comment_lines += 1
            if language == "python" and stripped.startswith("def "):
                m = re.search(r"def\s+(\w+)", stripped)
                if m:
                    metadata["functions"].append(m.group(1))
            if language in ("javascript", "typescript") and "function " in stripped:
                m = re.search(r"function\s+(\w+)", stripped)
                if m:
                    metadata["functions"].append(m.group(1))
            if language == "python" and stripped.startswith("class "):
                metadata["classes"].append(stripped[6:].split("(")[0].split(":")[0])
        if lines:
            metadata["comments_ratio"] = round(comment_lines / len(lines) * 100, 1)
        return metadata

    def _code_to_html(self, code: str, language: str, options: dict) -> str:
        theme      = options.get("theme", "dark")
        bg_color   = "#1E1E1E" if theme == "dark" else "#FFFFFF"
        text_color = "#D4D4D4" if theme == "dark" else "#000000"
        escaped    = html.escape(code, quote=True)
        label      = html.escape(str(language or "text"), quote=True)
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
    <title>CodeDock Export</title>
    <style>
        body {{ background: {bg_color}; color: {text_color}; font-family: 'Fira Code', monospace; padding: 20px; }}
        pre  {{ background: {bg_color}; padding: 20px; border-radius: 8px; overflow-x: auto; }}
        .header {{ color: #888; margin-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="header">Language: {label} | Exported from CodeDock v9.0.0</div>
    <pre><code>{escaped}</code></pre>
</body>
</html>"""


import_export = ImportExportService()

__all__ = ["ImportExportService", "import_export"]