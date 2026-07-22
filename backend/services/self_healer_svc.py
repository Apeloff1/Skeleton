"""
services/self_healer.py — SelfHealing service.

Extracted from server.py (Feb 2026 Phase-7). Self-contained — no parent
imports needed. The singleton ``self_healer`` is also re-exported from
server.py at boot via a back-compat shim so existing references
(``hub_tools._srv().self_healer``) continue to work.

Includes the **2026-02 BUGFIX** for ``organize_library``: previously it
crashed with ``AttributeError: 'str' object has no attribute 'get'``
when given a list of plain string filenames. Now it gracefully coerces
string entries into ``{"filename": s, "language": <ext-detected>}``.
"""
from __future__ import annotations

from typing import List


class SelfHealingService:
    """Self-healing and self-organizing system."""

    def __init__(self):
        self.health_checks: list = []
        self.recovery_actions: list = []

    async def diagnose(self, error: dict) -> dict:
        """Diagnose an error and suggest fixes."""
        error_type = error.get("type", "unknown")
        message    = error.get("message", "")

        diagnosis = {
            "error_type":      error_type,
            "severity":        self._assess_severity(error),
            "possible_causes": [],
            "suggested_fixes": [],
            "auto_fixable":    False,
        }

        msg_l = message.lower()
        if "syntax" in msg_l:
            diagnosis["possible_causes"] = ["Syntax error in code", "Missing bracket or semicolon", "Invalid character"]
            diagnosis["suggested_fixes"] = ["Check line indicated for typos", "Verify bracket matching", "Use linter"]
            diagnosis["auto_fixable"]    = True
        elif "import" in msg_l or "module" in msg_l:
            diagnosis["possible_causes"] = ["Missing module", "Incorrect import path", "Module not installed"]
            diagnosis["suggested_fixes"] = ["Install missing package", "Check import statement", "Verify module name"]
        elif "memory" in msg_l:
            diagnosis["possible_causes"] = ["Memory leak", "Large data structure", "Infinite loop"]
            diagnosis["suggested_fixes"] = ["Profile memory usage", "Optimize data structures", "Check loop conditions"]
        elif "timeout" in msg_l:
            diagnosis["possible_causes"] = ["Infinite loop", "Slow algorithm", "Network issue"]
            diagnosis["suggested_fixes"] = ["Check loop termination", "Optimize algorithm", "Increase timeout"]
        return diagnosis

    def _assess_severity(self, error: dict) -> str:
        message = error.get("message", "").lower()
        if "fatal" in message or "crash" in message:
            return "critical"
        if "error" in message:
            return "high"
        if "warning" in message:
            return "medium"
        return "low"

    async def auto_fix(self, code: str, error: dict) -> dict:
        """Attempt automatic fix for common errors."""
        fixes_applied: list[str] = []
        fixed_code               = code
        error_msg = error.get("message", "")

        if "expected ';'" in error_msg:
            line  = error.get("line", 0)
            lines = fixed_code.split("\n")
            if 0 < line <= len(lines):
                if not lines[line - 1].rstrip().endswith(";"):
                    lines[line - 1] = lines[line - 1].rstrip() + ";"
                    fixes_applied.append(f"Added semicolon at line {line}")
            fixed_code = "\n".join(lines)

        if "expected ':'" in error_msg:
            line  = error.get("line", 0)
            lines = fixed_code.split("\n")
            if 0 < line <= len(lines):
                if not lines[line - 1].rstrip().endswith(":"):
                    lines[line - 1] = lines[line - 1].rstrip() + ":"
                    fixes_applied.append(f"Added colon at line {line}")
            fixed_code = "\n".join(lines)

        return {
            "success":        len(fixes_applied) > 0,
            "original_code":  code,
            "fixed_code":     fixed_code,
            "fixes_applied": fixes_applied,
        }

    # ── extension-to-language map for the string-input bugfix ─────────────
    _EXT_LANG_MAP: dict[str, str] = {
        "py": "python",     "js": "javascript", "ts": "typescript",
        "tsx": "typescript","jsx": "javascript","cpp": "cpp",
        "c": "c",           "h": "c",           "hpp": "cpp",
        "java": "java",     "kt": "kotlin",     "swift": "swift",
        "rs": "rust",       "go": "go",         "rb": "ruby",
        "php": "php",       "html": "html",     "css": "css",
        "scss": "scss",     "json": "json",     "yaml": "yaml",
        "yml": "yaml",      "xml": "xml",       "md": "markdown",
        "sql": "sql",       "sh": "bash",       "bash": "bash",
        "r": "r",           "jl": "julia",      "lua": "lua",
        "pl": "perl",       "ex": "elixir",     "exs": "elixir",
        "hs": "haskell",    "ml": "ocaml",      "fs": "f_sharp",
        "clj": "clojure",   "scala": "scala",   "dart": "dart",
        "sol": "solidity",
    }

    def _coerce_file(self, raw) -> dict:
        """★ 2026-02 BUGFIX: tolerate plain string filenames in ``files[]``.

        Returns a dict shape ``{filename, language}`` regardless of input.
        Older clients pass in arbitrary strings; the original implementation
        crashed with ``AttributeError: 'str' object has no attribute 'get'``.
        """
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            ext  = raw.split(".")[-1].lower() if "." in raw else ""
            lang = self._EXT_LANG_MAP.get(ext, "unknown")
            return {"filename": raw, "language": lang}
        # Unknown shape — wrap so we never crash.
        return {"filename": str(raw), "language": "unknown"}

    async def organize_library(self, files: List) -> dict:  # noqa: UP006
        """Self-organizing library storage.

        Accepts both ``["a.py", "b.js"]`` and ``[{"filename":"a.py", "language":"python"}]``.
        """
        organized: dict = {
            "by_language": {},
            "by_date":     {},
            "by_project":  {},
            "suggestions": [],
        }
        for raw in files:
            f    = self._coerce_file(raw)
            lang = f.get("language", "unknown") or "unknown"
            organized["by_language"].setdefault(lang, []).append(f)

        for lang, files_list in organized["by_language"].items():
            if len(files_list) > 10:
                organized["suggestions"].append({
                    "type":     "create_folder",
                    "language": lang,
                    "message":  f"Consider creating a '{lang}' folder for {len(files_list)} files",
                })
        return organized


self_healer = SelfHealingService()

__all__ = ["SelfHealingService", "self_healer"]
