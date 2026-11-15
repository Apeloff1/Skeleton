#!/usr/bin/env python3
"""Format-2 owner-bound encrypted package delivery in one atomic Mongo record.

Historical unowned records remain untouched and inaccessible through the v2
delivery interface pending an explicit owner/provenance migration.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import math
import os
import re
import secrets
import threading
import time
from typing import Dict, List, Optional

from bson import BSON
from cryptography.fernet import Fernet, InvalidToken
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from gameforge.workflow.delivery_scope import DeliveryScope, current_scope

_DEFAULT_TTL = 30 * 24 * 3600
_DEFAULT_MAX_DOWNLOADS = 1000
_MAX_BYTES = 8 * 1024 * 1024
_MAX_DOWNLOADS = 100_000
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,159}", re.ASCII)
_PACKAGE_ID = re.compile(r"[0-9a-f]{32}", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,128}", re.ASCII)

def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()

class JeevesVault:
    def __init__(self):
        self._fernet: Fernet | None = None
        self._key_lock = threading.Lock()

    def _db(self):
        from core.databases import get_sync_db
        return get_sync_db()

    def _col(self):
        # Durable custody cannot silently fall back to process-local memory.
        return self._db()["jeeves_vault"]

    def _cipher(self) -> Fernet:
        with self._key_lock:
            if self._fernet is None:
                configured = os.environ.get("JEEVES_DELIVERY_KEY")
                if configured is not None:
                    key = configured.encode("ascii")
                else:
                    meta = self._db()["jeeves_delivery_meta"]
                    generated = Fernet.generate_key().decode("ascii")
                    try:
                        doc = meta.find_one_and_update(
                            {"_id": "fernet_key"}, {"$setOnInsert": {"key": generated}},
                            upsert=True, return_document=ReturnDocument.AFTER,
                        )
                    except DuplicateKeyError:
                        doc = meta.find_one({"_id": "fernet_key"})
                    if not doc or not isinstance(doc.get("key"), str):
                        raise RuntimeError("delivery key unavailable")
                    key = doc["key"].encode("ascii")
                self._fernet = Fernet(key)
            return self._fernet

    @staticmethod
    def _owned(scope: DeliveryScope | None = None) -> dict:
        return {"format": 2, "scope_key": (scope or current_scope()).key}

    @staticmethod
    def _record_id(package_id: str) -> dict:
        if not isinstance(package_id, str) or not _PACKAGE_ID.fullmatch(package_id):
            raise ValueError("invalid package identity")
        return {"_id": package_id, "format": 2}

    def register(self, project_name: str, package_name: str, package_bytes: bytes, *,
                 quality: float = 0.0, architectures: Optional[List[str]] = None,
                 signature: Optional[Dict] = None, metadata: Optional[Dict] = None,
                 ttl_seconds: int = _DEFAULT_TTL, max_downloads: int = _DEFAULT_MAX_DOWNLOADS) -> Dict:
        if not isinstance(project_name, str) or not 1 <= len(project_name) <= 120:
            raise ValueError("invalid project name")
        if not isinstance(package_name, str) or not _NAME.fullmatch(package_name):
            raise ValueError("invalid package filename")
        if type(package_bytes) is not bytes or not 1 <= len(package_bytes) <= _MAX_BYTES:
            raise ValueError("package exceeds delivery byte budget")
        if type(quality) not in (int, float) or not math.isfinite(quality) or not 0 <= quality <= 1:
            raise ValueError("invalid quality score")
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= _DEFAULT_TTL:
            raise ValueError("invalid package lifetime")
        if type(max_downloads) is not int or not 1 <= max_downloads <= _MAX_DOWNLOADS:
            raise ValueError("invalid download quota")
        architectures = list(architectures or [])
        if len(architectures) > 16 or any(not isinstance(a, str) or len(a) > 64 for a in architectures):
            raise ValueError("invalid architecture metadata")
        if (signature is not None and not isinstance(signature, dict)) or (metadata is not None and not isinstance(metadata, dict)):
            raise ValueError("invalid package metadata")
        if len(BSON.encode({"metadata": metadata or {}, "signature": signature or {}})) > 64 * 1024:
            raise ValueError("package metadata exceeds budget")
        digest = hashlib.sha256(package_bytes).hexdigest()
        if signature and signature.get("digest") not in (None, digest):
            raise ValueError("package descriptor digest mismatch")
        package_id, token = secrets.token_hex(16), secrets.token_urlsafe(32)
        now = time.time()
        doc = {
            "_id": package_id, "package_id": package_id, **self._owned(),
            "project_name": project_name, "package_name": package_name,
            "enc_content": self._cipher().encrypt(package_bytes),
            "size_bytes": len(package_bytes), "sha256": digest,
            "quality": round(float(quality), 4), "architectures": architectures,
            "signature": signature or {}, "metadata": metadata or {},
            "token_sha256": _token_digest(token),
            "download_path": f"/api/gameforge/workflow/vault/{package_id}/download",
            "download_count": 0, "max_downloads": max_downloads,
            "created_at": now, "expires_at": now + ttl_seconds, "revoked": False,
        }
        self._col().insert_one(doc)
        return {**self._public(doc), "download_token": token}

    def get_download(self, package_id: str, token: Optional[str] = None, *,
                     scope: DeliveryScope | None = None) -> Dict:
        try:
            selector = self._record_id(package_id)
        except ValueError:
            return {"ok": False, "error": "package_unavailable"}
        if token is not None:
            if not isinstance(token, str) or not _TOKEN.fullmatch(token):
                return {"ok": False, "error": "package_unavailable"}
            selector["token_sha256"] = _token_digest(token)
        elif scope is not None:
            selector["scope_key"] = scope.key
        else:
            return {"ok": False, "error": "package_unavailable"}
        selector.update({"revoked": False, "expires_at": {"$gt": time.time()}})
        col = self._col()
        doc = col.find_one(selector)
        if not doc:
            return {"ok": False, "error": "package_unavailable"}
        maximum, count, size = doc.get("max_downloads"), doc.get("download_count"), doc.get("size_bytes")
        if (type(maximum) is not int or not 1 <= maximum <= _MAX_DOWNLOADS
                or type(count) is not int or not 0 <= count < maximum):
            return {"ok": False, "error": "download_limit_reached"}
        if type(size) is not int or not 1 <= size <= _MAX_BYTES:
            return {"ok": False, "error": "package_integrity_failed"}
        encrypted = doc.get("enc_content")
        if not isinstance(encrypted, bytes) or len(encrypted) > 12 * 1024 * 1024:
            return {"ok": False, "error": "package_integrity_failed"}
        try:
            content = self._cipher().decrypt(encrypted)
        except (InvalidToken, ValueError, TypeError):
            return {"ok": False, "error": "package_integrity_failed"}
        if len(content) != size or not isinstance(doc.get("sha256"), str) or not hmac.compare_digest(
                hashlib.sha256(content).hexdigest(), doc["sha256"]):
            return {"ok": False, "error": "package_integrity_failed"}
        # Atomic count predicate and fresh expiry/credential/revocation check.
        claim = {**selector, "expires_at": {"$gt": time.time()}, "max_downloads": maximum,
                 "download_count": {"$lt": maximum, "$gte": 0}, "sha256": doc["sha256"]}
        if col.update_one(claim, {"$inc": {"download_count": 1}}).modified_count != 1:
            return {"ok": False, "error": "package_unavailable"}
        return {"ok": True, "package_id": package_id, "package_name": doc["package_name"],
                "project_name": doc["project_name"], "size_bytes": size, "sha256": doc["sha256"],
                "signature": doc.get("signature", {}), "architectures": doc.get("architectures", []),
                "content_base64": base64.b64encode(content).decode("ascii"),
                "install_instructions": self._install_instructions(doc)}

    def _install_instructions(self, doc: Dict) -> List[str]:
        return [f"Download {doc['package_name']} to your device.",
                f"Verify full SHA-256: {doc['sha256']}",
                "Extract only after integrity verification; review the README.",
                "Run only in a trusted isolated local environment."]

    def delivery_link(self, package: Dict, base_url: str = "") -> Dict:
        path = package.get("download_path", "")
        url = f"{base_url.rstrip('/')}{path}" if base_url else path
        return {"download_link": url, "download_path": path,
                "token": package.get("download_token", ""), "token_header": "X-Jeeves-Download-Token",
                "qr_payload": url, "expires_at": package.get("expires_at")}

    @staticmethod
    def _projection() -> dict:
        return {"_id": 0, "enc_content": 0, "token_sha256": 0, "scope_key": 0}

    def list_packages(self, project_name: Optional[str] = None, limit: int = 50) -> List[Dict]:
        q = self._owned()
        if project_name:
            q["project_name"] = project_name
        rows = self._col().find(q, self._projection()).sort("created_at", -1).limit(max(1, min(int(limit), 200)))
        return [self._public(row) for row in rows]

    def search(self, query: str, limit: int = 50) -> List[Dict]:
        if not isinstance(query, str) or not 1 <= len(query) <= 256:
            raise ValueError("invalid search query")
        q = {**self._owned(), "$or": [
            {"project_name": {"$regex": re.escape(query), "$options": "i"}},
            {"package_name": {"$regex": re.escape(query), "$options": "i"}}]}
        rows = self._col().find(q, self._projection()).sort("created_at", -1).limit(max(1, min(int(limit), 200)))
        return [self._public(row) for row in rows]

    def get(self, package_id: str) -> Optional[Dict]:
        try:
            query = {**self._record_id(package_id), **self._owned()}
        except ValueError:
            return None
        doc = self._col().find_one(query, self._projection())
        return self._public(doc) if doc else None

    def delete(self, package_id: str) -> bool:
        try:
            q = {**self._record_id(package_id), **self._owned()}
        except ValueError:
            return False
        return self._col().delete_one(q).deleted_count == 1

    def revoke(self, package_id: str) -> bool:
        try:
            q = {**self._record_id(package_id), **self._owned()}
        except ValueError:
            return False
        return self._col().update_one(q, {"$set": {"revoked": True}}).matched_count == 1

    def rotate_token(self, package_id: str) -> Optional[str]:
        try:
            q = {**self._record_id(package_id), **self._owned(),
                 "revoked": False, "expires_at": {"$gt": time.time()}}
        except ValueError:
            return None
        token = secrets.token_urlsafe(32)
        if self._col().update_one(q, {"$set": {"token_sha256": _token_digest(token)}}).matched_count == 1:
            return token
        return None

    def cleanup_expired(self) -> int:
        return self._col().delete_many({**self._owned(), "expires_at": {"$lte": time.time()}}).deleted_count

    def stats(self) -> Dict:
        rows = list(self._col().aggregate([
            {"$match": self._owned()},
            {"$group": {"_id": None, "total_packages": {"$sum": 1},
                        "total_downloads": {"$sum": "$download_count"}, "total_bytes": {"$sum": "$size_bytes"},
                        "avg_quality": {"$avg": "$quality"},
                        "expired": {"$sum": {"$cond": [{"$lte": ["$expires_at", time.time()]}, 1, 0]}}}},
        ]))
        summary = rows[0] if rows else {}
        return {"total_packages": summary.get("total_packages", 0), "total_downloads": summary.get("total_downloads", 0),
                "total_bytes": summary.get("total_bytes", 0), "avg_quality": round(summary.get("avg_quality", 0), 4),
                "expired": summary.get("expired", 0), "custody_format": 2}

    def export(self) -> List[Dict]:
        return self.list_packages(limit=200)

    @staticmethod
    def _public(doc: Dict) -> Dict:
        keys = ["package_id", "project_name", "package_name", "size_bytes", "sha256",
                "quality", "architectures", "signature", "metadata", "download_path",
                "download_count", "max_downloads", "created_at", "expires_at", "revoked"]
        return {key: doc.get(key) for key in keys}

jeeves_vault = JeevesVault()
