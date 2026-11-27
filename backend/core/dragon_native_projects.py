"""Dragon creator documents in the canonical game-learning Mongo workspace.

This adapter saves source data, never grants source-review, rights, compiler,
training or publication authority. Existing project admission, quotas, immutable
revision records and optimistic head commits remain the sole persistence owner.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import re
from typing import Mapping

from core.game_learning import GameLearningError, _key, workspace

SCHEMA = "skeleton.dragon.creator-project.v1"
EXPORT_SCHEMA = "skeleton.dragon.creator-export.v1"
COMPARISON_SCHEMA = "skeleton.dragon.creator-comparison.v1"
SOURCE_PATH = "game/editor/dragon_native.json"
MAX_DOCUMENT_BYTES = 128 * 1024
_HEX = re.compile(r"[a-f0-9]{64}\Z")
_FIELDS = {"schema", "title", "style", "targets", "seed", "portable_design",
           "authored_puzzles", "cited_brief"}
_DESIGN = {"palette", "hero", "quest_theme", "difficulty", "stages", "candidates",
           "project_notes", "procedural_levels", "campaign_pathing", "challenge_profile"}


def canonical(value: object) -> bytes:
    try:
        body = json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise GameLearningError("creator_document_invalid", "Creator project must contain finite UTF-8 JSON.") from exc
    if len(body) > MAX_DOCUMENT_BYTES:
        raise GameLearningError("creator_document_limit", "Creator project exceeds 128 KiB.", 413)
    return body


def _closed(value, keys):
    return type(value) is dict and set(value) == keys


def _text(value, maximum, *, multiline=False):
    return (isinstance(value, str) and len(value) <= maximum
            and not any(ord(c) < 32 and (not multiline or c not in "\n\t") for c in value))


def validate_document(raw: object) -> dict:
    """Structural drafts may be unfinished games; saving never runs the solver."""
    from skeleton.ai.webcrawler.dragon_native_targets import CATALOG, STYLES
    from skeleton.ai.webcrawler.dragon_native_production import PortableGameDesign

    # Leave room for the fixed portable envelope and its digest: every
    # admitted project must remain exportable under the same transport cap.
    if len(canonical(raw)) > MAX_DOCUMENT_BYTES - 256:
        raise GameLearningError("creator_document_limit", "Creator source leaves insufficient room for its portable envelope.", 413)
    valid = (_closed(raw, _FIELDS) and raw["schema"] == SCHEMA
             and isinstance(raw["title"], str)
             and re.fullmatch(r"[A-Za-z][A-Za-z0-9 ._'!-]{2,79}", raw["title"])
             and isinstance(raw["style"], str) and raw["style"] in STYLES
             and type(raw["targets"]) is list and 1 <= len(raw["targets"]) <= 3
             and all(isinstance(t, str) and t in CATALOG for t in raw["targets"])
             and len(set(raw["targets"])) == len(raw["targets"])
             and type(raw["seed"]) is int and 0 <= raw["seed"] <= 0xFFFFFFFF
             and _closed(raw["portable_design"], _DESIGN))
    if not valid:
        raise GameLearningError("creator_document_invalid", "Creator project has missing, unknown or invalid design fields.")
    try:
        PortableGameDesign(**raw["portable_design"]).validate()
    except (TypeError, ValueError) as exc:
        raise GameLearningError("creator_design_invalid", "Creator design controls are invalid.") from exc
    boards = raw["authored_puzzles"]
    if boards is not None and not (
        raw["style"] == "fixed_screen_puzzle" and type(boards) is list
        and len(boards) == raw["portable_design"]["stages"]
        and not raw["portable_design"]["procedural_levels"]
        and all(type(board) is list and len(board) == 10
                and all(isinstance(row, str) and re.fullmatch(r"[#.@$o]{12}", row)
                        for row in board) for board in boards)
    ):
        raise GameLearningError("creator_boards_invalid", "Authored stages must match the bounded 12 by 10 puzzle design.")
    brief = raw["cited_brief"]
    if (not _closed(brief, {"text", "citations"}) or not _text(brief["text"], 12000, multiline=True)
            or type(brief["citations"]) is not list or len(brief["citations"]) > 32):
        raise GameLearningError("creator_brief_invalid", "The saved brief or citation references exceed their bounds.")
    for citation in brief["citations"]:
        if (not _closed(citation, {"source_id", "revision_digest", "title", "url"})
                or not _text(citation["source_id"], 128) or not citation["source_id"]
                or not isinstance(citation["revision_digest"], str)
                or not _HEX.fullmatch(citation["revision_digest"])
                or not _text(citation["title"], 200)
                or not _text(citation["url"], 2048)
                or not re.fullmatch(r"https?://[^\s]+", citation["url"])):
            raise GameLearningError("creator_citation_invalid", "A citation reference is malformed; it is not an approval receipt.")
    return json.loads(canonical(raw))


def _decode(file: Mapping) -> dict:
    try:
        content = file["content"]
        data = validate_document(json.loads(content))
        if (canonical(data).decode() != content
                or file["digest"] != sha256(content.encode()).hexdigest()):
            raise ValueError("source digest changed")
        return data
    except (KeyError, TypeError, ValueError, GameLearningError) as exc:
        raise GameLearningError("creator_source_integrity", "Saved creator source failed integrity checks.", 503) from exc


def compare_documents(before: Mapping, after: Mapping) -> dict:
    """Bounded read-only projection of two already validated source documents."""
    def preview(value):
        return value[:240] if isinstance(value, str) else list(value) if isinstance(value, list) else value

    fields = []
    for path in ("title", "style", "targets", "seed", *("portable_design." + key for key in sorted(_DESIGN))):
        parts = path.split(".")
        left, right = before, after
        for part in parts:
            left, right = left[part], right[part]
        if left != right:
            fields.append({"path": path, "before": preview(left), "after": preview(right),
                           "before_truncated": isinstance(left, str) and len(left) > 240,
                           "after_truncated": isinstance(right, str) and len(right) > 240,
                           "before_sha256": sha256(canonical(left)).hexdigest(),
                           "after_sha256": sha256(canonical(right)).hexdigest()})
    left_brief, right_brief = before["cited_brief"], after["cited_brief"]

    def members(brief):
        return {sha256(canonical(citation)).hexdigest(): citation for citation in brief["citations"]}

    def reference(digest, citation, count):
        return {"reference_sha256": digest, "source_id": citation["source_id"],
                "revision_digest": citation["revision_digest"], "title": citation["title"][:96],
                "url": citation["url"][:256], "title_truncated": len(citation["title"]) > 96,
                "url_truncated": len(citation["url"]) > 256, "count": count}

    left_refs, right_refs = members(left_brief), members(right_brief)
    left_order = [sha256(canonical(citation)).hexdigest() for citation in left_brief["citations"]]
    right_order = [sha256(canonical(citation)).hexdigest() for citation in right_brief["citations"]]
    left_counts, right_counts = Counter(left_order), Counter(right_order)
    boards = []
    left_boards, right_boards = before["authored_puzzles"] or [], after["authored_puzzles"] or []
    for index in range(max(len(left_boards), len(right_boards))):
        left = left_boards[index] if index < len(left_boards) else None
        right = right_boards[index] if index < len(right_boards) else None
        cells = [[row, column, left[row][column] if left else None, right[row][column] if right else None]
                 for row in range(10) for column in range(12)
                 if (left[row][column] if left else None) != (right[row][column] if right else None)]
        if cells:
            boards.append({"stage": index + 1, "kind": "added" if left is None else "removed" if right is None else "modified",
                           "changed_cells": len(cells), "cells": cells})
    return {"fields": fields,
            "brief": {"changed": left_brief["text"] != right_brief["text"],
                      "before_preview": left_brief["text"][:240], "after_preview": right_brief["text"][:240],
                      "before_characters": len(left_brief["text"]), "after_characters": len(right_brief["text"]),
                      "before_sha256": sha256(left_brief["text"].encode()).hexdigest(),
                      "after_sha256": sha256(right_brief["text"].encode()).hexdigest()},
            "citations": {"before_count": len(left_order), "after_count": len(right_order),
                          "order_changed": left_order != right_order,
                          "added": [reference(key, right_refs[key], count) for key, count in sorted((right_counts - left_counts).items())],
                          "removed": [reference(key, left_refs[key], count) for key, count in sorted((left_counts - right_counts).items())]},
            "boards": {"before_count": len(left_boards), "after_count": len(right_boards), "items": boards}}


class DragonCreatorProjects:
    def __init__(self, authority=workspace):
        self.authority = authority

    async def _head(self, scope, project_id):
        row = await self.authority._project(project_id, scope)
        if row.get("_source_only_draft") is not True:
            raise GameLearningError("creator_project_not_found", "Creator project not found.", 404)
        files = row.get("files", [])
        if len(files) != 1 or files[0].get("path") != SOURCE_PATH:
            raise GameLearningError("creator_project_not_found", "Creator project not found.", 404)
        return row, _decode(files[0])

    @staticmethod
    def _view(row, document):
        stamp = lambda value: value.isoformat() if hasattr(value, "isoformat") else value
        return {"schema": SCHEMA, "project_id": row["project_id"], "version": row["version"],
                "document_sha256": sha256(canonical(document)).hexdigest(), "document": document,
                "created_at": stamp(row["created_at"]), "updated_at": stamp(row["updated_at"]),
                "source_only": True, "approval_restored": False}

    async def get(self, scope, project_id):
        return self._view(*(await self._head(scope, project_id)))

    async def _committed(self, scope, project_id, operation_id):
        head, _ = await self._head(scope, project_id)
        row = await self.authority.revisions.find_one({"_id": operation_id, **scope, "project_id": project_id})
        if row is None or operation_id not in head["revision_ids"] or len(row["files"]) != 1:
            raise GameLearningError("creator_commit_unconfirmed", "Project save has not been confirmed. Retry the same operation.", 503)
        committed = {**head, "version": row["version"], "updated_at": row["created_at"]}
        return {**self._view(committed, _decode(row["files"][0])), "head_version": head["version"]}

    async def list(self, scope, *, limit=32, offset=0):
        rows = await self.authority.projects.find(
            {**scope, "state": "active", "_source_only_draft": True,
             "files.path": SOURCE_PATH}).sort([("updated_at", -1), ("_id", -1)]).skip(offset).limit(limit).to_list(length=limit)
        result = []
        for row in rows:
            if len(row.get("files", [])) != 1:
                continue
            document = _decode(row["files"][0])
            view = self._view(row, document)
            result.append({k: v for k, v in view.items() if k != "document"} | {
                "title": document["title"], "style": document["style"], "targets": document["targets"]})
        return result

    async def create(self, scope, body):
        document = validate_document(body["document"])
        await self.authority.create_project(scope, {
            "name": document["title"], "console_id": "dragon_native:" + document["targets"][0],
            "idempotency_key": body["idempotency_key"],
        }, initial_files=[{"path": SOURCE_PATH, "content": canonical(document).decode(), "language": "json"}],
            source_only=True)
        project_id = _key(scope["tenant_id"] + ":" + scope["owner_id"], "project", body["idempotency_key"])
        return await self._committed(scope, project_id, _key(project_id, "initial-editor", body["idempotency_key"]))

    async def save(self, scope, project_id, body):
        document = validate_document(body["document"])
        head, current = await self._head(scope, project_id)
        operation_id = _key(project_id, "editor", body["idempotency_key"])
        prior = await self.authority.revisions.find_one({"_id": operation_id, **scope})
        committed = prior is not None and operation_id in head["revision_ids"]
        if not committed and (head["version"] != body["expected_version"]
                              or sha256(canonical(current)).hexdigest() != body["expected_sha256"]):
            raise GameLearningError("creator_project_conflict", "A newer project revision exists. Your draft is preserved; reopen it or save a copy.", 409)
        await self.authority.save_editor(scope, project_id, {
            "expected_version": body["expected_version"], "idempotency_key": body["idempotency_key"],
            "creator_expected_sha256": body["expected_sha256"],
            "files": [{"path": SOURCE_PATH, "content": canonical(document).decode(), "language": "json"}],
            "entrypoint": SOURCE_PATH,
        })
        return await self._committed(scope, project_id, operation_id)

    async def history(self, scope, project_id, *, before_version=None, limit=32):
        head, _ = await self._head(scope, project_id)
        ids = head["revision_ids"]
        query = {**scope, "project_id": project_id, "_id": {"$in": ids}}
        if before_version is not None:
            query["version"] = {"$lt": before_version}
        rows = await self.authority.revisions.find(query).sort("version", -1).limit(limit).to_list(length=limit)
        result = []
        for row in rows:
            if len(row["files"]) != 1 or row["files"][0]["path"] != SOURCE_PATH:
                raise GameLearningError("creator_source_integrity", "Committed creator history has incompatible source.", 503)
            document = _decode(row["files"][0])
            result.append({"version": row["version"], "title": document["title"],
                           "document_sha256": sha256(canonical(document)).hexdigest(),
                           "created_at": row["created_at"].isoformat()})
        return {"project_id": project_id, "head_version": head["version"], "revisions": result,
                "next_before_version": result[-1]["version"] if len(result) == limit and result[-1]["version"] > 1 else None}

    async def revision(self, scope, project_id, version):
        head, _ = await self._head(scope, project_id)
        row = await self.authority.revisions.find_one({**scope, "project_id": project_id,
                                                     "version": version, "_id": {"$in": head["revision_ids"]}})
        if row is None or len(row["files"]) != 1 or row["files"][0]["path"] != SOURCE_PATH:
            raise GameLearningError("creator_revision_not_found", "Committed creator revision not found.", 404)
        document = _decode(row["files"][0])
        return {"project_id": project_id, "version": version, "head_version": head["version"],
                "document": document, "document_sha256": sha256(canonical(document)).hexdigest(),
                "approval_restored": False}

    async def compare(self, scope, project_id, from_version, to_version):
        if any(type(version) is not int or not 1 <= version <= 512 for version in (from_version, to_version)):
            raise GameLearningError("creator_comparison_invalid", "Choose two saved revision numbers from 1 to 512.", 422)
        # revision() reuses the existing owned-project and committed-membership
        # authority. The pair stays explicit if another save advances the head.
        before = await self.revision(scope, project_id, from_version)
        after = await self.revision(scope, project_id, to_version)
        result = {"schema": COMPARISON_SCHEMA, "project_id": project_id,
                  "from": {"version": from_version, "document_sha256": before["document_sha256"]},
                  "to": {"version": to_version, "document_sha256": after["document_sha256"]},
                  "observed_head_version": max(before["head_version"], after["head_version"]),
                  "changes": compare_documents(before["document"], after["document"]),
                  "source_only": True, "approval_restored": False}
        # Enforce the declared transport budget, including the HTTP envelope.
        canonical({"ok": True, **result})
        return result

    async def export(self, scope, project_id):
        saved = await self.get(scope, project_id)
        return canonical({"schema": EXPORT_SCHEMA, "document": saved["document"],
                          "document_sha256": saved["document_sha256"]})


creator_projects = DragonCreatorProjects()
