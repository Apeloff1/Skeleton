#!/usr/bin/env python3
"""
JeevesVault — package delivery vault (Cowabunga v4 adaptation).

Full package lifecycle: registration, secure download tokens + limits,
download tracking, search, expiry cleanup, delete, stats, export. The actual
package BYTES are stored (encrypted + versioned) in the persistent
boardroom_vault; JeevesVault owns the registry/metadata + delivery in Mongo so
everything survives restarts and forks.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import Any, Dict, List, Optional

from gameforge.boardroom.persistent_vault import boardroom_vault

_DEFAULT_TTL = 30 * 24 * 3600          # 30 days
_DEFAULT_MAX_DOWNLOADS = 1000


class JeevesVault:
    def __init__(self):
        pass

    def _db(self):
        from core.databases import get_sync_db
        return get_sync_db()

    def _col(self):
        return self._db()["jeeves_vault"]

    # ── registration ──────────────────────────────────────────────────
    def register(
        self,
        project_name: str,
        package_name: str,
        package_bytes: bytes,
        *,
        quality: float = 0.0,
        architectures: Optional[List[str]] = None,
        signature: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
        ttl_seconds: int = _DEFAULT_TTL,
        max_downloads: int = _DEFAULT_MAX_DOWNLOADS,
    ) -> Dict:
        """Store the package in the encrypted vault + register a delivery record."""
        vault_entry = boardroom_vault.put_file(
            package_name, package_bytes,
            metadata={"kind": "jeeves_package", "project": project_name},
        )
        package_id = secrets.token_hex(8)
        token = secrets.token_urlsafe(24)
        now = time.time()
        doc = {
            "package_id": package_id,
            "project_name": project_name,
            "package_name": package_name,
            "vault_file_id": vault_entry.file_id,
            "vault_version": vault_entry.version,
            "size_bytes": len(package_bytes),
            "sha256": hashlib.sha256(package_bytes).hexdigest(),
            "quality": round(float(quality), 4),
            "architectures": architectures or ["arm64", "x86_64", "universal"],
            "signature": signature or {},
            "metadata": metadata or {},
            "download_token": token,
            "download_path": f"/api/gameforge/workflow/vault/{package_id}/download",
            "download_count": 0,
            "max_downloads": max_downloads,
            "created_at": now,
            "expires_at": now + ttl_seconds,
            "revoked": False,
        }
        self._col().update_one({"package_id": package_id}, {"$set": doc}, upsert=True)
        return self._public(doc, include_token=True)

    # ── delivery ──────────────────────────────────────────────────────
    def get_download(self, package_id: str, token: Optional[str] = None) -> Dict:
        """Validate + return package bytes (base64) with install instructions."""
        doc = self._col().find_one({"package_id": package_id})
        if not doc:
            return {"ok": False, "error": "package_not_found"}
        if doc.get("revoked"):
            return {"ok": False, "error": "package_revoked"}
        if time.time() > doc.get("expires_at", 0):
            return {"ok": False, "error": "package_expired"}
        if doc.get("download_count", 0) >= doc.get("max_downloads", _DEFAULT_MAX_DOWNLOADS):
            return {"ok": False, "error": "download_limit_reached"}
        # Token is optional (link already carries package_id) but validated when supplied.
        if token is not None and token != doc.get("download_token"):
            return {"ok": False, "error": "invalid_token"}

        content = boardroom_vault.get_file(doc["vault_file_id"], doc["vault_version"])
        if content is None:
            return {"ok": False, "error": "package_bytes_missing"}

        self._col().update_one({"package_id": package_id}, {"$inc": {"download_count": 1}})
        return {
            "ok": True,
            "package_id": package_id,
            "package_name": doc["package_name"],
            "project_name": doc["project_name"],
            "size_bytes": doc["size_bytes"],
            "sha256": doc["sha256"],
            "signature": doc.get("signature", {}),
            "architectures": doc.get("architectures", []),
            "content_base64": base64.b64encode(content).decode(),
            "install_instructions": self._install_instructions(doc),
        }

    def _install_instructions(self, doc: Dict) -> List[str]:
        return [
            f"1. Download {doc['package_name']} to your device.",
            "2. Unzip the package (it is a self-contained bundle).",
            f"3. Verify integrity — sha256 should equal {doc['sha256'][:16]}…",
            "4. Run: python internal_runtime.py game_manifest.json",
            f"5. Supported architectures: {', '.join(doc.get('architectures', []))}.",
        ]

    def delivery_link(self, package: Dict, base_url: str = "") -> Dict:
        """Build a shareable delivery link + QR payload for the frontend."""
        path = package.get("download_path", "")
        token = package.get("download_token", "")
        url = f"{base_url.rstrip('/')}{path}?token={token}" if base_url else f"{path}?token={token}"
        return {
            "download_link": url,
            "download_path": path,
            "token": token,
            "qr_payload": url,
            "expires_at": package.get("expires_at"),
        }

    # ── management ────────────────────────────────────────────────────
    def list_packages(self, project_name: Optional[str] = None, limit: int = 50) -> List[Dict]:
        q: Dict = {}
        if project_name:
            q["project_name"] = project_name
        docs = self._col().find(q).sort("created_at", -1).limit(int(limit))
        return [self._public(d) for d in docs]

    def search(self, query: str, limit: int = 50) -> List[Dict]:
        q = (query or "").lower()
        out = []
        for d in self._col().find().sort("created_at", -1).limit(500):
            hay = f"{d.get('project_name','')} {d.get('package_name','')}".lower()
            if q in hay:
                out.append(self._public(d))
            if len(out) >= limit:
                break
        return out

    def get(self, package_id: str) -> Optional[Dict]:
        d = self._col().find_one({"package_id": package_id})
        return self._public(d) if d else None

    def delete(self, package_id: str) -> bool:
        return self._col().delete_one({"package_id": package_id}).deleted_count > 0

    def revoke(self, package_id: str) -> bool:
        return self._col().update_one(
            {"package_id": package_id}, {"$set": {"revoked": True}}
        ).modified_count > 0

    def cleanup_expired(self) -> int:
        return self._col().delete_many({"expires_at": {"$lt": time.time()}}).deleted_count

    def stats(self) -> Dict:
        col = self._col()
        docs = list(col.find({}, {"_id": 0, "size_bytes": 1, "download_count": 1, "quality": 1}))
        total = len(docs)
        return {
            "total_packages": total,
            "total_downloads": sum(d.get("download_count", 0) for d in docs),
            "total_bytes": sum(d.get("size_bytes", 0) for d in docs),
            "avg_quality": round(sum(d.get("quality", 0) for d in docs) / total, 4) if total else 0.0,
            "expired": col.count_documents({"expires_at": {"$lt": time.time()}}),
        }

    def export(self) -> List[Dict]:
        return [self._public(d) for d in self._col().find().sort("created_at", -1)]

    # ── helpers ───────────────────────────────────────────────────────
    def _public(self, doc: Dict, include_token: bool = False) -> Dict:
        if not doc:
            return {}
        keys = [
            "package_id", "project_name", "package_name", "size_bytes", "sha256",
            "quality", "architectures", "signature", "metadata", "download_path",
            "download_count", "max_downloads", "created_at", "expires_at", "revoked",
        ]
        out = {k: doc.get(k) for k in keys}
        if include_token:
            out["download_token"] = doc.get("download_token")
        return out


jeeves_vault = JeevesVault()
