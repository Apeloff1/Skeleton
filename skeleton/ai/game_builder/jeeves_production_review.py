"""Source-preview and explicit human approval for existing Studio proposals.

This is an ergonomic coordinator over GameWorkspace.commit, not an alternative
filesystem writer. It preflights every proposal's content/address identity
before any commit, returns unified diffs and tracks partial-failure receipts.
Individual canonical optimistic source controls remain in effect.
"""
from __future__ import annotations

import difflib
from hashlib import sha256
import re
from typing import Any

from .contracts import canonical_digest
from .game_project_workspace import (
    GameWorkspace, WorkspaceError, _json, _read,
)
from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, digest,
)

SCHEMA = "skeleton.ai.jeeves_production_review.v1"
MAX_REVIEW = 24
MAX_SOURCE = 256_000
MAX_TOTAL_INPUT = 2_000_000
MAX_TOTAL_DIFF = 350_000
MAX_DIFF_PER_FILE = 55_000
SHA = re.compile(r"[0-9a-f]{64}\Z")
EMPTY_SHA = sha256(b"").hexdigest()


def _validated_ids(proposal_ids: Any) -> list[str]:
    if (type(proposal_ids) is not list or
            not 1 <= len(proposal_ids) <= MAX_REVIEW or
            any(type(ident) is not str or not SHA.fullmatch(ident)
                for ident in proposal_ids)):
        raise JeevesAppwideError("1–24 exact proposal SHA-256 IDs required")
    if len(set(proposal_ids)) != len(proposal_ids):
        raise JeevesAppwideError("duplicate source proposal ID")
    return sorted(proposal_ids)


