"""
services/import_export_svc.py — ImportExport service.

Extracted from server.py (Feb 2026 Phase-7). Self-contained: re-implements
the original ImportExportService class with **identical public surface**
and **identical singleton name** (``import_export``). Server.py keeps a
back-compat shim so callers that do ``from server import import_export``
work unchanged.
"""
from __future__ import annotations

import re
from datetime import datetime


class ImportExportService:
    """Handle file import/export in multiple formats."""

    SUPPORTED_IMPORT_FORMATS = [
        "txt", "py", "js", "ts", "cpp", "c", "h", "hpp", "java", "kt", "swift",
        "rs", "go", "rb", "php", "html", "css", "scss", "json", "yaml", "yml",
        "xml", "md", "sql", "sh", "bash", "ps1", "r", "jl", "lua", "pl", "ex",
        "exs", "hs", "ml", "fs", "clj", "scala", "dart", "sol", "v", "vhd",
        "asm", "s", "wat", "tex", "typ", "toml", "ini", "cfg", "dockerfile",
        "makefile", "cmake", "gradle", "sbt", "cabal", "cargo", "package",
    ]

    SUPPORTED_EXPORT_FORMATS = ["txt", "html", "pdf", "md", "json", "zip"]

    async def import_file(self, content: str, filename: str, format_hint: str = None) -> dict:
        """Import a file and detect its language."""
        extension = filename.split(".")[-1].lower() if "." in filename else (format_hint or "")
        language  = self._detect_language(content, extension)
        metadata  = self._extract_metadata(content, language)
        return {
            "success":     True,
            "filename":    filename,
            "language":    language,
            "content":     content,
            "metadata":    metadata,
            "line_count":  len(content.splitlines()),
            "char_count":  len(content),
        }

    async def export_file(self, code: str, language: str, format: str, options: dict = None) -> dict:
        """Export code in various formats."""
        options = options or {}
        if format == "txt":
            return {"content": code, "mime_type": "text/plain", "extension": ".txt"}
        if format == "html":
            html = self._code_to_html(code, language, options)
            return {"content": html, "mime_type": "text/html", "extension": ".html"}
        if format == "md":
            md = f"```{language}\n{code}\n```"
            return {"content": md, "mime_type": "text/markdown", "extension": ".md"}
        if format == "json":
            import json
            data = {
                "code":        code,
                "language":    language,
                "exported_at": datetime.utcnow().isoformat(),
                "version":     "9.0.0",
            }
            return {"content": json.dumps(data, indent=2), "mime_type": "application/json", "extension": ".json"}
        return {"error": f"Unsupported format: {format}"}

    def _detect_language(self, content: str, extension: str) -> str:
        extension_map = {
            "py": "python",     "js": "javascript", "ts": "typescript",
            "cpp": "cpp",       "c": "c",           "h": "c",           "hpp": "cpp",
            "java": "java",     "kt": "kotlin",     "swift": "swift",
            "rs": "rust",       "go": "go",         "rb": "ruby",       "php": "php",
            "html": "html",     "css": "css",       "scss": "scss",
            "json": "json",     "yaml": "yaml",     "yml": "yaml",
            "xml": "xml",       "md": "markdown",   "sql": "sql",
            "sh": "bash",       "bash": "bash",     "ps1": "powershell",
            "r": "r",           "jl": "julia",      "lua": "lua",       "pl": "perl",
            "ex": "elixir",     "exs": "elixir",    "hs": "haskell",
            "ml": "ocaml",      "fs": "f_sharp",    "clj": "clojure",
            "scala": "scala",   "dart": "dart",     "sol": "solidity",
            "v": "verilog",     "vhd": "vhdl",      "asm": "assembly_x86",
            "s": "assembly_arm","wat": "webassembly",
            "tex": "latex",     "typ": "typst",     "toml": "toml",
        }
        if extension in extension_map:
            return extension_map[extension]
        # Content-based fallback
        if content.startswith("#!/usr/bin/env python") or "import " in content[:100]:
            return "python"
        if "function " in content[:100] or "const " in content[:100]:
            return "javascript"
        if "#include" in content[:100]:
            return "cpp"
        return "text"

    def _extract_metadata(self, content: str, language: str) -> dict:
        metadata: dict = {
            "functions":       [],
            "classes":         [],
            "imports":         [],
            "comments_ratio":  0,
        }
        lines         = content.splitlines()
        comment_lines = 0
        for line in lines:
            stripped = line.strip()
            if language == "python" and stripped.startswith("#"):
                comment_lines += 1
            elif language in ("javascript", "typescript", "cpp", "c", "java") and stripped.startswith("//"):
                comment_lines += 1
            if language == "python" and stripped.startswith("def "):
                metadata["functions"].append(stripped[4:].split("(")[0])
            elif language == "javascript" and "function " in stripped:
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
        escaped    = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>CodeDock Export</title>
    <style>
        body {{ background: {bg_color}; color: {text_color}; font-family: 'Fira Code', monospace; padding: 20px; }}
        pre  {{ background: {bg_color}; padding: 20px; border-radius: 8px; overflow-x: auto; }}
        .header {{ color: #888; margin-bottom: 10px; }}
    </style>
</head>
<body>
    <div class="header">Language: {language} | Exported from CodeDock v9.0.0</div>
    <pre><code>{escaped}</code></pre>
</body>
</html>"""


import_export = ImportExportService()

__all__ = ["ImportExportService", "import_export"]
