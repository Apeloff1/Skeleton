"""Executable original game-design source editing through Jeeves' CreatorCommand.

This is a concrete local project-source owner, NOT an in-memory pretend forge:
approved create/edit commands commit revisioned SQLite documents and receipts;
test/preview read actual persisted material; export writes content-addressed
JSON source bundles to an explicit host-owned directory.

Real Godot compilations, sprite generation and runtime tests are separate
adapters; a successful document export cannot claim those effects.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from hashlib import sha256
import json
import io
import os
from pathlib import Path, PurePosixPath
import zipfile
import re
import sqlite3
from threading import RLock
from typing import Any

from skeleton.forge.creator.command_surface import (
    CreatorCommand, build_creator_command, dispatch_creator_command,
)
from skeleton.jeeves.agent.tools import (
    ArgumentRule, ToolDenied, ToolExecutionContext, ToolRegistry, ToolSpec,
)
from skeleton.jeeves.agent.types import RiskTier

from .studio_interaction_contract import FACETS, digest, identifier

SCHEMA = "skeleton.jeeves.creator_source_store.v1"
MAX_RECORD_BYTES = 96 * 1024
MAX_RECORDS = 50_000
MAX_EVENTS = 200_000
MAX_BUNDLE_BYTES = 16 * 1024 * 1024
HEX = re.compile(r"^[0-9a-f]{64}$")

_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS creator_source_meta(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 project_id TEXT NOT NULL, head_sha256 TEXT, event_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS creator_source_record(
 record_id TEXT PRIMARY KEY, facet TEXT NOT NULL,
 revision INTEGER NOT NULL, document_json TEXT NOT NULL,
 dependencies_json TEXT NOT NULL, content_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS creator_source_event(
 sequence INTEGER PRIMARY KEY, kind TEXT NOT NULL, record_id TEXT NOT NULL,
 prior_content_sha256 TEXT, new_content_sha256 TEXT NOT NULL,
 command_sha256 TEXT NOT NULL, previous TEXT, digest TEXT NOT NULL UNIQUE
);
"""


class CreatorSourceError(ValueError):
    """Invalid original source, missing host owner or stale project revision."""


def _json(value: Any, *, limit: int = MAX_RECORD_BYTES) -> bytes:
    # Do not inherit the studio *event* byte cap for whole project exports:
    # 50k source records cannot fit within one audit-event envelope.
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise CreatorSourceError("authored source must be finite JSON") from exc
    if len(raw) > limit:
        raise CreatorSourceError("authored source exceeds bounded JSON budget")
    return raw


def _document(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not value or len(value) > 96:
        raise CreatorSourceError("creator document requires bounded original fields")
    copy = json.loads(_json(value))
    if any(
        not isinstance(key, str) or not key or len(key) > 128
        or key.startswith("_") or any(ord(c) < 32 for c in key)
        for key in copy
    ):
        raise CreatorSourceError("creator document contains reserved fields")
    return copy


def _deps(value: Any, *, record_id: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 32:
        raise CreatorSourceError("source dependency list exceeds authoring budget")
    result = [identifier(item, "source dependency") for item in value]
    if len(set(result)) != len(result) or record_id in result:
        raise CreatorSourceError("duplicate or self-referential source dependency")
    return result


def _godot_archive(
    files: Mapping[str, str], receipt: Mapping[str, Any],
    *, binary_assets: Mapping[str, bytes] | None = None,
) -> bytes:
    """Deterministically package exact independently verified Godot source."""
    if not isinstance(files, Mapping) or not files or len(files) > 128:
        raise CreatorSourceError("Godot archive requires bounded native source files")
    binary = {} if binary_assets is None else dict(binary_assets)
    if (set(files) & set(binary) or len(files) + len(binary) > 128
            or any(type(payload) is not bytes for payload in binary.values())):
        raise CreatorSourceError("native image source must be distinct bounded binary files")
    expected = receipt.get("godot_file_hashes")
    if not isinstance(expected, Mapping) or set(expected) != set(files) | set(binary):
        raise CreatorSourceError("Godot file hash ancestry differs from native proof")
    manifest = _json(dict(receipt), limit=MAX_RECORD_BYTES)
    output = io.BytesIO()
    total = len(manifest)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, allowZip64=False) as archive:
        for name in sorted(set(files) | set(binary)):
            path = PurePosixPath(name)
            if (not isinstance(name, str) or not name
                    or path.is_absolute() or ".." in path.parts
                    or "\\" in name or path.as_posix() != name
                    or name == "jeeves_source_receipt.json"):
                raise CreatorSourceError("Godot source path attempts archive traversal")
            if name in binary:
                raw = binary[name]
            else:
                content = files[name]
                if not isinstance(content, str):
                    raise CreatorSourceError("Godot exporter supplied nontext native file")
                raw = content.encode("utf-8")
            if sha256(raw).hexdigest() != expected[name]:
                raise CreatorSourceError("Godot native source differs from validated receipt")
            total += len(raw)
            if total > MAX_BUNDLE_BYTES:
                raise CreatorSourceError("Godot game source exceeds archive budget")
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, raw)
        proof = zipfile.ZipInfo("jeeves_source_receipt.json", (1980, 1, 1, 0, 0, 0))
        proof.compress_type = zipfile.ZIP_DEFLATED
        proof.external_attr = 0o100644 << 16
        archive.writestr(proof, manifest)
    data = output.getvalue()
    if len(data) > MAX_BUNDLE_BYTES:
        raise CreatorSourceError("compressed native project exceeds artifact budget")
    return data


