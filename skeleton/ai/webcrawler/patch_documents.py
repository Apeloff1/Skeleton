"""Finite inert unified-diff source extraction; no patch application or IO.

External file names are labels only, never paths opened on disk. Binary diffs
and suspicious credential-bearing hunks are suppressed. This is not a static
security audit or a validation of the content's provenance.
"""
from __future__ import annotations

import re

from .research_projection import (
    ResearchFormatError, ResearchProjection, check_text, project_lines,
)

PATCH_MEDIA_TYPES = frozenset({
    "text/x-diff", "text/x-patch", "application/x-diff", "text/patch",
})
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@(?: .{0,256})?$")
_SENSITIVE = re.compile(
    r"(?i)(?:api[_-]?key|password|passwd|private[_-]?key|client[_-]?secret"
    r"|refresh[_-]?token|authorization|cookie|bearer\s+|BEGIN [A-Z ]*PRIVATE KEY)",
)
_SECRET_PATH = re.compile(
    r"(?i)(?:^|/)(?:\.env(?:\.|$)|id_rsa|id_ed25519|credentials?|secrets?)(?:\..*)?$"
)


def extract_unified_patch(
    raw: str, *, max_chars: int = 524288, max_links: int = 0,
) -> ResearchProjection:
    check_text(raw, max_chars=max_chars, max_links=max_links)
    if len(raw.splitlines()) > 16384:
        raise ResearchFormatError("unbounded patch line count")
    files = hunks = 0
    lines = []
    allowed_file = True
    changed_lines = 0
    for row in raw.splitlines():
        if len(row) > 8192:
            raise ResearchFormatError("unbounded patch line")
        if row.startswith(("GIT binary patch", "Binary files ", "literal ", "delta ")):
            raise ResearchFormatError("binary patches require separate inspection")
        if row.startswith("diff --git "):
            files += 1
            if files > 128:
                raise ResearchFormatError("patch file count exceeded")
            fields = row.split()
            if len(fields) != 4 or not fields[2].startswith("a/") or not fields[3].startswith("b/"):
                raise ResearchFormatError("unexpected patch file identity")
            label = fields[3][2:]
            if len(label) > 1024 or "\\" in label or ".." in label.split("/"):
                raise ResearchFormatError("unsafe patch file identity")
            allowed_file = not _SECRET_PATH.search(label)
            lines.append(f"Changed source {files}: "
                         + ("[sensitive path withheld]" if not allowed_file else label))
        elif row.startswith("@@"):
            if not _HUNK.fullmatch(row):
                raise ResearchFormatError("invalid unified patch hunk")
            hunks += 1
            if hunks > 2048:
                raise ResearchFormatError("patch hunk capacity exceeded")
            if allowed_file:
                lines.append(f"Diff hunk {hunks}: {row[:256]}")
        elif row.startswith(("+", "-")) and not row.startswith(("+++", "---")):
            changed_lines += 1
            if changed_lines > 8192:
                raise ResearchFormatError("patch changed-line capacity exceeded")
            if not allowed_file:
                continue
            if _SENSITIVE.search(row):
                lines.append("[credential-related patch line withheld]")
            else:
                lines.append("Change: " + row[:4096])
        elif row.startswith(("--- ", "+++ ", "index ", "new file mode ",
                             "deleted file mode ", "similarity index ",
                             "rename from ", "rename to ", " ")):
            continue
        elif row and not row.startswith(("From ", "Date:", "Subject:")):
            # Tolerate usual mail-format patch headers but never execute them.
            continue
    if not files or not hunks:
        raise ResearchFormatError("not a bounded unified patch")
    return project_lines(lines, title="Source patch evidence", max_chars=max_chars)
