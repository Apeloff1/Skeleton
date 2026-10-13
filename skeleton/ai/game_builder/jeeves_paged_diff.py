"""Paged, complete, SHA-pinned human diff review of large original game sources.

The existing bundle review intentionally rejects truncated diffs. This
provides a full-source alternative without weakening that gate: every
UTF-8 chunk of a single exact canonical proposal must be acknowledged by
SHA-256 before GameWorkspace.commit can be called. No automatic bulk
approval, blind editing, or replacement of the canonical source writer.
"""
from __future__ import annotations

import difflib
from hashlib import sha256
import re

from .jeeves_appwide_fabric import AppwideInventory,JeevesAppwideError,digest
from .jeeves_production_review import JeevesProductionReview
from .game_project_workspace import GameWorkspace,WorkspaceError

SCHEMA="skeleton.ai.jeeves_paged_diff.v1"
SHA=re.compile(r"[a-f0-9]{64}\Z")
PAGE_CHARS=24000
MAX_DIFF_BYTES=800000
MAX_PAGES=40


def _chunks(diff):
    encoded=diff.encode("utf-8")
    if len(encoded)>MAX_DIFF_BYTES:
        raise JeevesAppwideError("diff exceeds reviewed bounded single source size")
    result=[]
    if not diff:
        raise JeevesAppwideError("unchanged source has no diff to review")
    for at in range(0,len(diff),PAGE_CHARS):
        text=diff[at:at+PAGE_CHARS]
        data=text.encode("utf-8")
        result.append({
            "index":len(result),
            "char_offset":at,
            "char_length":len(text),
            "utf8_bytes":len(data),
            "sha256":sha256(data).hexdigest(),
            "text":text,
        })
    if len(result)>MAX_PAGES:
        raise JeevesAppwideError("diff exceeds bounded independent review pages")
    return result