class JeevesProductionReview:
    """Canonical existing reviewed game edits, with no silent publication."""

    def __init__(self, inventory: AppwideInventory, workspace: GameWorkspace):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("review source inventory required")
        inventory._require_scanned()
        if not isinstance(workspace, GameWorkspace):
            raise JeevesAppwideError("selected GameWorkspace required")
        self.inv = inventory
        self.ws = workspace

    def _records(self, *, project, proposal_ids, expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot != self.inv._digest:
            raise JeevesAppwideError("stale repository inventory")
        if type(project) is not str or self.ws.active() != project:
            raise JeevesAppwideError("selected current project required")
        identities = _validated_ids(proposal_ids)
        ws = self.ws
        rows = []
        paths = set()
        bytes_total = 0
        for ident in identities:
            path = ws.root / "reviews" / "proposals" / (ident + ".json")
            proposal = _json(_read(path, 300_000))
            if type(proposal) is not dict or canonical_digest(proposal) != ident:
                raise JeevesAppwideError("source proposal custody has changed")
            if proposal.get("schema") != "skeleton.game_builder.targeted_edit.v1":
                raise JeevesAppwideError("unrecognized game source proposal")
            if proposal.get("project") != project:
                raise JeevesAppwideError("proposal belongs to another original game")
            relative = proposal.get("path")
            target = ws._file("current", project, relative)
            if relative in paths:
                raise JeevesAppwideError("multiple proposals modify the same source")
            paths.add(relative)
            if (type(proposal.get("new_content")) is not str or
                    len(proposal["new_content"].encode("utf-8")) > MAX_SOURCE):
                raise JeevesAppwideError("unbounded source review content")
            bytes_total += len(proposal["new_content"].encode("utf-8"))
            if bytes_total > MAX_TOTAL_INPUT:
                raise JeevesAppwideError("review bundle source budget exceeded")
            expected = proposal.get("expected_sha256")
            outcome = proposal.get("new_sha256")
            if (type(expected) is not str or not SHA.fullmatch(expected) or
                    type(outcome) is not str or not SHA.fullmatch(outcome)):
                raise JeevesAppwideError("source identity digest malformed")
            if sha256(proposal["new_content"].encode()).hexdigest() != outcome:
                raise JeevesAppwideError("proposal text changed after authoring")
            if (ws.root / "reviews" / "accepted" / (ident + ".json")).exists():
                raise JeevesAppwideError("review proposal already human committed")
            old = _read(target) if target.exists() else ""
            observed = sha256(old.encode("utf-8")).hexdigest()
            if observed != expected:
                raise JeevesAppwideError("current project source differs from proposal base")
            rows.append({
                "proposal_id": ident,
                "path": relative,
                "old_text": old,
                "new_text": proposal["new_content"],
                "previous_sha256": expected,
                "proposed_sha256": outcome,
                "new_source_bytes": len(proposal["new_content"].encode("utf-8")),
                "is_new_source": not target.exists(),
                "review_reason": str(proposal.get("reason", ""))[:1000],
                "canonical_commit_will_be_required": True,
            })
        return sorted(rows, key=lambda x: x["path"])

    def review(self, *, project, proposal_ids, expected_snapshot=None):
        records = self._records(
            project=project, proposal_ids=proposal_ids,
            expected_snapshot=expected_snapshot)
        total_diff = 0
        reviews = []
        for entry in records:
            diff = "".join(difflib.unified_diff(
                entry["old_text"].splitlines(keepends=True),
                entry["new_text"].splitlines(keepends=True),
                fromfile="before/" + entry["path"],
                tofile="proposed/" + entry["path"],
            ))
            b = diff.encode("utf-8")
            remaining = max(0, MAX_TOTAL_DIFF - total_diff)
            take = min(len(b), MAX_DIFF_PER_FILE, remaining)
            clipped = b[:take].decode("utf-8", errors="ignore")
            total_diff += len(clipped.encode("utf-8"))
            reviews.append({
                "proposal_id": entry["proposal_id"],
                "path": entry["path"],
                "previous_sha256": entry["previous_sha256"],
                "proposed_sha256": entry["proposed_sha256"],
                "new_source_bytes": entry["new_source_bytes"],
                "is_new_source": entry["is_new_source"],
                "review_reason": entry["review_reason"],
                "unified_diff": clipped,
                "diff_bytes_full": len(b),
                "diff_truncated": len(b) > take,
                "review_requires_human_approval": True,
            })
        body = {
            "schema": SCHEMA + ".review",
            "project": project,
            "inventory_snapshot": self.inv._digest,
            "workspace_revision": self.ws.tree()["revision"],
            "proposal_count": len(reviews),
            "source_bytes_inspected": sum(r["new_source_bytes"] for r in reviews),
            "diff_bytes_returned": total_diff,
            "proposals": reviews,
            "some_diffs_truncated": any(r["diff_truncated"] for r in reviews),
            "source_files_committed": 0,
            "complete_review_text_must_be_rendered_before_acceptance": True,
            "independent_human_acceptance_required": True,
            "reviewed_bundle_is_not_atomic_commit": True,
        }
        return {**body, "digest": digest(body)}

    def commit(self, *, project, proposal_ids, expected_review_digest,
               approvals, expected_snapshot=None, operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("explicit designer write authority required")
        if type(expected_review_digest) is not str or not SHA.fullmatch(expected_review_digest):
            raise JeevesAppwideError("exact fresh source review receipt required")
        identities = _validated_ids(proposal_ids)
        if type(approvals) is not list or len(approvals) != len(identities):
            raise JeevesAppwideError("explicit one-to-one source approvals required")
        approvals_by_id = {}
        for raw in approvals:
            if type(raw) is not dict or set(raw) != {
                "proposal_id", "reviewed_sha256", "human_approved"
            }:
                raise JeevesAppwideError("exact typed individual approval required")
            key = raw["proposal_id"]
            if (type(key) is not str or not SHA.fullmatch(key) or
                    key in approvals_by_id or raw["human_approved"] is not True):
                raise JeevesAppwideError("unapproved or duplicate source commit")
            approvals_by_id[key] = raw["reviewed_sha256"]
        if set(approvals_by_id) != set(identities):
            raise JeevesAppwideError("proposal approvals do not cover every source")
        report = self.review(
            project=project, proposal_ids=identities,
            expected_snapshot=expected_snapshot)
        if report["digest"] != expected_review_digest:
            raise JeevesAppwideError("review receipt stale after source or proposal drift")
        if report["some_diffs_truncated"]:
            raise JeevesAppwideError(
                "full diff review required; split bundle or use individual Studio commit")
        for record in report["proposals"]:
            if approvals_by_id[record["proposal_id"]] != record["proposed_sha256"]:
                raise JeevesAppwideError("individual human-reviewed content hash mismatch")
        # All reviewed sources are now preflighted. The existing canonical
        # commit route remains the ONLY source writer, executed sequentially.
        # If a later disk failure occurs, record the committed prefix rather
        # than representing partially written output as an atomic success.
        committed = []
        for record in report["proposals"]:
            try:
                action = self.ws.commit(
                    record["proposal_id"],
                    human_approved=True, authorized=True)
            except (WorkspaceError, OSError, ValueError) as exc:
                # The canonical writer stores the source, then acceptance,
                # then revision. A disk error between those operations can
                # leave the failing file ALREADY CHANGED, even though
                # commit() raised. Report the observed source/receipt state
                # instead of calling it safely "uncommitted".
                failed_path = record["path"]
                accepted_path = (
                    self.ws.root / "reviews" / "accepted" /
                    (record["proposal_id"] + ".json")
                )
                observed_source_sha = None
                try:
                    current = self.ws.read("current", project, failed_path)
                    observed_source_sha = current["version"]["sha256"]
                except (WorkspaceError, OSError, ValueError):
                    pass
                write_state = (
                    "source_matches_proposal_but_commit_report_failed"
                    if observed_source_sha == record["proposed_sha256"]
                    else "old_source_unchanged"
                    if observed_source_sha == record["previous_sha256"]
                    else "unknown_source_state"
                )
                failure = {
                    "schema": SCHEMA + ".partial",
                    "failed_proposal": record["proposal_id"],
                    "failed_source": failed_path,
                    "failed_source_sha256_observed": observed_source_sha,
                    "failed_source_write_state": write_state,
                    "accepted_receipt_present": accepted_path.is_file(),
                    "manual_reconciliation_needed_before_any_retry": True,
                    "review_digest": report["digest"],
                    "committed_count": len(committed),
                    "committed": committed,
                    "uncommitted": [
                        item["proposal_id"] for item in report["proposals"]
                        if item["proposal_id"] not in
                        {done["proposal_id"] for done in committed}
                    ],
                    "partial_failure": True,
                    "error_class": type(exc).__name__,
                    "resume_requires_fresh_review": True,
                    "automatic_retry_performed": False,
                }
                return {**failure, "digest": digest(failure)}
            committed.append({
                "proposal_id": record["proposal_id"],
                "path": action["path"],
                "sha256": action["sha256"],
                "human_approved": True,
            })
        body = {
            "schema": SCHEMA + ".committed",
            "project": project,
            "source_count": len(committed),
            "source_versions": committed,
            "review_digest": report["digest"],
            "individually_reviewed_and_approved": True,
            "canonical_workspace_commit_used": True,
            "release_and_hardware_acceptance_not_inferred": True,
            "model_weights_changed": False,
        }
        return {**body, "digest": digest(body)}
