"""Source-pinned multi-file exact-hunk proposal for canonical Jeeves inventory.

This extends the existing source.propose path without introducing a writable
repository editor or a second source authority. Operator-reviewed transformations
are generated only from exact original source bytes and optimistic hashes. This
never applies a patch, commits a file, executes scanned code or trains weights.
"""
from __future__ import annotations

from hashlib import sha256
from typing import Any

from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, MAX_PATCH, PRIVATE,
    _relative, digest,
)

SCHEMA = "skeleton.ai.jeeves_source_patchset.v1"
MAX_FILES = 8
MAX_EDITS_PER_FILE = 24
MAX_TOTAL_EDITS = 72
MAX_INPUT_BYTES = 380_000
MAX_TOTAL_DIFF_BYTES = 512_000
MAX_TOTAL_SOURCE_BYTES = 850_000
MAX_ITEM_BYTES = 120_000
MAX_REASON = 1_000
HASH_CHARS = frozenset("0123456789abcdef")


def _digest_match(value: Any) -> str:
    if (type(value) is not str or len(value) != 64 or
            any(char not in HASH_CHARS for char in value)):
        raise JeevesAppwideError("expected exact lowercase source SHA-256")
    return value


def _typed_map(raw: Any, *, name: str, expected: set[str]) -> dict:
    if type(raw) is not dict or set(raw) != expected:
        raise JeevesAppwideError(name + " has invalid or missing keys")
    return raw


def _str(raw: Any, *, name: str, maximum: int,
         minimum: int = 1) -> str:
    if (type(raw) is not str or
            not minimum <= len(raw.encode("utf-8")) <= maximum or
            "\x00" in raw):
        raise JeevesAppwideError("invalid bounded " + name)
    return raw


def _compile_edits(original: str, edits: list, *, path: str) -> tuple[str, list]:
    if type(edits) is not list or not 1 <= len(edits) <= MAX_EDITS_PER_FILE:
        raise JeevesAppwideError("1–24 exact source replacements required")
    # First validate against the *unchanged* source. Applying each edit to
    # intermediate output would let one replacement forge an anchor used by
    # a later edit. Original-offset based spans prevent that ambiguity.
    spans = []
    summaries = []
    for index, edit in enumerate(edits):
        row = _typed_map(edit, name="source hunk",
                         expected={"old", "new"})
        before = _str(row["old"], name="source anchor",
                      maximum=MAX_ITEM_BYTES)
        after = _str(row["new"], name="replacement text",
                     maximum=MAX_ITEM_BYTES, minimum=0)
        if before == after:
            raise JeevesAppwideError("no-op hunk rejected")
        count = original.count(before)
        if count != 1:
            raise JeevesAppwideError(
                "source hunk must uniquely match unchanged original: " + path
            )
        start = original.index(before)
        stop = start + len(before)
        spans.append((start, stop, after))
        summaries.append({
            "hunk": index,
            "old_sha256": sha256(before.encode()).hexdigest(),
            "new_sha256": sha256(after.encode()).hexdigest(),
            "start_offset": start,
            "end_offset": stop,
            "old_bytes": len(before.encode("utf-8")),
            "new_bytes": len(after.encode("utf-8")),
            "original_line": original.count("\n", 0, start) + 1,
            "old_text_occurrences": 1,
        })
    ordered = sorted(spans)
    for prev, nxt in zip(ordered, ordered[1:]):
        if nxt[0] < prev[1]:
            raise JeevesAppwideError(
                "overlapping exact hunk spans are ambiguous: " + path
            )
    output = original
    for start, stop, replacement in reversed(ordered):
        output = output[:start] + replacement + output[stop:]
    return output, summaries