def _sprite_archive(
    compiled: Mapping[str, Any], *, project_id: str,
    source_head_sha256: str | None,
) -> bytes:
    """Write reproducible PNG and animation-state assets with source receipts."""
    from .studio_sprite_verify import verify_published_sprite
    from .studio_sprite_godot_resources import (
        compile_godot_sprite_resources, verify_godot_sprite_resources,
    )

    atlas = compiled["assets"]
    metadata = {
        "schema_version": "skeleton.jeeves.sprite_package.v1",
        "project_id": project_id, "source_head_sha256": source_head_sha256,
        "asset_count": compiled["count"],
        "atlas_hashes": compiled["atlas_hashes"],
        "sprites": [item["metadata"] for item in atlas],
        "native_engine_sprite_binding_verified": False,
        "artist_review_claimed": False,
    }
    metadata["receipt_sha256"] = digest(metadata)
    files: dict[str, bytes] = {}
    for entry in atlas:
        proof = entry["metadata"]
        name = proof["asset_id"]
        raw = entry["png"]
        if sha256(raw).hexdigest() != proof["png_sha256"]:
            raise CreatorSourceError("sprite output differs from its generated proof")
        independent = verify_published_sprite(raw, proof)
        if not independent["layout_and_padding_reproduced"]:
            raise CreatorSourceError("published sprite pixel atlas does not replay")
        files["sprites/" + name + ".png"] = raw
        files["sprites/" + name + ".json"] = _json(proof)
        resources = compile_godot_sprite_resources(
            proof, directory="sprites",
        )
        verify_godot_sprite_resources(proof, resources, directory="sprites")
        for path, source in resources.items():
            if path in files:
                raise CreatorSourceError("Godot sprite resource identity collides")
            files[path] = source.encode("utf-8")
    files["jeeves_sprite_receipt.json"] = _json(metadata, limit=MAX_BUNDLE_BYTES)
    total = sum(len(raw) for raw in files.values())
    if total > MAX_BUNDLE_BYTES:
        raise CreatorSourceError("sprite project would exceed export size budget")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9, allowZip64=False) as archive:
        for name in sorted(files):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, files[name])
    data = output.getvalue()
    if len(data) > MAX_BUNDLE_BYTES:
        raise CreatorSourceError("compressed sprite atlas exceeds artifact size")
    with zipfile.ZipFile(io.BytesIO(data)) as reread:
        if set(reread.namelist()) != set(files):
            raise CreatorSourceError("published sprite package membership differs")
        for name, raw in files.items():
            if reread.read(name) != raw:
                raise CreatorSourceError("published sprite bytes differ from original")
    return data


