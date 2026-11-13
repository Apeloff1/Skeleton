"""GameWorkspace project <-> GameSavePlane save/restore.

Each project is one save-plane slot (``project:<id>``). A save writes two
bundle sections (``bundle`` metadata and ``files`` index) and puts file
contents into a :class:`ChunkReceiptStore` as ``<path>#<n>`` chunks, so the
plane's receipt root seals the content. Versions are save-plane sequences;
any :class:`CheckpointStore` works, including ``SqliteCheckpointStore``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping

from skeleton.ai.game_builder.game_project_workspace import GameWorkspace
from skeleton.kernel.game_save_plane import ChunkReceiptStore, GameSavePlane, SavePlaneError

from .manifest import BUNDLE_SCHEMA_VERSION, BundleError, BundleFile, BundleManifest

CHUNK_CHARS = 32_000
BUNDLE_SECTIONS = ("bundle", "files")


def slot_for(project_id: str) -> str:
    return "project:" + project_id


def _sha(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProjectVersion:
    manifest: BundleManifest
    files: dict[str, str]  # path -> text, verified against the manifest
    sections: dict[str, Any]


def build_state(project_id: str, genre: str, files: Mapping[str, str], *, label: str | None = None
                ) -> tuple[dict[str, dict[str, Any]], ChunkReceiptStore]:
    """Return (sections, receipts) for a project file map, deterministically."""
    receipts = ChunkReceiptStore()
    index: dict[str, Any] = {}
    for path in sorted(files):
        text = files[path]
        chunks = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)] or [""]
        ids = []
        for n, part in enumerate(chunks):
            cid = f"{path}#{n}"
            receipts.put(cid, {"path": path, "index": n, "text": part})
            ids.append(cid)
        index[path] = {"sha256": _sha(text), "bytes": len(text.encode("utf-8")), "chunks": ids}
    sections = {
        "bundle": {"bundle_schema_version": BUNDLE_SCHEMA_VERSION, "project_id": project_id,
                   "genre": genre, "label": label},
        "files": index,
    }
    return sections, receipts


def files_from_state(sections: Mapping[str, Any], receipts: ChunkReceiptStore | None) -> dict[str, str]:
    """Reassemble and verify file texts from the ``files`` index and receipts."""
    if receipts is None:
        raise BundleError("save has no content receipts")
    by_id: dict[str, str] = {}
    cursor: int | None = 0
    while cursor is not None:
        page = receipts.page(cursor=cursor, limit=receipts.max_page_size)
        for r in page.items:  # page() verifies each receipt digest
            by_id[r.chunk_id] = r.body["text"]
        cursor = page.next_cursor
    out: dict[str, str] = {}
    for path, entry in sorted(sections["files"].items()):
        try:
            text = "".join(by_id[c] for c in entry["chunks"])
        except KeyError as exc:
            raise BundleError(f"missing content chunk for {path}") from exc
        if _sha(text) != entry["sha256"]:
            raise BundleError(f"file digest mismatch for {path}")
        out[path] = text
    return out


def manifest_for(sections: Mapping[str, Any], receipts: ChunkReceiptStore, sequence: int,
                 save_schema_version: int) -> BundleManifest:
    meta = sections["bundle"]
    return BundleManifest(
        project_id=meta["project_id"], genre=meta["genre"],
        files=tuple(BundleFile(p, e["sha256"], e["bytes"]) for p, e in sorted(sections["files"].items())),
        receipt_root=receipts.root(), sequence=sequence, label=meta.get("label"),
        save_schema_version=save_schema_version,
        bundle_schema_version=int(meta.get("bundle_schema_version", BUNDLE_SCHEMA_VERSION)),
    )


class ProjectSaver:
    """Save/restore workspace projects through one GameSavePlane."""

    def __init__(self, plane: GameSavePlane) -> None:
        self.plane = plane

    def next_sequence(self, project_id: str) -> int:
        latest = self.plane.store.latest(GameSavePlane.COMPONENT_PREFIX + slot_for(project_id))
        return 1 if latest is None else latest.sequence + 1

    def save_files(self, project_id: str, genre: str, files: Mapping[str, str], *,
                   sequence: int | None = None, label: str | None = None,
                   extra_sections: Mapping[str, Mapping[str, Any]] | None = None) -> BundleManifest:
        sections, receipts = build_state(project_id, genre, files, label=label)
        for name, body in (extra_sections or {}).items():
            if name in BUNDLE_SECTIONS:
                raise BundleError(f"section {name!r} is reserved for the bundle")
            sections[name] = dict(body)  # opaque passthrough (e.g. gameplay state)
        seq = self.next_sequence(project_id) if sequence is None else sequence
        manifest = manifest_for(sections, receipts, seq, self.plane.schema_version)  # validates first
        self.plane.save(slot_for(project_id), seq, sections, receipts=receipts)
        return manifest

    def save_project(self, workspace: GameWorkspace, project_id: str, *, sequence: int | None = None,
                     label: str | None = None) -> BundleManifest:
        """Snapshot a ``current`` workspace project into the save plane."""
        record = workspace.read("current", project_id, "project.json")
        genre = json.loads(record["content"])["genre"]
        files: dict[str, str] = {}
        for fv in workspace.files("current", project_id):
            body = workspace.read("current", project_id, fv.path)["content"]
            if _sha(body) != fv.sha256:
                raise BundleError(f"{fv.path} changed while saving")
            files[fv.path] = body
        return self.save_files(project_id, genre, files, sequence=sequence, label=label)

    def load(self, project_id: str, *, sequence: int | None = None) -> ProjectVersion:
        try:
            sections, receipts = self.plane.restore(slot_for(project_id), sequence=sequence)
        except SavePlaneError as exc:
            raise BundleError(f"no restorable version for {project_id}") from exc
        from .migrations import check_bundle_schema
        sections = check_bundle_schema(dict(sections))
        files = files_from_state(sections, receipts)
        seq = sequence if sequence is not None else self.plane.store.restore(
            GameSavePlane.COMPONENT_PREFIX + slot_for(project_id)).sequence
        manifest = manifest_for(sections, receipts, seq, self.plane.schema_version)
        return ProjectVersion(manifest, files, dict(sections))

    def restore_to_workspace(self, workspace: GameWorkspace, project_id: str, *,
                             sequence: int | None = None, human_approved: bool,
                             authorized: bool, reason: str = "restore project version from save plane"
                             ) -> dict[str, Any]:
        """Write a saved version back through the workspace's review flow.

        Uses only ``propose``/``commit`` (so all workspace validators and the
        human-commit gate still apply). The workspace exposes no delete, so
        files absent from the saved version are reported, not removed.
        """
        if not authorized or human_approved is not True:
            raise PermissionError("restoring a project version needs explicit human approval")
        version = self.load(project_id, sequence=sequence)
        if workspace.active() != project_id:
            workspace.select_project(project_id, authorized=True)
        current = {fv.path: fv.sha256 for fv in workspace.files("current", project_id)}
        written = []
        for path, text in sorted(version.files.items()):
            before = current.get(path, _sha(""))
            if before == _sha(text):
                continue
            prop = workspace.propose(project_id, path, text, expected_sha256=before,
                                     reason=reason, authorized=True)
            workspace.commit(prop["proposal_id"], human_approved=True, authorized=True)
            written.append(path)
        return {"sequence": version.manifest.sequence, "written": written,
                "not_removed": sorted(set(current) - set(version.files))}


__all__ = ["CHUNK_CHARS", "BUNDLE_SECTIONS", "ProjectSaver", "ProjectVersion", "slot_for",
           "build_state", "files_from_state", "manifest_for"]
