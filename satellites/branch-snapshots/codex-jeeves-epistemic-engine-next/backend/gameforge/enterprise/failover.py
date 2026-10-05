from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Dict, Any
import os


@dataclass
class FailoverStep:
    id: str
    title: str
    owner: str
    automated: bool
    command_or_action: str
    expected_result: str


class MultiRegionFailoverRunbook:
    def __init__(self):
        self.primary = os.getenv("GAMEFORGE_REGION_PRIMARY", "eu-north-1")
        self.secondary = os.getenv("GAMEFORGE_REGION_SECONDARY", "eu-west-1")

    def steps(self) -> List[FailoverStep]:
        return [
            FailoverStep(
                "dns_precheck",
                "Verify secondary health endpoints",
                "sre",
                True,
                "GET secondary /health && /ready",
                "200 + ready=true",
            ),
            FailoverStep(
                "queue_drain_primary",
                "Pause producers / drain primary queue",
                "sre",
                False,
                "Disable deploy + wait queue depth ~0",
                "Primary queue lag near zero",
            ),
            FailoverStep(
                "promote_secondary_db",
                "Promote secondary Postgres",
                "dba",
                False,
                "Managed DB promote / update DATABASE_URL",
                "Writes succeed on secondary",
            ),
            FailoverStep(
                "redis_repoint",
                "Repoint Redis Streams consumers",
                "sre",
                False,
                "Update REDIS_URL; restart workers",
                "Workers consume on secondary",
            ),
            FailoverStep(
                "backup_restore_verify",
                "Verify latest S3 backup in secondary",
                "sre",
                True,
                "List s3 bucket latest object",
                "Fresh backup object exists",
            ),
            FailoverStep(
                "dns_cutover",
                "DNS / LB cutover",
                "sre",
                False,
                "Update Route53/CNAME or LB pool",
                "Public traffic on secondary",
            ),
            FailoverStep(
                "postcheck",
                "Post-failover smoke",
                "sre",
                True,
                "health, ready, sample work, audit",
                "All green",
            ),
            FailoverStep(
                "comms",
                "Incident comms + timeline",
                "incident-commander",
                False,
                "Status post + compliance export",
                "Stakeholders notified",
            ),
        ]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "primary_region": self.primary,
            "secondary_region": self.secondary,
            "rto_target_minutes": int(os.getenv("GAMEFORGE_RTO_MINUTES", "60")),
            "rpo_target_minutes": int(os.getenv("GAMEFORGE_RPO_MINUTES", "15")),
            "steps": [asdict(s) for s in self.steps()],
        }