def _project_path(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise CreatorSourceError("private absolute SQLite source-store path required")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise CreatorSourceError("source store requires an existing private directory")
    return path


class CreatorProjectSourceStore:
    """Durable source records plus a fully replayed SHA-linked command history."""

    def __init__(self, path: Path, *, project_id: str, export_root: Path) -> None:
        self.path = _project_path(path)
        self.project_id = identifier(project_id, "creator project")
        self.export_root = Path(export_root)
        if (not self.export_root.is_absolute() or self.export_root.is_symlink()
                or not self.export_root.is_dir()):
            raise CreatorSourceError("preexisting private non-symlink export root required")
        self._lock = RLock()
        self._db = sqlite3.connect(str(path), timeout=10, isolation_level=None,
                                   check_same_thread=False)
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_SQL)
            owner = self._db.execute(
                "SELECT project_id FROM creator_source_meta WHERE singleton=1"
            ).fetchone()
            if owner is None:
                if self._db.execute("SELECT COUNT(*) FROM creator_source_event").fetchone()[0]:
                    raise CreatorSourceError("source history is missing its project owner")
                self._db.execute("INSERT INTO creator_source_meta VALUES(1,?,NULL,0)",
                                 (self.project_id,))
            elif owner[0] != self.project_id:
                raise CreatorSourceError("creator source store belongs to another game")
            self.verify()
            self._data_version = self._db.execute("PRAGMA data_version").fetchone()[0]
        except BaseException:
            self._db.close()
            raise

    def _documents(self) -> dict[str, dict[str, Any]]:
        rows = self._db.execute(
            "SELECT record_id,facet,revision,document_json,"
            "dependencies_json,content_sha256 FROM creator_source_record ORDER BY record_id"
        )
        documents = {}
        for name, facet, revision, raw, rawdeps, head in rows:
            identifier(name, "creator source")
            if facet not in FACETS or type(revision) is not int or revision < 1:
                raise CreatorSourceError("source record identity or revision changed")
            document = _document(json.loads(raw))
            dependencies = _deps(json.loads(rawdeps), record_id=name)
            if (raw != _json(document).decode("utf-8")
                    or rawdeps != _json(dependencies).decode("utf-8")
                    or digest([name, facet, revision, document, dependencies]) != head):
                raise CreatorSourceError("creator source record digest changed")
            if name in documents:
                raise CreatorSourceError("duplicate source record")
            documents[name] = {
                "record_id": name, "facet": facet, "revision": revision,
                "document": document, "depends_on": dependencies,
                "source_sha256": head,
            }
        if len(documents) > MAX_RECORDS:
            raise CreatorSourceError("creator project exceeds record budget")
        return documents

    def verify(self) -> dict[str, Any]:
        """Replay real create/edit effects and compare against materialized records."""
        with self._lock:
            meta = self._db.execute(
                "SELECT project_id,head_sha256,event_count FROM creator_source_meta"
            ).fetchall()
            if len(meta) != 1 or meta[0][0] != self.project_id:
                raise CreatorSourceError("creator source owner metadata is corrupt")
            count = 0
            prior = None
            # Check live materialization against each corresponding final
            # mutation. A rewritten source cannot pass just by changing metadata.
            state: dict[str, str] = {}
            for seq, kind, record, old, new, command, ancestor, sha in self._db.execute(
                "SELECT sequence,kind,record_id,prior_content_sha256,"
                "new_content_sha256,command_sha256,previous,digest "
                "FROM creator_source_event ORDER BY sequence"
            ):
                if (seq != count or count >= MAX_EVENTS or kind not in ("create", "edit")
                        or ancestor != prior or not HEX.fullmatch(new)
                        or not HEX.fullmatch(command)
                        or old != state.get(record)
                        or (kind == "create" and record in state)
                        or (kind == "edit" and record not in state)):
                    raise CreatorSourceError("creator source event ancestry is invalid")
                payload = {
                    "schema_version": SCHEMA, "project_id": self.project_id,
                    "sequence": seq, "kind": kind, "record_id": record,
                    "prior_content_sha256": old, "new_content_sha256": new,
                    "command_sha256": command, "previous": ancestor,
                }
                if digest(payload) != sha:
                    raise CreatorSourceError("creator source history digest differs")
                state[record] = new
                prior = sha
                count += 1
            documents = self._documents()
            if (count != meta[0][2] or prior != meta[0][1]
                    or state != {key: value["source_sha256"]
                                 for key, value in documents.items()}):
                raise CreatorSourceError("source records differ from transaction history")
            self._head = prior
            self._event_count = count
            self._records = documents
            return {
                "schema_version": SCHEMA, "project_id": self.project_id,
                "event_count": count, "head_sha256": prior,
                "source_count": len(documents),
            }

    def _refresh(self) -> None:
        version = self._db.execute("PRAGMA data_version").fetchone()[0]
        if version != self._data_version:
            self.verify()
            self._data_version = version

    def _validate_graph(self, documents: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
        """Iterative DFS avoids depth failures in multi-year dependency graphs."""
        missing: set[str] = set()
        cycles: set[str] = set()
        done: set[str] = set()
        visiting: set[str] = set()
        for key in sorted(documents):
            stack: list[tuple[str, bool]] = [(key, False)]
            while stack:
                node, leaving = stack.pop()
                if leaving:
                    visiting.discard(node)
                    done.add(node)
                    continue
                if node in done:
                    continue
                if node in visiting:
                    cycles.add(node)
                    continue
                if node not in documents:
                    missing.add(node)
                    continue
                visiting.add(node)
                stack.append((node, True))
                stack.extend((dep, False) for dep in
                             reversed(documents[node]["depends_on"]))
        return {
            "sources_checked": len(documents),
            "missing_dependencies": sorted(missing),
            "cyclic_dependencies": sorted(cycles),
            "valid": not missing and not cycles,
        }

    def search(self, query: str, *, limit: int = 6,
               facet: str | None = None) -> dict[str, Any]:
        """Find relevant real authored documents with exact revision proofs."""
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2048:
            raise CreatorSourceError("bounded source question required")
        if type(limit) is not int or not 1 <= limit <= 12:
            raise CreatorSourceError("authoring-context retrieval budget invalid")
        if facet is not None and facet not in FACETS:
            raise CreatorSourceError("unknown source facet filter")
        terms = set(re.findall(r"[^\W_]+", query.casefold())) - {
            "the", "and", "are", "you", "how", "that", "with", "from", "for",
        }
        if not terms:
            raise CreatorSourceError("source query contains no searchable terms")
        with self._lock:
            self._refresh()
            scores: list[tuple[int, str, dict[str, Any]]] = []
            for key, record in self._records.items():
                if facet is not None and record["facet"] != facet:
                    continue
                searchable = key + " " + record["facet"] + " " + json.dumps(
                    record["document"], sort_keys=True, ensure_ascii=False,
                )
                overlap = len(terms & set(re.findall(
                    r"[^\W_]+", searchable.casefold(),
                )))
                if overlap:
                    scores.append((-overlap, key, record))
            scores.sort(key=lambda item: (item[0], item[1]))
            excerpts = []
            for _, key, record in scores[:limit]:
                raw = _json(record["document"])
                excerpts.append({
                    "record_id": key, "facet": record["facet"],
                    "revision": record["revision"],
                    "source_sha256": record["source_sha256"],
                    "depends_on": record["depends_on"],
                    "document_excerpt": raw[:1000].decode("utf-8", errors="ignore"),
                    "excerpt_is_partial": len(raw) > 1000,
                })
            return {
                "schema_version": SCHEMA, "project_id": self.project_id,
                "source_head_sha256": self._head,
                "source_count": len(self._records), "results": excerpts,
                "results_sha256": digest(excerpts),
                "native_engine_compilation_performed": False,
            }

    def _mutate(self, command: CreatorCommand, *,
                record_id: str, facet: str, document: dict[str, Any],
                depends_on: list[str], old: dict[str, Any] | None) -> dict[str, Any]:
        expected = old["source_sha256"] if old else None
        version = old["revision"] + 1 if old else 1
        content_sha = digest([record_id, facet, version, document, depends_on])
        # Do not persist a structurally invalid image as a valid game asset.
        # Validate original pixel bytes and independent verification before
        # opening the SQLite write transaction (which stays short).
        if facet == "sprite_forge" and document.get("kind") == "pixel_sprite":
            from .studio_sprite_forge import compile_authored_sprite
            compile_authored_sprite({
                "record_id": record_id, "facet": facet,
                "revision": version, "document": document,
                "depends_on": depends_on,
                "source_sha256": content_sha,
            })
        if self._event_count >= MAX_EVENTS:
            raise CreatorSourceError("source event journal needs archival")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            meta = self._db.execute(
                "SELECT head_sha256,event_count FROM creator_source_meta WHERE singleton=1"
            ).fetchone()
            if meta != (self._head, self._event_count):
                raise CreatorSourceError("concurrent creator-source writer changed revision head")
            current = self._db.execute(
                "SELECT content_sha256 FROM creator_source_record WHERE record_id=?",
                (record_id,),
            ).fetchone()
            if (current[0] if current else None) != expected:
                raise CreatorSourceError("creator document was concurrently modified")
            if old is None:
                if len(self._records) >= MAX_RECORDS:
                    raise CreatorSourceError("project reached source-record budget")
                self._db.execute(
                    "INSERT INTO creator_source_record VALUES(?,?,?,?,?,?)",
                    (record_id, facet, version, _json(document).decode("utf-8"),
                     _json(depends_on).decode("utf-8"), content_sha),
                )
            else:
                self._db.execute(
                    "UPDATE creator_source_record SET revision=?,document_json=?,"
                    "dependencies_json=?,content_sha256=? WHERE record_id=?",
                    (version, _json(document).decode("utf-8"),
                     _json(depends_on).decode("utf-8"), content_sha, record_id),
                )
            event = {
                "schema_version": SCHEMA, "project_id": self.project_id,
                "sequence": self._event_count,
                "kind": command.operation, "record_id": record_id,
                "prior_content_sha256": expected,
                "new_content_sha256": content_sha,
                "command_sha256": command.digest, "previous": self._head,
            }
            head = digest(event)
            self._db.execute(
                "INSERT INTO creator_source_event VALUES (?,?,?,?,?,?,?,?)",
                (self._event_count, command.operation, record_id, expected,
                 content_sha, command.digest, self._head, head),
            )
            self._db.execute("UPDATE creator_source_meta SET "
                             "head_sha256=?,event_count=? WHERE singleton=1",
                             (head, self._event_count + 1))
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise
        self._records[record_id] = {
            "record_id": record_id, "facet": facet, "revision": version,
            "document": document, "depends_on": depends_on, "source_sha256": content_sha,
        }
        self._head = head
        self._event_count += 1
        return {
            "project_id": self.project_id, "record_id": record_id,
            "facet": facet, "revision": version,
            "source_sha256": content_sha, "history_sha256": head,
            "source_written_to_sqlite": True,
            "game_executable_created": False,
        }

    def create(self, command: CreatorCommand) -> dict[str, Any]:
        if command.operation != "create":
            raise CreatorSourceError("creator create command required")
        intent = command.payload["intent"]
        if not isinstance(intent, Mapping) or set(intent) != {
            "record_id", "facet", "document", "depends_on",
        }:
            raise CreatorSourceError("creator intent needs record_id, facet, document and depends_on")
        record_id = identifier(intent["record_id"], "source record")
        facet = intent["facet"]
        if facet not in FACETS:
            raise CreatorSourceError("source facet is not in the Jeeves Studio catalog")
        document = _document(intent["document"])
        dependencies = _deps(intent["depends_on"], record_id=record_id)
        with self._lock:
            self._refresh()
            if record_id in self._records:
                raise CreatorSourceError("record already exists; use reviewed edit with revision")
            if any(dep not in self._records for dep in dependencies):
                raise CreatorSourceError("creator source cannot refer to an uncreated dependency")
            return self._mutate(command, record_id=record_id, facet=facet,
                                document=document, depends_on=dependencies, old=None)

    def edit(self, command: CreatorCommand) -> dict[str, Any]:
        if command.operation != "edit":
            raise CreatorSourceError("creator edit command required")
        record_id = identifier(command.payload["target_id"], "source record")
        patch = command.payload["patch"]
        if not isinstance(patch, Mapping) or set(patch) != {"set", "remove"}:
            raise CreatorSourceError("edit patch requires explicit set and remove")
        updates, removals = patch["set"], patch["remove"]
        if (not isinstance(updates, Mapping) or not isinstance(removals, list)
                or len(removals) > 96 or not all(isinstance(x, str) for x in removals)
                or set(updates) & set(removals)):
            raise CreatorSourceError("invalid disjoint edit changes")
        with self._lock:
            self._refresh()
            old = self._records.get(record_id)
            if old is None:
                raise CreatorSourceError("source record not found")
            if old["revision"] != command.payload["expected_revision"]:
                raise CreatorSourceError("stale revision; review current source before editing")
            new_doc = dict(old["document"])
            for field in removals:
                if field not in new_doc:
                    raise CreatorSourceError("edit attempts to remove an absent source field")
                del new_doc[field]
            new_doc.update(dict(updates))
            updated = _document(new_doc)
            if updated == old["document"]:
                raise CreatorSourceError("no-op edit must not claim a source revision")
            return self._mutate(
                command, record_id=record_id, facet=old["facet"],
                document=updated, depends_on=old["depends_on"], old=old,
            )

    def test(self, command: CreatorCommand) -> dict[str, Any]:
        scopes = command.payload["scopes"]
        with self._lock:
            self._refresh()
            missing = sorted(set(scopes) - set(self._records))
            dependency = self._validate_graph(self._records)
            result = {
                "schema_version": SCHEMA, "profile": command.payload["profile"],
                "requested_scopes": list(scopes), "missing_requested_sources": missing,
                "dependency_assurance": dependency,
                "source_count": len(self._records), "history_sha256": self._head,
                "passed": not missing and dependency["valid"],
                "engine_playthrough_performed": False,
            }
            result["report_sha256"] = digest(result)
            return result

    def preview(self, command: CreatorCommand) -> dict[str, Any]:
        scopes = command.payload["scopes"]
        mode = command.payload["mode"]
        if mode != "static":
            raise CreatorSourceError("runtime preview requires a real engine adapter")
        with self._lock:
            self._refresh()
            if any(key not in self._records for key in scopes):
                raise CreatorSourceError("preview cannot invent missing source records")
            documents = [self._records[key] for key in scopes]
            return {
                "schema_version": SCHEMA, "mode": mode,
                "project_id": self.project_id, "source_head_sha256": self._head,
                "documents": json.loads(_json(documents, limit=MAX_BUNDLE_BYTES)),
                "rendered_frames": False, "native_engine_used": False,
            }

    def export(self, command: CreatorCommand) -> dict[str, Any]:
        export_format = command.payload["format"]
        if export_format not in (
            "game-source-json", "frontier-studio-json", "frontier-godot4-zip",
            "sprite-atlas-zip",
        ):
            raise CreatorSourceError("unsupported typed game source export format")
        artifact = identifier(command.payload["artifact_name"], "artifact")
        if "/" in artifact or "\\" in artifact:
            raise CreatorSourceError("source artifact name must not contain path separators")
        with self._lock:
            self._refresh()
            generation = self._head
            report = self._validate_graph(self._records)
            if not self._records or not report["valid"]:
                raise CreatorSourceError("unresolved sources or dependencies block export")
            if export_format == "sprite-atlas-zip":
                from .studio_sprite_forge import compile_sprite_collection
                compiled = compile_sprite_collection(self._records)
                raw = _sprite_archive(
                    compiled, project_id=self.project_id,
                    source_head_sha256=self._head,
                )
                extension = ".zip"
            elif export_format == "frontier-godot4-zip":
                from .studio_frontier_godot_package import compile_original_godot_candidate
                candidate = compile_original_godot_candidate(
                    self.project_id, self._records,
                    source_head_sha256=self._head,
                )
                raw = _godot_archive(
                    candidate["files"], candidate["receipt"],
                    binary_assets=candidate["binary_assets"],
                )
                extension = ".zip"
            elif export_format == "frontier-studio-json":
                from .studio_frontier_source_compile import (
                    compile_persisted_frontier_source,
                )
                bundle = compile_persisted_frontier_source(
                    self.project_id, self._records,
                    source_head_sha256=self._head,
                )
            else:
                bundle = {
                    "schema_version": SCHEMA, "project_id": self.project_id,
                    "source_head_sha256": self._head,
                    "source_count": len(self._records),
                    "source_documents": [
                        self._records[key] for key in sorted(self._records)
                    ],
                    "dependency_assurance": report,
                    "native_binary_compiled": False,
                }
            if export_format not in ("frontier-godot4-zip", "sprite-atlas-zip"):
                raw = _json(bundle, limit=MAX_BUNDLE_BYTES)
                extension = ".json"
            # Compilation can take longer than ordinary SQLite mutations.
            # Do not emit a supposedly current source bundle if another
            # producer committed during compilation.
            self._refresh()
            if self._head != generation:
                raise CreatorSourceError("project source changed during candidate compilation")
            content_sha = sha256(raw).hexdigest()
            name = artifact + "-" + content_sha[:24] + extension
            target = self.export_root / name
            if target.is_symlink():
                raise CreatorSourceError("export target cannot be a symbolic link")
            def disk_proof() -> dict[str, Any] | None:
                if export_format == "sprite-atlas-zip":
                    # Independently reread the exact bytes from the export
                    # directory, not the in-memory ZIP buffer used by PNG forge.
                    published_bytes = target.read_bytes()
                    if published_bytes != raw:
                        raise CreatorSourceError(
                            "saved original sprite archive differs from reviewed bytes"
                        )
                    return {
                        "schema_version": "skeleton.jeeves.sprite_disk_receipt.v1",
                        "project_id": self.project_id,
                        "source_head_sha256": self._head,
                        "archive_sha256": sha256(published_bytes).hexdigest(),
                        "archive_bytes": len(published_bytes),
                        "actual_archive_bytes_verified": True,
                        "native_sprite_scene_binding_verified": False,
                    }
                if export_format != "frontier-godot4-zip":
                    return None
                from .studio_godot_zip_verify import verify_published_godot_zip
                return verify_published_godot_zip(
                    target, project_id=self.project_id,
                    source_head_sha256=self._head,
                    expected_archive_sha256=content_sha,
                )

            if target.exists():
                if target.read_bytes() != raw:
                    raise CreatorSourceError("previous export identity has conflicting bytes")
                published = disk_proof()
                return {
                    "project_id": self.project_id, "artifact_name": name,
                    "disk_verification": published,
                    "bytes": len(raw), "artifact_sha256": content_sha,
                    "source_head_sha256": self._head,
                    "export_format": export_format,
                    "already_exported": True, "native_binary_compiled": False,
                }
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(raw)
                    f.flush()
                    os.fsync(f.fileno())
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            try:
                published = disk_proof()
            except BaseException:
                # Do not publish an unverified Godot archive. Keep it for
                # forensics if an external actor changed its bytes meanwhile.
                if target.read_bytes() == raw:
                    target.unlink(missing_ok=True)
                raise
            return {
                "project_id": self.project_id, "artifact_name": name,
                "disk_verification": published,
                "bytes": len(raw), "artifact_sha256": content_sha,
                "source_head_sha256": self._head,
                "export_format": export_format,
                "already_exported": False, "native_binary_compiled": False,
            }

    def mutations_after(self, expected_head_sha256: str | None,
                        *, limit: int = 32) -> list[dict[str, str]]:
        """Reconstruct host source effects since an independently pinned head.

        Production resume can admit only effects whose command hashes have
        already succeeded in the identical durable CreatorRunbook. Any other
        project mutation makes the model's decision context stale.
        """
        if (expected_head_sha256 is not None
                and not HEX.fullmatch(expected_head_sha256)):
            raise CreatorSourceError("source lineage pin requires a valid SHA-256")
        if type(limit) is not int or not 1 <= limit <= 128:
            raise CreatorSourceError("bounded source-delta inspection required")
        with self._lock:
            self._refresh()
            if expected_head_sha256 == self._head:
                return []
            if expected_head_sha256 is None:
                start = -1
            else:
                match = self._db.execute(
                    "SELECT sequence FROM creator_source_event WHERE digest=?",
                    (expected_head_sha256,),
                ).fetchone()
                if match is None:
                    raise CreatorSourceError("source history does not contain plan generation")
                start = match[0]
            rows = self._db.execute(
                "SELECT command_sha256,digest,record_id FROM creator_source_event "
                "WHERE sequence>? ORDER BY sequence LIMIT ?",
                (start, limit + 1),
            ).fetchall()
            if len(rows) > limit:
                raise CreatorSourceError("more source edits than current runbook supports")
            return [
                {"command_sha256": row[0], "event_sha256": row[1],
                 "record_id": row[2]} for row in rows
            ]

    def run_native_playthrough(
        self, *, godot_executable: str, timeout_seconds: int = 90,
    ) -> dict[str, Any]:
        """Execute existing Godot 4 native verification against actual source.

        The caller MUST be a host-authenticated producer; this method does
        not expose a model tool or issue runtime execution permission.
        """
        from .studio_frontier_godot_package import (
            run_original_game_native_playthrough,
        )
        with self._lock:
            self._refresh()
            previous = self._head
            evidence = run_original_game_native_playthrough(
                self.project_id, self._records,
                source_head_sha256=previous,
                godot_executable=godot_executable,
                timeout_seconds=timeout_seconds,
            )
            # Refuse to attach the verified native result to a different
            # source generation if an outside producer changed the SQLite
            # game while the Godot process executed.
            self._refresh()
            if self._head != previous:
                raise CreatorSourceError(
                    "game source changed during native engine execution"
                )
            return evidence

    def head_identity(self) -> str | None:
        """O(1) trusted in-process project head; verify external SQLite changes."""
        with self._lock:
            self._refresh()
            return self._head

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._refresh()
            result = self.verify()
            result["dependency_assurance"] = self._validate_graph(self._records)
            return result

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> "CreatorProjectSourceStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def register_creator_source_tool(
    registry: ToolRegistry, *, store: CreatorProjectSourceStore,
    authorize: Callable[[CreatorCommand, ToolExecutionContext], bool],
) -> str:
    """Install the actual typed create/edit/test/preview/export host handler.

    Registering does not issue ToolGrants or approve plans. The outer creator
    runbook still requires a separate exact fingerprint, expiring one-shot
    HIGH_IMPACT grant for every action.
    """
    if not isinstance(registry, ToolRegistry) or not isinstance(store, CreatorProjectSourceStore):
        raise CreatorSourceError("real host registry and durable source store required")
    if not callable(authorize):
        raise CreatorSourceError("host exact-command authorizer is mandatory")
    handlers = {
        "create": store.create, "edit": store.edit,
        "test": store.test, "preview": store.preview,
        "export": store.export,
    }

    def perform(arguments: Mapping[str, Any],
                context: ToolExecutionContext) -> dict[str, Any]:
        # Only the existing typed command compiler may mint command identity.
        command = build_creator_command(
            arguments["operation"], project_id=arguments["project_id"],
            payload=arguments["payload"],
        )
        if command.project_id != store.project_id:
            raise ToolDenied("creator operation belongs to another project")
        if authorize(command, context) is not True:
            raise ToolDenied("host denied the exact creator mutation")
        receipt = dispatch_creator_command(
            command, handlers={command.operation: handlers[command.operation]},
        )
        return receipt.to_dict()

    registry.register(ToolSpec(
        name="creator_execute_authorized",
        description=(
            "Execute host-reviewed original game-source create/edit/test/"
            "static preview or export with persistent source receipts"
        ),
        risk=RiskTier.HIGH_IMPACT, idempotent=False,
        arguments=(
            ArgumentRule("operation", "string",
                         choices=("create", "edit", "test", "preview", "export")),
            ArgumentRule("project_id", "string", max_length=128),
            ArgumentRule("payload", "object", max_length=32),
        ),
        timeout_seconds=30,
        produces_evidence=True,
    ), perform)
    return "creator_execute_authorized"


__all__ = ["CreatorProjectSourceStore", "CreatorSourceError", "register_creator_source_tool"]
