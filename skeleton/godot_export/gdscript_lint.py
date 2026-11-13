"""Offline GDScript lint for GF-D (GFL-01..04).

Not a full parser: it catches the defects that break ``--check-only`` or export
in practice and can be detected line-wise: mixed tab/space indentation,
``extends``/``class_name`` after other code, missing preload targets and
duplicate ``class_name`` declarations across a project.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .project import GodotProject, path_to_res

_CLASS_NAME = re.compile(r"^class_name\s+([A-Za-z_][A-Za-z0-9_]*)")
_EXTENDS = re.compile(r"^extends\s+\S+")
_PRELOAD = re.compile(r"""\bpreload\(\s*["'](res://[^"']+)["']\s*\)""")
_ANNOTATION = re.compile(r"^@(tool|icon|static_unload)\b")


@dataclass(frozen=True)
class LintIssue:
    case_id: str
    path: str
    line: int
    message: str


def _strip_comment(line: str) -> str:
    out = []
    quote = ""
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "#":
            break
        out.append(ch)
    return "".join(out)


def lint_source(text: str, res_path: str = "<script>") -> list[LintIssue]:
    issues: list[LintIssue] = []
    file_style: str | None = None
    seen_code = False
    multiline = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if raw.count('"""') % 2 == 1:
            multiline = not multiline
            continue
        if multiline:
            continue
        body = _strip_comment(raw)
        if not body.strip():
            continue
        indent = body[: len(body) - len(body.lstrip(" \t"))]
        if " " in indent and "\t" in indent:
            issues.append(LintIssue("GFL-01", res_path, lineno, "tabs and spaces mixed in one indent"))
        elif indent:
            style = "tab" if "\t" in indent else "space"
            if file_style is None:
                file_style = style
            elif style != file_style:
                issues.append(LintIssue("GFL-01", res_path, lineno, f"{style} indent in {file_style}-indented file"))
        stripped = body.strip()
        if indent:
            continue
        if _ANNOTATION.match(stripped):
            continue
        if _EXTENDS.match(stripped) or _CLASS_NAME.match(stripped):
            if seen_code:
                issues.append(LintIssue("GFL-02", res_path, lineno, "extends/class_name must precede other declarations"))
            continue
        seen_code = True
    return issues


def class_name_of(text: str) -> str | None:
    for raw in text.splitlines():
        m = _CLASS_NAME.match(raw.strip())
        if m:
            return m.group(1)
    return None


def preload_targets(text: str) -> list[tuple[int, str]]:
    out = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        for m in _PRELOAD.finditer(_strip_comment(raw)):
            out.append((lineno, m.group(1)))
    return out


def lint_project(project: GodotProject) -> list[LintIssue]:
    issues: list[LintIssue] = []
    owners: dict[str, str] = {}
    for script in project.scripts():
        res = path_to_res(project.root, script)
        text = script.read_text(encoding="utf-8", errors="replace")
        issues.extend(lint_source(text, res))
        for lineno, target in preload_targets(text):
            if not project.exists(target):
                issues.append(LintIssue("GFL-03", res, lineno, f"preload target missing: {target}"))
        cname = class_name_of(text)
        if cname:
            if cname in owners:
                issues.append(LintIssue("GFL-04", res, 0, f"class_name {cname} already declared in {owners[cname]}"))
            else:
                owners[cname] = res
    return issues


def lint_file(path: Path) -> list[LintIssue]:
    return lint_source(path.read_text(encoding="utf-8", errors="replace"), str(path))
