"""Paged on-disk current-project proposal custody over canonical Studio records.

This is an operator view of the existing proposals/accepted stores, not a
parallel backlog, approval oracle or source writer. Untrusted malformed,
symlinked, oversized and stale files are refused or explicitly counted.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from hashlib import sha256
import re

from .contracts import canonical_digest
from .game_project_workspace import (
    GameWorkspace, WorkspaceError, _json, _read,
)
from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, digest,
)

SCHEMA = "skeleton.ai.jeeves_proposal_queue.v1"
SHA = re.compile(r"[a-f0-9]{64}\Z")
MAX_FILES_PER_PAGE = 80
MAX_STORE_FILES = 50_000
MAX_SCAN_BYTES = 9_000_000


class JeevesProposalQueue:
    """Browse precise human-edit proposal and accepted receipts, read-only."""

    def __init__(self, inventory: AppwideInventory, workspace: GameWorkspace):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("source custody inventory required")
        inventory._require_scanned()
        if not isinstance(workspace, GameWorkspace):
            raise JeevesAppwideError("original GameWorkspace required")
        self.inv = inventory
        self.ws = workspace

    def page(self, *, project, start_after=None, limit=30,
             expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot != self.inv._digest:
            raise JeevesAppwideError("stale repository source inventory")
        if type(project) is not str or project != self.ws.active():
            raise JeevesAppwideError("active current game required for proposal queue")
        if type(limit) is not int or not 1 <= limit <= MAX_FILES_PER_PAGE:
            raise JeevesAppwideError("bounded source queue page required")
        if start_after is not None and (
            type(start_after) is not str or not SHA.fullmatch(start_after)
        ):
            raise JeevesAppwideError("exact source proposal cursor required")
        root = self.ws.root / "reviews" / "proposals"
        if root.is_symlink() or not root.is_dir():
            raise JeevesAppwideError("canonical proposal custody unavailable")
        # The directory filename list is bounded without reading file data.
        names = sorted(
            p.stem for p in root.iterdir()
            if p.suffix == ".json" and SHA.fullmatch(p.stem)
        )
        if len(names) > MAX_STORE_FILES:
            raise JeevesAppwideError("source proposal queue exceeds count budget")
        index = bisect_right(names, start_after) if start_after else 0
        end = min(len(names), index + limit)
        window = names[index:end]
        accepted_dir = self.ws.root / "reviews" / "accepted"
        if accepted_dir.is_symlink() or not accepted_dir.is_dir():
            raise JeevesAppwideError("canonical accepted source custody unavailable")
        stored = {entry.path: entry for entry in self.ws.files("current", project)}
        records = []
        skipped = Counter()
        scanned_bytes = 0
        for ident in window:
            path = root / (ident + ".json")
            if path.is_symlink() or not path.is_file():
                skipped["unsafe_source_proposal"] += 1
                continue
            size = path.stat().st_size
            if size > 300_000 or scanned_bytes + size > MAX_SCAN_BYTES:
                skipped["oversized_or_byte_budgeted"] += 1
                continue
            scanned_bytes += size
            try:
                proposal = _json(_read(path, 300_000))
            except (WorkspaceError, OSError, ValueError):
                skipped["unreadable_or_malformed"] += 1
                continue
            if (type(proposal) is not dict or
                    canonical_digest(proposal) != ident or
                    proposal.get("schema") !=
                    "skeleton.game_builder.targeted_edit.v1"):
                skipped["invalid_source_receipt"] += 1
                continue
            if proposal.get("project") != project:
                skipped["different_project"] += 1
                continue
            original = proposal.get("path")
            try:
                self.ws._file("current", project, original)
            except (WorkspaceError, ValueError, TypeError):
                skipped["unsafe_original_source_path"] += 1
                continue
            proposed = proposal.get("new_sha256")
            previous = proposal.get("expected_sha256")
            if (type(proposed) is not str or not SHA.fullmatch(proposed) or
                    type(previous) is not str or not SHA.fullmatch(previous)):
                skipped["invalid_source_hash"] += 1
                continue
            accepted = accepted_dir / (ident + ".json")
            if accepted.is_symlink():
                skipped["unsafe_accepted_receipt"] += 1
                continue
            source = stored.get(original)
            current_sha = source.sha256 if source is not None else sha256(b"").hexdigest()
            status = (
                "human_committed" if accepted.is_file() else
                "awaiting_review" if current_sha == previous else
                "stale_source_conflict"
            )
            records.append({
                "proposal_id": ident,
                "path": original,
                "previous_sha256": previous,
                "proposed_sha256": proposed,
                "current_source_sha256": current_sha,
                "status": status,
                "reason": str(proposal.get("reason", ""))[:200],
                "accepted_receipt_present": accepted.is_file(),
                "approval_is_not_implied_by_presence": True,
            })
        result = {
            "schema": SCHEMA + ".page",
            "project": project,
            "inventory_snapshot": self.inv._digest,
            "workspace_revision": self.ws.tree()["revision"],
            "total_custody_filenames_all_projects": len(names),
            "start_after": start_after,
            "next_after": window[-1] if end < len(names) and window else None,
            "examined_filenames": len(window),
            "returned_current_project_rows": len(records),
            "source_proposal_bytes_examined": scanned_bytes,
            "skipped_reason_counts": dict(sorted(skipped.items())),
            "entries": records,
            "more_pages_possible": end < len(names),
            "the_queue_is_persisted_workspace_data_not_a_new_owner": True,
            "existing_source_files_written": 0,
        }
        return {**result, "digest": digest(result)}
