#!/usr/bin/env python3
"""
Bulk-migrate every `fetch(` call in /app/frontend/features/** to `apiFetch(`,
and ensure `apiFetch` is imported from utils/apiController.

This v2:
  • Handles multi-line `import { ... } from '...'` statements correctly.
  • Removes any prior (badly-positioned) apiFetch import line and re-inserts
    it after the import block, so re-running heals previous mistakes.
  • Idempotent: re-running on already-migrated files makes no changes.
"""
from __future__ import annotations
import os
import re
import sys

FEATURES_ROOT = "/app/frontend/features"
APP_ROOT = "/app/frontend/app"
CONTROLLER_ABS = "/app/frontend/utils/apiController"

FETCH_CALL_RE = re.compile(r"(?<![A-Za-z0-9_.])fetch\s*\(")
APIFETCH_IMPORT_LINE_RE = re.compile(
    r"""^\s*import\s*\{\s*apiFetch\s*\}\s*from\s*['"][^'"]*apiController['"]\s*;?\s*$"""
)


def rel_import_path(file_path: str) -> str:
    src_dir = os.path.dirname(file_path)
    rel = os.path.relpath(CONTROLLER_ABS, src_dir).replace(os.sep, "/")
    if not rel.startswith(".") and not rel.startswith("/"):
        rel = "./" + rel
    return rel


def _strip_strings_and_comments(line: str) -> str:
    """Remove string contents & line comments so brace counting is reliable."""
    out = []
    i = 0
    in_str = None  # quote char
    while i < len(line):
        c = line[i]
        if in_str:
            if c == "\\" and i + 1 < len(line):
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in ('"', "'", "`"):
            in_str = c
            i += 1
            continue
        if c == "/" and i + 1 < len(line) and line[i + 1] == "/":
            break  # rest is line comment
        out.append(c)
        i += 1
    return "".join(out)


def find_imports_end(lines: list[str]) -> int:
    """
    Walk top-of-file blocks (comments, blank lines, import statements) and
    return the line index *after* the last top-level import statement.

    Properly handles multi-line `import { ... } from '...';`.
    """
    i = 0
    n = len(lines)
    in_block_comment = False
    last_after = 0

    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            i += 1
            last_after = i
            continue

        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
            i += 1
            last_after = i
            continue

        if stripped.startswith("//") or stripped == "":
            i += 1
            last_after = i
            continue

        if stripped.startswith("import "):
            # Consume possibly-multi-line import: balance braces until we hit
            # a terminating `;` outside braces (or just a line ending after `from '...';`).
            brace = 0
            saw_terminator = False
            while i < n and not saw_terminator:
                clean = _strip_strings_and_comments(lines[i])
                brace += clean.count("{") - clean.count("}")
                if brace <= 0 and (";" in clean or ("from " in clean and re.search(r"from\s*['\"][^'\"]+['\"]\s*;?", clean))):
                    # If brace is balanced and we have a terminator on this line.
                    if ";" in clean or re.search(r"from\s*['\"][^'\"]+['\"]\s*$", clean):
                        i += 1
                        saw_terminator = True
                        break
                i += 1
            last_after = i
            continue

        # First real code line — stop.
        break

    return last_after


def strip_existing_apifetch_imports(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not APIFETCH_IMPORT_LINE_RE.match(ln)]


def migrate_file(path: str) -> tuple[bool, int]:
    with open(path, "r", encoding="utf-8") as f:
        original = f.read()

    matches = list(FETCH_CALL_RE.finditer(original))
    has_apifetch_already_well = False

    # 1) Replace fetch( → apiFetch(
    new_content = FETCH_CALL_RE.sub("apiFetch(", original) if matches else original

    needs_import = "apiFetch(" in new_content

    # 2) Repair / re-place the import.
    lines = new_content.split("\n")
    # Detect if there's already a well-placed apiFetch import (alone on a line
    # at top of file). We'll strip all of them first and re-add in the right place.
    lines = strip_existing_apifetch_imports(lines)

    if needs_import:
        end_idx = find_imports_end(lines)
        rel = rel_import_path(path)
        import_line = f"import {{ apiFetch }} from '{rel}';"
        # Insert with a leading blank line guard only if previous line is non-blank.
        lines.insert(end_idx, import_line)

    new_content2 = "\n".join(lines)

    if new_content2 != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content2)
        return True, len(matches)
    return False, 0


def walk_targets(root: str):
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith((".tsx", ".ts")) and not name.endswith(".d.ts"):
                yield os.path.join(dirpath, name)


def main(argv):
    roots = argv[1:] or [FEATURES_ROOT]
    total_files = 0
    total_changed = 0
    total_replacements = 0
    for root in roots:
        for fp in walk_targets(root):
            if fp.endswith("/apiController.ts") or fp.endswith("/fetchInterceptor.ts"):
                continue
            total_files += 1
            changed, n = migrate_file(fp)
            if changed:
                total_changed += 1
                total_replacements += n
                print(f"  ✓ {fp}  ({n} replacements)")
    print(
        f"\nDone. Scanned {total_files} files, "
        f"changed {total_changed}, "
        f"replaced {total_replacements} fetch( occurrences."
    )


if __name__ == "__main__":
    main(sys.argv)