class JeevesPagedDiff:
    """One original source file, immutable exact diff, one approval per page."""

    def __init__(self,inventory:AppwideInventory,workspace:GameWorkspace):
        if not isinstance(inventory,AppwideInventory):
            raise JeevesAppwideError("original scanned app inventory required")
        inventory._require_scanned()
        if not isinstance(workspace,GameWorkspace):
            raise JeevesAppwideError("human-reviewed GameWorkspace required")
        self.inv=inventory;self.ws=workspace

    def _prepare(self,*,project,proposal_id,expected_snapshot=None):
        if expected_snapshot is not None and expected_snapshot!=self.inv._digest:
            raise JeevesAppwideError("stale original game source inventory")
        if type(proposal_id) is not str or not SHA.fullmatch(proposal_id):
            raise JeevesAppwideError("exact one original source proposal ID required")
        records=JeevesProductionReview(self.inv,self.ws)._records(
            project=project,proposal_ids=[proposal_id],
            expected_snapshot=expected_snapshot)
        entry=records[0]
        diff="".join(difflib.unified_diff(
            entry["old_text"].splitlines(keepends=True),
            entry["new_text"].splitlines(keepends=True),
            fromfile="before/"+entry["path"],
            tofile="reviewed/"+entry["path"],
        ))
        pages=_chunks(diff)
        manifest={
            "schema":SCHEMA+".manifest",
            "project":project,
            "proposal_id":proposal_id,
            "inventory_snapshot":self.inv._digest,
            "workspace_revision":self.ws.tree()["revision"],
            "source_path":entry["path"],
            "prior_source_sha256":entry["previous_sha256"],
            "new_source_sha256":entry["proposed_sha256"],
            "new_source_bytes":entry["new_source_bytes"],
            "full_unified_diff_utf8_bytes":len(diff.encode("utf-8")),
            "full_unified_diff_sha256":sha256(diff.encode("utf-8")).hexdigest(),
            "page_count":len(pages),
            "page_receipts":[{
                key:value for key,value in page.items() if key!="text"
            } for page in pages],
            "truncated_diff_text_does_not_count_as_review":True,
            "human_must_read_each_page_and_approve_exact_page_sha":True,
            "canonical_GameWorkspace_commit_remains_sole_writer":True,
            "reviewed_source_not_committed_yet":True,
        }
        return {**manifest,"digest":digest(manifest)},pages

    def manifest(self,*,project,proposal_id,expected_snapshot=None):
        report,_=self._prepare(
            project=project,proposal_id=proposal_id,
            expected_snapshot=expected_snapshot)
        return report

    def page(self,*,project,proposal_id,index,expected_review_digest,
             expected_snapshot=None):
        if type(index) is not int or not 0<=index<MAX_PAGES:
            raise JeevesAppwideError("bounded exact original diff page index required")
        if type(expected_review_digest) is not str or not SHA.fullmatch(
                expected_review_digest):
            raise JeevesAppwideError("exact current original source review required")
        report,pages=self._prepare(
            project=project,proposal_id=proposal_id,
            expected_snapshot=expected_snapshot)
        if report["digest"]!=expected_review_digest:
            raise JeevesAppwideError("original source changed after review manifest")
        if index>=len(pages):
            raise JeevesAppwideError("source diff page outside current proposal")
        item=pages[index]
        result={
            "schema":SCHEMA+".page",
            "project":project,"proposal_id":proposal_id,
            "manifest_digest":report["digest"],
            "page_index":index,
            "page_count":len(pages),
            "char_offset":item["char_offset"],
            "full_utf8_sha256":item["sha256"],
            "review_text":item["text"],
            "source_sha256":report["new_source_sha256"],
            "human_read_acknowledgement_still_required":True,
            "next_index":index+1 if index+1<len(pages) else None,
        }
        return {**result,"digest":digest(result)}

    def commit(self,*,project,proposal_id,expected_review_digest,reviewed_pages,
               expected_snapshot=None,operator_authorized=False):
        if operator_authorized is not True:
            raise PermissionError("designer must explicitly approve every full diff page")
        if (type(expected_review_digest) is not str or
                not SHA.fullmatch(expected_review_digest) or
                type(reviewed_pages) is not list):
            raise JeevesAppwideError("exact source review and per-page approvals required")
        report,pages=self._prepare(
            project=project,proposal_id=proposal_id,
            expected_snapshot=expected_snapshot)
        if report["digest"]!=expected_review_digest:
            raise JeevesAppwideError("source review receipt stale at commit boundary")
        if len(reviewed_pages)!=len(pages):
            raise JeevesAppwideError("every exact source diff page must be human reviewed")
        acknowledged={}
        for row in reviewed_pages:
            if (type(row) is not dict or
                    set(row)!={"index","sha256","human_approved"} or
                    type(row["index"]) is not int
                    or row["index"] in acknowledged
                    or type(row["sha256"]) is not str or
                    row["human_approved"] is not True):
                raise JeevesAppwideError("invalid duplicate or unapproved source diff page")
            acknowledged[row["index"]]=row["sha256"]
        if acknowledged!={p["index"]:p["sha256"] for p in pages}:
            raise JeevesAppwideError("human page approvals differ from complete original source")
        try:
            action=self.ws.commit(
                proposal_id,human_approved=True,authorized=True)
        except (WorkspaceError,OSError,ValueError) as exc:
            # The original writer can fail after changing the source and
            # before creating the acceptance receipt. Never say no write
            # occurred; surface the observed source and fail closed.
            version=None
            try:
                version=self.ws.read(
                    "current",project,report["source_path"])["version"]["sha256"]
            except (WorkspaceError,OSError,ValueError):
                pass
            receipt_path=(
                self.ws.root/"reviews"/"accepted"/(proposal_id+".json")
            )
            body={
                "schema":SCHEMA+".partial",
                "project":project,"proposal_id":proposal_id,
                "source_path":report["source_path"],
                "observed_source_sha256":version,
                "matches_proposed_source":version==report["new_source_sha256"],
                "accepted_record_is_present":receipt_path.is_file(),
                "manual_reconciliation_before_retry_required":True,
                "failure_class":type(exc).__name__,
            }
            return {**body,"digest":digest(body)}
        body={
            "schema":SCHEMA+".committed",
            "project":project,"proposal_id":proposal_id,
            "source_path":report["source_path"],
            "accepted_source_sha256":action["sha256"],
            "full_diff_sha256":report["full_unified_diff_sha256"],
            "individually_reviewed_diff_pages":len(pages),
            "all_human_reviewed_page_shas_matched":True,
            "canonical_game_source_writer_invoked":True,
            "source_files_committed":1,
            "native_game_or_ci_execution_claimed":False,
        }
        return {**body,"digest":digest(body)}
