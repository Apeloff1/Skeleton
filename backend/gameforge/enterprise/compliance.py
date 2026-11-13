from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.vault_secure_fs import anchored_directory, atomic_write, ensure_directory
from gameforge.enterprise.access_review import AccessReviewService
from gameforge.enterprise.alerts import METRICS
from gameforge.enterprise.audit import AUDIT
from gameforge.enterprise.oidc_config import load_oidc_settings
from gameforge.enterprise.quotas import QUOTAS


def _data_dir() -> Path:
    p = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
    return ensure_directory(p)


def _seal_compliance_export(plaintext: bytes, tenant_token: str) -> bytes:
    """Authenticated encryption of tenant exports; never persist plaintext.

    The key is injected by the operator from a secret manager. A missing key
    stops export instead of writing a sensitive unencrypted compliance pack.
    The nonce is unique per export; tenant binding prevents cross-tenant swaps.
    """
    raw = os.getenv("GAMEFORGE_COMPLIANCE_EXPORT_KEY_B64", "")
    try:
        key = base64.b64decode(raw, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid compliance export encryption configuration") from exc
    if len(key) != 32:
        raise ValueError("compliance export requires a 256-bit AES-GCM key")
    if not isinstance(tenant_token, str) or len(tenant_token) != 24:
        raise ValueError("invalid compliance export tenant binding")
    if len(plaintext) > 48 * 1024 * 1024:
        raise ValueError("compliance export exceeds plaintext byte budget")
    nonce = secrets.token_bytes(12)
    aad = ("gameforge-compliance-v1:" + tenant_token).encode("ascii")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    envelope = {
        "format": "gameforge-compliance-aes256gcm-v1",
        "tenant_sha256_prefix": tenant_token,
        "nonce_b64": base64.b64encode(nonce).decode("ascii"),
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
    }
    return json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("ascii")


@dataclass
class CompliancePackMeta:
    generated_at: str
    tenant_id: str
    pack_version: str = "1.0"
    generator: str = "gameforge.compliance"


class ComplianceExportService:
    def __init__(self, out_dir: str | None = None):
        self.out_dir = ensure_directory(Path(out_dir) if out_dir else _data_dir() / "compliance_exports")
        self.access_reviews = AccessReviewService()

    async def build_tenant_pack(
        self,
        tenant_id: str,
        *,
        tenant_snapshot: dict,
        tenant_obj=None,
        audit_limit: int = 2000,
        lookback_days: int = 30,
    ) -> dict:
        events = await AUDIT.list_for_tenant(tenant_id, limit=audit_limit)
        oidc = load_oidc_settings().as_dict()
        quotas = QUOTAS.snapshot(tenant_id)

        sensitive = {
            "tenant.create",
            "member.add",
            "member.update",
            "member.remove",
            "quota.update",
            "crypto.rotate",
            "agent.spawn",
            "work.submit",
            "diary.delete",
            "workspace.create",
            "scim.member.upsert",
            "scim.member.remove",
            "scim.user.upsert",
            "access_review.attest",
            "compliance.export",
        }
        privileged = [e for e in events if e.get("action") in sensitive]

        access_review_report = None
        if tenant_obj is not None:
            access_review_report = await self.access_reviews.build_report(
                tenant_obj, lookback_days=lookback_days
            )

        posture = {
            "oidc": oidc,
            "encryption_enabled_env": os.getenv("GAMEFORGE_ENCRYPTION", "0") == "1",
            "dev_open": oidc.get("dev_open"),
            "quotas": quotas,
            "metrics_snapshot": METRICS.snapshot(),
        }
        retention_policy = {
            "work_history_days": int(os.getenv("GAMEFORGE_WORK_RETENTION_DAYS", "30")),
            "audit_days": int(os.getenv("GAMEFORGE_AUDIT_RETENTION_DAYS", "180")),
            "diary_days": int(os.getenv("GAMEFORGE_DIARY_RETENTION_DAYS", "365")),
        }

        pack = {
            "meta": asdict(
                CompliancePackMeta(
                    generated_at=datetime.utcnow().isoformat(),
                    tenant_id=tenant_id,
                )
            ),
            "access_review": access_review_report
            or {
                "tenant_id": tenant_id,
                "members": tenant_snapshot.get("members", {}),
                "note": "lightweight snapshot only",
            },
            "privileged_audit_events": privileged,
            "audit_event_count_total": len(events),
            "config_posture": posture,
            "retention_policy": retention_policy,
            "control_checklist": self._control_checklist(oidc, posture, bool(access_review_report)),
        }
        body = json.dumps(pack, sort_keys=True, default=str).encode("utf-8")
        pack["meta"]["sha256"] = hashlib.sha256(body).hexdigest()
        tenant_token = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:24]
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        # Compliance bundles may contain private tenant audit events, member details,
        # and enterprise posture. Never publish their plaintext to the filesystem.
        # Require an operator-provisioned 256-bit AES-GCM key; do not silently
        # downgrade to unencrypted JSON when the key is absent or malformed.
        plaintext = json.dumps(pack, indent=2, default=str, allow_nan=False).encode("utf-8")
        sealed = _seal_compliance_export(plaintext, tenant_token)
        filename = f"compliance_{tenant_token}_{timestamp}_{secrets.token_hex(8)}.json.aesgcm"
        with anchored_directory(self.out_dir) as directory:
            atomic_write(
                directory, filename,
                lambda stream: stream.write(sealed), max_bytes=68 * 1024 * 1024,
            )
        path = self.out_dir / filename
        pack["export_path"] = str(path)
        return pack

    def _control_checklist(self, oidc: dict, posture: dict, has_access_review: bool) -> List[dict]:
        return [
            {
                "control": "AUTH-001",
                "title": "Centralized authentication",
                "status": "pass" if oidc.get("enabled") else "gap",
                "evidence": "OIDC configured" if oidc.get("enabled") else "OIDC not enabled",
            },
            {
                "control": "AUTH-002",
                "title": "No open anonymous admin in production",
                "status": "pass" if not oidc.get("dev_open") else "gap",
                "evidence": f"dev_open={oidc.get('dev_open')}",
            },
            {
                "control": "DATA-001",
                "title": "Encryption at rest available",
                "status": "pass" if posture.get("encryption_enabled_env") else "partial",
                "evidence": f"GAMEFORGE_ENCRYPTION={posture.get('encryption_enabled_env')}",
            },
            {
                "control": "AUDIT-001",
                "title": "Privileged actions audited",
                "status": "pass",
                "evidence": "audit_events retained in process log / store",
            },
            {
                "control": "ACCESS-001",
                "title": "RBAC on tenant mutations",
                "status": "pass",
                "evidence": "MemberRole matrix owner/admin/operator/viewer",
            },
            {
                "control": "ACCESS-002",
                "title": "Periodic access review evidence",
                "status": "pass" if has_access_review else "partial",
                "evidence": "access-review report embedded" if has_access_review else "members snapshot only",
            },
            {
                "control": "RET-001",
                "title": "Retention policy declared",
                "status": "pass",
                "evidence": "work/audit/diary retention env defaults",
            },
        ]
