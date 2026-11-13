#!/usr/bin/env python3
"""Fail-closed, exact-head Dragon qualification admission for the 20-workflow cap.

A single already-required Backend Quality workflow owns dispatch. These flags
only decide *which* read-only, reusable Dragon CI jobs need to run. If file
discovery fails, all Dragon jobs are admitted; never use a failed or incomplete
diff as evidence that a security/qualification job can be skipped.

No PR-authored shell command, path, title or branch name is executed. Git
receives only the two strict 40-hex commit identities from the event context.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable

FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_DIFF_BYTES = 16 * 1024 * 1024
DRAGON_FILES = frozenset({
    "backend/core/dragon_crawler.py",
    "backend/routes/dragon_academy.py",
    "backend/tests/test_dragon_atlas_bridge.py",
    "backend/requirements.txt",
    "frontend/src/product/crawlerClient.ts",
    "frontend/src/features/Jeeves/CrawlerResearchAtlasPanel.tsx",
    "frontend/src/features/Jeeves/CrawlerWorkspace.tsx",
    "frontend/src/features/Jeeves/atlasCampaignPlan.ts",
    "frontend/scripts/test-dragon-atlas-contract.cjs",
    "scripts/check_dragon_workflow_scope.py",
    "tests/test_dragon_workflow_scope.py",
    ".github/workflows/backend-quality.yml",
})
FRONTEND_FILES = frozenset({
    "frontend/src/product/crawlerClient.ts",
    "frontend/src/features/Jeeves/CrawlerResearchAtlasPanel.tsx",
    "frontend/src/features/Jeeves/CrawlerWorkspace.tsx",
    "frontend/src/features/Jeeves/atlasCampaignPlan.ts",
    "frontend/scripts/test-dragon-atlas-contract.cjs",
})
BACKEND_FILES = frozenset({
    "backend/core/dragon_crawler.py",
    "backend/routes/dragon_academy.py",
    "backend/tests/test_dragon_atlas_bridge.py",
    "backend/requirements.txt",
})
TRIGGER_ALL = frozenset({
    "scripts/check_dragon_workflow_scope.py",
    "tests/test_dragon_workflow_scope.py",
    ".github/workflows/backend-quality.yml",
})


def classify(paths: Iterable[str]) -> dict[str, bool]:
    """Over-admit relative to old path filters; never deny relevant work."""
    found = {"backend": False, "source": False, "frontend": False}
    for p in paths:
        if not isinstance(p, str) or not p or p.startswith("/") or "\x00" in p:
            # Invalid/untrusted diff report has no safe skip classification.
            return dict.fromkeys(found, True)
        if p in TRIGGER_ALL or p.startswith(".github/workflows/dragon-"):
            return dict.fromkeys(found, True)
        if p in BACKEND_FILES:
            found["backend"] = True
        if p in FRONTEND_FILES or p.startswith("frontend/src/features/Jeeves/CrawlerResearch"):
            found["frontend"] = True
        if (
            p.startswith("skeleton/ai/webcrawler/")
            or p.startswith("tests/test_ai_webcrawler_dragon_")
            or p in BACKEND_FILES
        ):
            found["source"] = True
        if p.startswith("skeleton/ai/webcrawler/") or (
            p in {"tests/test_ai_webcrawler_dragon_atlas.py",
                  "tests/test_ai_webcrawler_dragon_mime_custody.py"}
        ):
            found["backend"] = True
    return found


def _run(*argv: str) -> bytes:
    result = subprocess.run(
        list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=True, timeout=90,
    )
    if len(result.stdout) > MAX_DIFF_BYTES:
        raise OverflowError("changed-path inventory exceeds bound")
    return result.stdout


def exact_head_paths(*, base: str, head: str) -> tuple[str, ...]:
    """Inspect full changed-file names, including deleted/renamed paths.

    Caller fetches the base SHA without persisting write credentials. Neither
    untrusted PR code nor a shell parser is involved in diff arguments.
    """
    if not FULL_SHA.fullmatch(base) or not FULL_SHA.fullmatch(head):
        raise ValueError("base and head must be exact 40-hex SHA identities")
    observed = _run("git", "rev-parse", "HEAD").decode("ascii", "strict").strip()
    if observed != head:
        raise ValueError("checkout does not match exact PR head")
    _run("git", "cat-file", "-e", f"{base}^{{commit}}")
    _run("git", "cat-file", "-e", f"{head}^{{commit}}")
    raw = _run(
        "git", "diff", "--name-only", "--no-renames", "--no-ext-diff",
        "-z", base, head, "--",
    )
    if raw and not raw.endswith(b"\x00"):
        raise ValueError("incomplete NUL-delimited git changed-path inventory")
    return tuple(os.fsdecode(p) for p in raw.split(b"\x00") if p)


def decide(*, base: str, head: str) -> tuple[dict[str, bool], str]:
    try:
        paths = exact_head_paths(base=base, head=head)
        flags = classify(paths)
        return flags, f"exact Git diff: {len(paths)} changed paths"
    except (OSError, ValueError, OverflowError, subprocess.SubprocessError) as exc:
        # Missing base, truncated results, Git failure and checkout drift
        # must not silently suppress protected source qualification.
        return {"backend": True, "source": True, "frontend": True}, (
            f"fail-closed all Dragon suites: {type(exc).__name__}"
        )


def main() -> int:
    if os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        print("Dragon scope only accepts a pull_request event", file=sys.stderr)
        return 2
    base = os.environ.get("DRAGON_BASE_SHA", "")
    head = os.environ.get("DRAGON_HEAD_SHA", "")
    # Malformed caller identities are an explicit failure, not a false scope.
    if not FULL_SHA.fullmatch(base) or not FULL_SHA.fullmatch(head):
        print("invalid exact-head event identities", file=sys.stderr)
        return 2
    flags, reason = decide(base=base, head=head)
    print(f"Dragon exact-head scope: {reason}; " +
          ", ".join(f"{key}={str(value).lower()}" for key, value in flags.items()))
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        print("missing GitHub output receipt", file=sys.stderr)
        return 2
    with Path(output).open("a", encoding="utf-8") as receipt:
        for name in ("backend", "source", "frontend"):
            receipt.write(f"{name}={'true' if flags[name] else 'false'}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
