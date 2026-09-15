from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from gameforge.enterprise.tenancy import Tenant, MemberRole
from gameforge.enterprise.audit import AUDIT


@dataclass
class AccessReviewFinding:
    severity: str
    code: str
    message: str
    user_id: Optional[str] = None


class AccessReviewService:
    async def build_report(self, tenant: Tenant, *, lookback_days: int = 30) -> Dict[str, Any]:
        members = {u: r.value for u, r in tenant.members.items()}
        owners = [u for u, r in tenant.members.items() if r == MemberRole.OWNER]
        admins = [u for u, r in tenant.members.items() if r == MemberRole.ADMIN]
        events = await AUDIT.list_for_tenant(tenant.tenant_id, limit=2000)
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)
        recent = []
        for e in events:
            try:
                ts = datetime.fromisoformat(e["ts"])
            except Exception:
                continue
            if ts >= cutoff:
                recent.append(e)
        member_changes = [
            e
            for e in recent
            if e.get("action")
            in {
                "member.add",
                "member.update",
                "member.remove",
                "scim.member.upsert",
                "scim.member.remove",
            }
        ]
        findings: List[AccessReviewFinding] = []
        if len(owners) == 0:
            findings.append(AccessReviewFinding("critical", "NO_OWNER", "Tenant has no owner"))
        if len(owners) > 3:
            findings.append(
                AccessReviewFinding(
                    "warn",
                    "MANY_OWNERS",
                    f"Tenant has {len(owners)} owners; prefer least privilege",
                )
            )
        if len(admins) > 10:
            findings.append(
                AccessReviewFinding("warn", "MANY_ADMINS", f"Tenant has {len(admins)} admins")
            )
        if not member_changes and (len(admins) + len(owners)) >= 5:
            findings.append(
                AccessReviewFinding(
                    "info",
                    "REVIEW_RECOMMENDED",
                    f"No membership changes in last {lookback_days} days; run manual access attestation",
                )
            )
        return {
            "tenant_id": tenant.tenant_id,
            "generated_at": datetime.utcnow().isoformat(),
            "lookback_days": lookback_days,
            "summary": {
                "member_count": len(members),
                "owner_count": len(owners),
                "admin_count": len(admins),
                "operator_count": sum(1 for r in tenant.members.values() if r == MemberRole.OPERATOR),
                "viewer_count": sum(1 for r in tenant.members.values() if r == MemberRole.VIEWER),
                "membership_changes_in_window": len(member_changes),
            },
            "members": members,
            "owners": owners,
            "admins": admins,
            "recent_membership_events": member_changes[:100],
            "findings": [asdict(f) for f in findings],
            "attestation": {
                "statement": "I reviewed the members and roles listed above and confirmed least-privilege access.",
                "reviewer_user_id": None,
                "reviewed_at": None,
                "notes": None,
            },
        }
