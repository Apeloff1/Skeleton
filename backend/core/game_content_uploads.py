"""Owner-scoped, streamed game media in the existing Mongo workspace.

Only immutable admitted chunks enter a private file-backed emulator bundle.
No client filesystem path, whole-disc JSON payload, or unreviewed URI is used.
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from datetime import timedelta
from pathlib import Path, PurePosixPath
from uuid import NAMESPACE_URL, uuid4, uuid5

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.databases import core_db
from core.game_learning import GameLearningError, _digest, _now, _time

CHUNK_BYTES = 1024 * 1024
MAX_FILE = 2 * 1024**3
MAX_BUNDLE = 4 * 1024**3
MAX_OWNER = 8 * 1024**3
MAX_FILES = 64
MAX_UPLOADS = 32
MAX_PRIVATE_BYTES = 8 * 1024**3
MAX_PRIVATE_BUNDLES = 256
LEASE_SECONDS = 300
UPLOAD_HOURS = 24


def _path(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or PurePosixPath(value).is_absolute()
        or str(PurePosixPath(value)) != value
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(character in value for character in ("\\", ":", "\x00"))
        or any(ord(character) < 32 for character in value)
        or ".cache.json" in PurePosixPath(value).parts
    ):
        raise GameLearningError("invalid_content_path", "Media paths must be unique relative paths.")
    return value


def _hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise GameLearningError("invalid_content_hash", "Content SHA-256 must be lowercase hexadecimal.")
    return value


class GameContentUploadAuthority:
    def __init__(self, database=core_db, workspace=None):
        self.database = database
        self.uploads = database["game_learning_content_uploads"]
        self.chunks = database["game_learning_content_chunks"]
        self.limits = database["game_learning_content_limits"]
        self._workspace = workspace
        self._indexed = False
        self._private_roots: dict[str, set[str]] = {}

    @property
    def workspace(self):
        if self._workspace is None:
            from core.game_learning import workspace

            return workspace
        return self._workspace

    async def ensure_indexes(self):
        if self._indexed:
            return
        await self.uploads.create_index(
            [("tenant_id", ASCENDING), ("owner_id", ASCENDING), ("expires_at", ASCENDING)]
        )
        await self.chunks.create_index(
            [("upload_id", ASCENDING), ("file_index", ASCENDING), ("chunk_index", ASCENDING)],
            unique=True,
        )
        self._indexed = True

    @staticmethod
    def _owner(scope):
        return str(uuid5(NAMESPACE_URL, "game-media:" + _digest(scope)))

    async def _read(self, scope, upload_id, *, allow_terminal=False):
        row = await self.uploads.find_one({"_id": upload_id, **scope})
        if row is None:
            raise GameLearningError("upload_not_found", "Media upload not found.", 404)
        if not allow_terminal and row["status"] in {"withdrawn", "expired"}:
            raise GameLearningError("upload_unavailable", "Media upload is no longer available.", 410)
        if row["status"] not in {"ready", "withdrawn", "expired"} and _time(row["expires_at"]) <= _now():
            await self._expire(scope, row)
            raise GameLearningError("upload_expired", "Media upload expired. Start a new upload.", 410)
        return row

    async def _release(self, scope, row):
        reservation = "reservations." + row["_id"]
        await self.limits.update_one(
            {"_id": self._owner(scope), **scope, reservation + ".bytes": row["total_bytes"]},
            {"$unset": {reservation: ""}, "$inc": {"reserved_bytes": -row["total_bytes"], "uploads": -1}},
        )

    async def _expire(self, scope, row):
        result = await self.uploads.update_one(
            {
                "_id": row["_id"],
                **scope,
                "status": {"$nin": ["ready", "withdrawn", "expired"]},
                "expires_at": {"$lte": _now()},
            },
            {
                "$set": {"status": "expired", "updated_at": _now()},
                "$unset": {"lease_token": "", "lease_until": ""},
            },
        )
        if result.modified_count:
            await self.chunks.delete_many({**scope, "upload_id": row["_id"]})
            await self._release(scope, row)

    async def _prune(self, scope):
        rows = (
            await self.uploads.find(
                {
                    **scope,
                    "status": {"$nin": ["ready", "withdrawn", "expired"]},
                    "expires_at": {"$lte": _now()},
                }
            )
            .limit(MAX_UPLOADS)
            .to_list(MAX_UPLOADS)
        )
        for row in rows:
            await self._expire(scope, row)
        # Reclaim a reservation whose process stopped before inserting its upload.
        limits = await self.limits.find_one({"_id": self._owner(scope), **scope})
        for upload_id, reservation in (limits or {}).get("reservations", {}).items():
            if _time(reservation["expires_at"]) > _now():
                continue
            if await self.uploads.find_one({"_id": upload_id, **scope}) is None:
                await self._release(scope, {"_id": upload_id, "total_bytes": reservation["bytes"]})

    async def _public(self, scope, row):
        received: dict[int, list[int]] = {}
        async for chunk in self.chunks.find(
            {**scope, "upload_id": row["_id"]}, {"file_index": 1, "chunk_index": 1}
        ):
            received.setdefault(chunk["file_index"], []).append(chunk["chunk_index"])
        files = []
        for index, item in enumerate(row["files"]):
            present = set(received.get(index, []))
            files.append(
                {
                    "path": item["path"],
                    "bytes": item["bytes"],
                    "sha256": item.get("sha256"),
                    "chunk_count": item["chunk_count"],
                    "received_chunks": sorted(present),
                    "missing_chunks": [value for value in range(item["chunk_count"]) if value not in present],
                }
            )
        return {
            "upload_id": row["_id"],
            "project_id": row["project_id"],
            "status": row["status"],
            "entrypoint": row["entrypoint"],
            "chunk_bytes": CHUNK_BYTES,
            "total_bytes": row["total_bytes"],
            "files": files,
            "expires_at": _time(row["expires_at"]).isoformat(),
            "source_id": row.get("source_id"),
            "content_digest": row.get("content_digest"),
        }

    async def create(self, scope, project_id, body):
        await self.ensure_indexes()
        await self._prune(scope)
        await self.workspace._project(project_id, scope)
        raw = body.get("files")
        if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_FILES:
            raise GameLearningError("content_file_limit", "Select between 1 and 64 media files.", 413)
        files, seen, total = [], set(), 0
        for item in raw:
            path = _path(item.get("path"))
            size = item.get("bytes")
            if path.casefold() in seen or type(size) is not int or not 1 <= size <= MAX_FILE:
                raise GameLearningError(
                    "content_file_limit", "Media files must be unique and at most 2 GiB.", 413
                )
            seen.add(path.casefold())
            total += size
            files.append(
                {
                    "path": path,
                    "bytes": size,
                    "sha256": _hash(item["sha256"]) if item.get("sha256") else None,
                    "chunk_count": (size + CHUNK_BYTES - 1) // CHUNK_BYTES,
                }
            )
        if total > MAX_BUNDLE:
            raise GameLearningError("content_bundle_limit", "A media bundle may contain at most 4 GiB.", 413)
        entrypoint = _path(body.get("entrypoint"))
        if entrypoint not in {item["path"] for item in files}:
            raise GameLearningError(
                "content_entrypoint_missing", "Choose an existing media file as the entrypoint."
            )
        refs = body.get("rights_refs")
        if (
            body.get("rights_acknowledged") is not True
            or not isinstance(refs, list)
            or not 1 <= len(refs) <= 64
            or any(not isinstance(ref, str) or not 1 <= len(ref) <= 512 or ref != ref.strip() for ref in refs)
        ):
            raise GameLearningError(
                "content_consent_required", "Acknowledge media rights and identify their source."
            )
        key = body.get("idempotency_key")
        if not isinstance(key, str) or not 1 <= len(key) <= 512 or key != key.strip():
            raise GameLearningError("invalid_idempotency", "A normalized upload key is required.")
        upload_id = str(uuid5(NAMESPACE_URL, "game-content:" + _digest(scope) + ":" + project_id + ":" + key))
        identity = {
            "files": files,
            "entrypoint": entrypoint,
            "rights_refs": refs,
            "expected_version": body["expected_version"],
        }
        request_digest = _digest(identity)
        previous = await self.uploads.find_one({"_id": upload_id, **scope})
        if previous:
            if previous["request_digest"] != request_digest:
                raise GameLearningError(
                    "idempotency_conflict", "Upload key already identifies different media.", 409
                )
            return await self._public(scope, await self._read(scope, upload_id))
        await self.workspace._project(project_id, scope, body["expected_version"])
        receipt = await self.workspace._admit(scope, "game-learning-content", upload_id, total)
        owner_id = self._owner(scope)
        try:
            await self.limits.update_one(
                {"_id": owner_id, **scope},
                {"$setOnInsert": {**scope, "reserved_bytes": 0, "uploads": 0, "reservations": {}}},
                upsert=True,
            )
        except DuplicateKeyError:
            pass
        reservation = "reservations." + upload_id
        reserved = await self.limits.find_one_and_update(
            {
                "_id": owner_id,
                **scope,
                reservation: {"$exists": False},
                "reserved_bytes": {"$lte": MAX_OWNER - total},
                "uploads": {"$lt": MAX_UPLOADS},
            },
            {
                "$set": {
                    reservation: {
                        "bytes": total,
                        "request_digest": request_digest,
                        "expires_at": _now() + timedelta(hours=UPLOAD_HOURS),
                    }
                },
                "$inc": {"reserved_bytes": total, "uploads": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if reserved is None:
            reserved = await self.limits.find_one(
                {
                    "_id": owner_id,
                    **scope,
                    reservation + ".bytes": total,
                    reservation + ".request_digest": request_digest,
                }
            )
            if reserved is None:
                raise GameLearningError(
                    "content_quota", "Media storage or upload slots are full. Withdraw unused uploads.", 429
                )
        row = {
            "_id": upload_id,
            **scope,
            "project_id": project_id,
            "request_digest": request_digest,
            "expected_version": body["expected_version"],
            "files": files,
            "entrypoint": entrypoint,
            "total_bytes": total,
            "rights_refs": refs,
            "rights_acknowledged": True,
            "status": "uploading",
            "storage_receipt": receipt,
            "created_at": _now(),
            "updated_at": _now(),
            "expires_at": _now() + timedelta(hours=UPLOAD_HOURS),
        }
        try:
            await self.uploads.insert_one(row)
        except DuplicateKeyError:
            row = await self._read(scope, upload_id)
            if row["request_digest"] != request_digest:
                raise GameLearningError("idempotency_conflict", "Upload key identifies different media.", 409)
        except Exception:
            # Keep the reservation when insertion outcome is uncertain; reclamation
            # only follows an authoritative read, never an assumed failed write.
            if await self.uploads.find_one({"_id": upload_id, **scope}) is None:
                await self._release(scope, row)
            raise
        return await self._public(scope, row)

    async def status(self, scope, upload_id):
        return await self._public(scope, await self._read(scope, upload_id, allow_terminal=True))

    async def put_chunk(self, scope, upload_id, file_index, chunk_index, data, declared_hash):
        row = await self._read(scope, upload_id)
        if row["status"] != "uploading":
            raise GameLearningError("upload_not_writable", "Media upload is not accepting chunks.", 409)
        await self.workspace._project(row["project_id"], scope, row["expected_version"])
        if type(file_index) is not int or not 0 <= file_index < len(row["files"]):
            raise GameLearningError("invalid_content_index", "Media file index is invalid.")
        file = row["files"][file_index]
        if type(chunk_index) is not int or not 0 <= chunk_index < file["chunk_count"]:
            raise GameLearningError("invalid_content_index", "Media chunk index is invalid.")
        expected_bytes = min(CHUNK_BYTES, file["bytes"] - chunk_index * CHUNK_BYTES)
        if type(data) is not bytes or len(data) != expected_bytes:
            raise GameLearningError(
                "content_chunk_size", "Chunk length does not match its exact file range.", 413
            )
        digest = hashlib.sha256(data).hexdigest()
        if _hash(declared_hash) != digest:
            raise GameLearningError("content_chunk_hash", "Chunk SHA-256 differs from its supplied bytes.")
        chunk_id = str(uuid5(NAMESPACE_URL, f"game-content-chunk:{upload_id}:{file_index}:{chunk_index}"))
        chunk = {
            "_id": chunk_id,
            **scope,
            "upload_id": upload_id,
            "file_index": file_index,
            "chunk_index": chunk_index,
            "bytes": len(data),
            "sha256": digest,
            "payload": data,
        }
        try:
            await self.chunks.insert_one(chunk)
        except DuplicateKeyError:
            previous = await self.chunks.find_one({"_id": chunk_id, **scope})
            if previous is None or previous["sha256"] != digest or previous["bytes"] != len(data):
                raise GameLearningError(
                    "content_chunk_conflict", "This chunk already contains different bytes.", 409
                )
        current = await self._read(scope, upload_id, allow_terminal=True)
        if current["status"] != "uploading":
            # Finalization may include the immutable same bytes. Withdrawal always
            # wins, including a chunk that arrived after the cleanup query.
            if current["status"] in {"withdrawn", "expired"}:
                await self.chunks.delete_many({**scope, "upload_id": upload_id})
            raise GameLearningError("upload_not_writable", "Upload changed while accepting the chunk.", 409)
        return await self._public(scope, current)

    async def _chunks(self, scope, row, file_index):
        file = row["files"][file_index]
        index = 0
        async for chunk in self.chunks.find(
            {**scope, "upload_id": row["_id"], "file_index": file_index}
        ).sort("chunk_index", ASCENDING):
            payload = bytes(chunk.get("payload", b""))
            expected = min(CHUNK_BYTES, file["bytes"] - index * CHUNK_BYTES)
            if (
                chunk["chunk_index"] != index
                or not 0 <= index < file["chunk_count"]
                or len(payload) != expected
                or chunk.get("bytes") != expected
                or hashlib.sha256(payload).hexdigest() != chunk.get("sha256")
            ):
                raise GameLearningError(
                    "content_corrupt", "Media chunks are missing, changed, or out of order.", 409
                )
            yield payload
            index += 1
        if index != file["chunk_count"]:
            raise GameLearningError(
                "content_incomplete", "Upload every media chunk before completing the bundle.", 409
            )

    async def complete(self, scope, upload_id):
        from skeleton.jeeves.game_emulator_catalog import GameContentBundle, GameContentReference

        row = await self._read(scope, upload_id)
        if row["status"] == "ready":
            await self.assert_authority(scope, row["project_id"], upload_id, row["content_digest"])
            return {
                "upload": await self._public(scope, row),
                "project": await self.workspace.get_project(scope, row["project_id"]),
                "source": {
                    "source_id": row["source_id"],
                    "kind": "content_bundle",
                    "state": "active",
                    "content_digest": row["content_digest"],
                },
            }
        token = str(uuid4())
        row = await self.uploads.find_one_and_update(
            {
                "_id": upload_id,
                **scope,
                "status": {"$in": ["uploading", "finalizing"]},
                "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lte": _now()}}],
            },
            {
                "$set": {
                    "status": "finalizing",
                    "lease_token": token,
                    "lease_until": _now() + timedelta(seconds=LEASE_SECONDS),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if row is None:
            raise GameLearningError("upload_finalizing", "This media bundle is already being completed.", 409)
        try:
            references, actual_files = {}, []
            for index, file in enumerate(row["files"]):
                descriptor = PurePosixPath(file["path"]).suffix.lower() in {".cue", ".gdi", ".m3u", ".ccd"}
                if descriptor and file["bytes"] > 65536:
                    raise GameLearningError(
                        "disc_descriptor_limit", "Disc descriptor text exceeds 64 KiB.", 413
                    )
                digest, prefix = hashlib.sha256(), bytearray()
                async for chunk in self._chunks(scope, row, index):
                    digest.update(chunk)
                    if descriptor:
                        maximum = 65536
                    elif PurePosixPath(file["path"]).suffix.lower() == ".iso":
                        maximum = 17 * 2048
                    else:
                        maximum = 2048
                    if len(prefix) < maximum:
                        prefix.extend(chunk[: maximum - len(prefix)])
                actual = digest.hexdigest()
                if file.get("sha256") and file["sha256"] != actual:
                    raise GameLearningError(
                        "content_file_hash", "Media file SHA-256 differs from the declared value."
                    )
                artifact = f"game-content:{upload_id}:{index}"
                references[file["path"]] = GameContentReference(
                    file["path"], file["bytes"], actual, artifact, bytes(prefix)
                )
                actual_files.append(
                    {
                        "path": file["path"],
                        "bytes": file["bytes"],
                        "sha256": actual,
                        "artifact_ref": artifact,
                        "prefix_hex": bytes(prefix).hex(),
                    }
                )
                heartbeat = await self.uploads.update_one(
                    {"_id": upload_id, **scope, "status": "finalizing", "lease_token": token},
                    {"$set": {"lease_until": _now() + timedelta(seconds=LEASE_SECONDS)}},
                )
                if not heartbeat.modified_count:
                    raise GameLearningError("upload_lease_lost", "Upload changed while verifying media.", 409)
            source_digest = _digest(
                {
                    "entrypoint": row["entrypoint"],
                    "files": [
                        {"path": f["path"], "bytes": f["bytes"], "sha256": f["sha256"]} for f in actual_files
                    ],
                }
            )
            bundle = GameContentBundle(row["entrypoint"], references, source_digest)
            manifest = {
                "bundle_id": upload_id,
                "entrypoint": row["entrypoint"],
                "content_digest": bundle.bundle_digest,
                "byte_length": row["total_bytes"],
                "total_bytes": row["total_bytes"],
                "files": actual_files,
                "descriptor": bundle.as_dict(),
                "rights_refs": row["rights_refs"],
                "rights_acknowledged": True,
            }
            source_id = str(
                uuid5(NAMESPACE_URL, "game-content-source:" + row["project_id"] + ":" + upload_id)
            )
            prepared = await self.uploads.update_one(
                {"_id": upload_id, **scope, "status": "finalizing", "lease_token": token},
                {
                    "$set": {
                        "manifest": manifest,
                        "source_id": source_id,
                        "content_digest": bundle.bundle_digest,
                    }
                },
            )
            if not prepared.modified_count:
                raise GameLearningError(
                    "upload_lease_lost", "Upload changed while preparing the source.", 409
                )
            project, source = await self.workspace.register_content_source(
                scope, row["project_id"], manifest, source_id, row["expected_version"]
            )
            result = await self.uploads.update_one(
                {"_id": upload_id, **scope, "status": "finalizing", "lease_token": token},
                {
                    "$set": {"status": "ready", "updated_at": _now()},
                    "$unset": {"lease_token": "", "lease_until": ""},
                },
            )
            if not result.modified_count:
                await self.workspace.sources.update_one(
                    {"_id": source_id, **scope},
                    {
                        "$set": {"state": "revoked", "rights_acknowledged": False},
                        "$inc": {"authority_epoch": 1},
                    },
                )
                raise GameLearningError(
                    "upload_lease_lost", "Media authority changed during publication.", 409
                )
            return {"upload": await self.status(scope, upload_id), "project": project, "source": source}
        except Exception:
            await self.uploads.update_one(
                {"_id": upload_id, **scope, "lease_token": token, "status": "finalizing"},
                {"$set": {"status": "uploading"}, "$unset": {"lease_token": "", "lease_until": ""}},
            )
            raise

    async def assert_authority(self, scope, project_id, bundle_id, expected_digest):
        row = await self._read(scope, bundle_id)
        project = await self.workspace._project(project_id, scope)
        source = await self.workspace.sources.find_one(
            {
                "_id": row.get("source_id"),
                **scope,
                "project_id": project_id,
                "kind": "content_bundle",
                "state": "active",
            }
        )
        from skeleton.jeeves.game_emulator_catalog import GameContentBundle

        manifest = row.get("manifest", {})
        validated = GameContentBundle.from_descriptor(manifest.get("descriptor"))
        if (
            row["project_id"] != project_id
            or row["status"] != "ready"
            or row.get("content_digest") != expected_digest
            or validated.bundle_digest != expected_digest
            or manifest.get("bundle_id") != bundle_id
            or source is None
            or row.get("source_id") not in project["source_ids"]
            or source.get("rights_acknowledged") is not True
            or not source.get("rights_refs")
            or row.get("rights_acknowledged") is not True
            or not row.get("rights_refs")
            or source.get("bundle_id") != bundle_id
            or source.get("source_digest") != expected_digest
            or source.get("bundle", {}).get("bundle_digest") != expected_digest
            or source.get("content_manifest") != manifest
            or source.get("rights_refs") != row.get("rights_refs")
            or manifest.get("rights_refs") != row.get("rights_refs")
            or source.get("byte_length") != row.get("total_bytes")
        ):
            raise GameLearningError(
                "content_authority_unavailable",
                "This media bundle no longer has current source authority.",
                409,
            )
        return row

    def _cache_base(self):
        base = Path(tempfile.gettempdir()) / ("skeleton-game-content-cache-" + str(os.getuid()))
        base.mkdir(mode=0o700, exist_ok=True)
        info = base.lstat()
        if base.is_symlink() or not base.is_dir() or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise GameLearningError(
                "content_cache_unavailable", "Private content cache permissions are invalid.", 503
            )
        return base

    async def _cache_lock(self):
        base = self._cache_base()
        handle = os.open(base / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        deadline = time.monotonic() + 120
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return base, handle
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(handle)
                    raise GameLearningError(
                        "content_cache_busy", "Another media materialization is active; retry shortly.", 503
                    )
                try:
                    await asyncio.sleep(0.05)
                except BaseException:
                    os.close(handle)
                    raise

    @staticmethod
    def _cache_key(scope, bundle_id, digest):
        return _digest({**scope, "bundle_id": bundle_id, "content_digest": digest})

    def _cache_usage(self, base):
        total, count = 0, 0
        for directory in base.iterdir():
            if directory.name == ".lock":
                continue
            count += 1
            if count > MAX_PRIVATE_BUNDLES:
                raise GameLearningError("content_cache_limit", "Private media cache count is exhausted.", 413)
            if directory.is_symlink() or not directory.is_dir():
                raise GameLearningError(
                    "content_cache_corrupt", "Private media cache has an invalid entry.", 503
                )
            marker = directory / ".cache.json"
            try:
                if marker.is_symlink() or marker.stat().st_size > 131072:
                    raise ValueError("invalid cache marker")
                entry = json.loads(marker.read_text())
                if entry.get("status") != "ready":
                    # The global OS lock is held. A preparing entry therefore
                    # belongs to a worker that stopped and cannot still write.
                    shutil.rmtree(directory)
                    continue
                size = entry["bytes"]
                if type(size) is not int or not 0 < size <= MAX_BUNDLE:
                    raise ValueError("invalid cache size")
                media = directory / "media"
                if (
                    not media.is_dir()
                    or media.is_symlink()
                    or media.stat().st_mode & 0o077
                    or set(path.name for path in directory.iterdir()) != {"media", ".cache.json"}
                ):
                    raise ValueError("invalid cache media root")
                expected = {file["path"]: file["bytes"] for file in entry["files"]}
                if len(expected) != len(entry["files"]):
                    raise ValueError("duplicate cached file")
                observed = {}
                entries = 0
                for parent, directories, files in os.walk(media, followlinks=False):
                    entries += len(directories) + len(files)
                    if entries > 192:
                        raise ValueError("cache inventory exceeds capacity")
                    for name in directories + files:
                        path = Path(parent) / name
                        if path.is_symlink():
                            raise ValueError("unsafe cache inventory")
                        if name in files:
                            if not path.is_file():
                                raise ValueError("nonregular cached file")
                            observed[path.relative_to(media).as_posix()] = path.stat().st_size
                if observed != expected or sum(observed.values()) != size:
                    raise ValueError("cache inventory or byte count differs")
                total += size
            except (OSError, ValueError, KeyError, TypeError):
                shutil.rmtree(directory)
        return total, count

    async def materialize(self, scope, project_id, bundle_id):
        from skeleton.jeeves.game_emulator_catalog import GameContentBundle

        row = await self._read(scope, bundle_id)
        row = await self.assert_authority(scope, project_id, bundle_id, row.get("content_digest"))
        bundle = GameContentBundle.from_descriptor(row["manifest"]["descriptor"])
        base, lock = await self._cache_lock()
        root = base / self._cache_key(scope, bundle_id, row["content_digest"])
        media = root / "media"
        created = False
        try:
            await self.assert_authority(scope, project_id, bundle_id, row["content_digest"])
            total, _ = await asyncio.to_thread(self._cache_usage, base)
            marker = root / ".cache.json"
            if root.exists():
                cached = json.loads(marker.read_text())
                expected = {
                    "bundle_id": bundle_id,
                    "content_digest": row["content_digest"],
                    "bytes": row["total_bytes"],
                    "files": row["manifest"]["files"],
                    "status": "ready",
                }
                if cached != expected:
                    raise GameLearningError(
                        "content_cache_corrupt", "Private media cache identity differs.", 503
                    )
                for file in cached["files"]:
                    target = media.joinpath(*PurePosixPath(file["path"]).parts)
                    if (
                        target.is_symlink()
                        or target.resolve(strict=True) != target
                        or not target.is_file()
                        or target.stat().st_size != file["bytes"]
                    ):
                        raise GameLearningError(
                            "content_cache_corrupt", "Private media cache file geometry differs.", 503
                        )

                    def verify(path=target, expected_digest=file["sha256"]):
                        digest = hashlib.sha256()
                        with path.open("rb") as handle:
                            for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
                                digest.update(chunk)
                        return digest.hexdigest() == expected_digest

                    if not await asyncio.to_thread(verify):
                        raise GameLearningError(
                            "content_cache_corrupt", "Private media cache bytes differ.", 503
                        )
                await self.assert_authority(scope, project_id, bundle_id, row["content_digest"])
                return {
                    "root": str(media),
                    "entrypoint": bundle.entrypoint,
                    "files": cached["files"],
                    "content_digest": row["content_digest"],
                    "bundle_id": bundle_id,
                }
            if total + row["total_bytes"] > MAX_PRIVATE_BYTES:
                raise GameLearningError(
                    "content_cache_limit", "The shared private media cache byte budget is exhausted.", 413
                )
            root.mkdir(mode=0o700)
            created = True
            media.mkdir(mode=0o700)
            marker.write_text(json.dumps({"status": "preparing", "bytes": row["total_bytes"]}))
            os.chmod(marker, 0o600)
            for index, file in enumerate(row["manifest"]["files"]):
                await self.assert_authority(scope, project_id, bundle_id, row["content_digest"])
                target = media.joinpath(*PurePosixPath(file["path"]).parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                handle = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                digest, count = hashlib.sha256(), 0
                try:
                    async for chunk in self._chunks(scope, row, index):
                        digest.update(chunk)
                        count += len(chunk)

                        # Buffered data is never larger than one admitted chunk.
                        def write_chunk(data=chunk, fd=handle):
                            view = memoryview(data)
                            while view:
                                written = os.write(fd, view)
                                if written <= 0:
                                    raise OSError("private media write made no progress")
                                view = view[written:]

                        writing = asyncio.create_task(asyncio.to_thread(write_chunk))
                        try:
                            await asyncio.shield(writing)
                        except asyncio.CancelledError:
                            # The descriptor must remain owned until its actual
                            # write stops; otherwise a reused fd could be hit.
                            await asyncio.shield(writing)
                            raise
                finally:
                    os.close(handle)
                if count != file["bytes"] or digest.hexdigest() != file["sha256"]:
                    raise GameLearningError(
                        "content_corrupt", "Private media materialization differs from its source.", 409
                    )
                os.chmod(target, 0o400)
            await self.assert_authority(scope, project_id, bundle_id, row["content_digest"])
            marker.write_text(
                json.dumps(
                    {
                        "bundle_id": bundle_id,
                        "content_digest": row["content_digest"],
                        "bytes": row["total_bytes"],
                        "files": row["manifest"]["files"],
                        "status": "ready",
                    }
                )
            )
            self._private_roots.setdefault(bundle_id, set()).add(str(root))
            return {
                "root": str(media),
                "entrypoint": bundle.entrypoint,
                "files": [
                    {"path": f["path"], "bytes": f["bytes"], "sha256": f["sha256"]}
                    for f in row["manifest"]["files"]
                ],
                "content_digest": row["content_digest"],
                "bundle_id": bundle_id,
            }
        except BaseException:
            if created:
                await asyncio.to_thread(shutil.rmtree, root, True)
            raise
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)

    async def withdraw_source(self, scope, source_id):
        row = await self.uploads.find_one({**scope, "source_id": source_id})
        if row:
            await self._withdraw_storage(scope, row)

    async def _withdraw_storage(self, scope, row):
        await self.uploads.update_one(
            {"_id": row["_id"], **scope},
            {
                "$set": {"status": "withdrawn", "rights_acknowledged": False, "updated_at": _now()},
                "$unset": {"lease_token": "", "lease_until": ""},
            },
        )
        await self.chunks.delete_many({**scope, "upload_id": row["_id"]})
        await self._release(scope, row)
        base, lock = await self._cache_lock()
        try:
            roots = self._private_roots.pop(row["_id"], set())
            if row.get("content_digest"):
                roots.add(str(base / self._cache_key(scope, row["_id"], row["content_digest"])))
            for root in roots:
                await asyncio.to_thread(shutil.rmtree, root, True)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
            os.close(lock)

    async def withdraw(self, scope, upload_id):
        row = await self._read(scope, upload_id, allow_terminal=True)
        if row.get("source_id"):
            project = await self.workspace._project(row["project_id"], scope)
            if row["source_id"] in project["source_ids"]:
                await self.workspace.revoke_source(
                    scope, row["project_id"], row["source_id"], project["version"]
                )
        await self._withdraw_storage(scope, row)
        return await self.status(scope, upload_id)


content_uploads = GameContentUploadAuthority()


async def materialize_content(scope, project_id, bundle_id):
    return await content_uploads.materialize(scope, project_id, bundle_id)


async def assert_content_authority(scope, project_id, bundle_id, expected_digest):
    return await content_uploads.assert_authority(scope, project_id, bundle_id, expected_digest)
