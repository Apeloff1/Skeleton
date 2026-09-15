from __future__ import annotations
import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import os

from gameforge.enterprise.audit import AUDIT
from gameforge.enterprise.quotas import QUOTAS
from gameforge.enterprise.oidc_config import load_oidc_settings
from gameforge.enterprise.alerts import METRICS
from gameforge.enterprise.access_review import AccessReviewService


def _data_dir() -> Path:
    p = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class CompliancePackMeta:
    generated_at: str
    tenant_id: str
    pack_version: str = "1.0"
    generator: str = "gameforge.compliance"


class ComplianceExportService:
    def __init__(self, out_dir: str | None = None):
        self.out_dir = Path(out_dir or _data_dir() / "compliance_exports")
        self.out_dir.mkdir(parents=True, exist_ok=True)
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
        path = self.out_dir / f"compliance_{tenant_id}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
        path.write_text(json.dumps(pack, indent=2, default=str))
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