def preview_source_patchset(
    inventory: AppwideInventory, *, patches: Any, reason: Any,
    expected_snapshot=None, operator_authorized=False
) -> dict:
    """Generate exact-byte, all-preflighted multi-file review proposals.

    A successful bundle is NOT a commit or an authorization to commit; every
    file requires a fresh source read at approval time. A source identity
    conflict aborts the whole batch before any proposals are returned.
    """
    if operator_authorized is not True:
        raise PermissionError("operator approval required for source proposals")
    if not isinstance(inventory, AppwideInventory):
        raise JeevesAppwideError("canonical scanned inventory required")
    inventory._require_scanned()
    if expected_snapshot is not None and expected_snapshot != inventory._digest:
        raise JeevesAppwideError("stale source inventory for patchset")
    reason = _str(reason, name="review justification", maximum=MAX_REASON,
                  minimum=12)
    if type(patches) is not list or not 1 <= len(patches) <= MAX_FILES:
        raise JeevesAppwideError("patchset requires 1–8 original source files")
    indexed = []
    all_paths = set()
    total_original = 0
    total_input = len(reason.encode("utf-8"))
    total_edits = 0
    # Phase 1: bounded, exact, non-mutating preflight of *every* original.
    for raw in patches:
        item = _typed_map(raw, name="patch target",
                          expected={"path", "expected_sha256", "edits"})
        path = _relative(item["path"])
        if PRIVATE.search(path):
            raise JeevesAppwideError("private source patching is forbidden")
        if path in all_paths:
            raise JeevesAppwideError("duplicate patchset path")
        all_paths.add(path)
        expected = _digest_match(item["expected_sha256"])
        entry = inventory._files.get(path)
        if entry is None or not entry.readable or entry.kind not in ("source", "text"):
            raise JeevesAppwideError("unavailable patchset source")
        if entry.bytes > MAX_PATCH:
            raise JeevesAppwideError("source exceeds reviewed patch size")
        original = inventory._safe_file(path, max_size=MAX_PATCH)
        original_digest = sha256(original.encode("utf-8")).hexdigest()
        if original_digest != expected:
            raise JeevesAppwideError("stale patchset source: " + path)
        replacement, hunks = _compile_edits(original, item["edits"], path=path)
        total_edits += len(hunks)
        total_original += len(original.encode("utf-8"))
        total_input += sum(
            len(_str(h["old"], name="hunk old", maximum=MAX_ITEM_BYTES).encode())
            + len(_str(h["new"], name="hunk new", maximum=MAX_ITEM_BYTES,
                       minimum=0).encode()) for h in item["edits"]
        )
        if total_edits > MAX_TOTAL_EDITS:
            raise JeevesAppwideError("patchset exceeds total exact-hunk budget")
        if total_original > MAX_TOTAL_SOURCE_BYTES or total_input > MAX_INPUT_BYTES:
            raise JeevesAppwideError("patchset exceeds source/input byte budget")
        if len(replacement.encode("utf-8")) > MAX_PATCH:
            raise JeevesAppwideError("patchset result exceeds single-file capacity")
        indexed.append((path, expected, replacement, hunks))
    # Phase 2: canonical individual proposal engine. Still read-only.
    reviewed = []
    diff_bytes = 0
    for path, expected, replacement, hunks in sorted(indexed):
        proposal = inventory.propose_source_revision(
            path=path, expected_sha256=expected, replacement=replacement,
            reason=reason, operator_authorized=True)
        diff_bytes += len(proposal["diff"].encode("utf-8"))
        if diff_bytes > MAX_TOTAL_DIFF_BYTES:
            raise JeevesAppwideError("bounded patchset diff exceeded")
        reviewed.append({
            "path": path,
            "previous_sha256": expected,
            "proposed_sha256": proposal["proposed_sha256"],
            "hunks": hunks,
            "unified_diff": proposal["diff"],
            "canonical_single_file_receipt": proposal["digest"],
            "source_committed": False,
        })
    evidence = {
        "schema": SCHEMA,
        "inventory_snapshot": inventory._digest,
        "reason": reason,
        "file_count": len(reviewed),
        "hunk_count": total_edits,
        "original_source_bytes": total_original,
        "proposal_input_bytes": total_input,
        "combined_diff_bytes": diff_bytes,
        "patches": reviewed,
        "every_edit_matched_unique_unchanged_source": True,
        "all_paths_preflighted_before_review": True,
        "whole_patchset_requires_fresh_source_identities_before_commit": True,
        "source_files_written": 0,
        "commits_created": 0,
        "tests_run": 0,
        "review_and_independent_authorization_required": True,
    }
    return {**evidence, "digest": digest(evidence)}
