"""Milestone 6: campaign ledger over frontier sessions.

Aggregates ordered session admissions into a campaign record,
compares two campaign outcomes, and produces an audit receipt.
Candidate-only. No GPU, no weight loading.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
from hashlib import sha256
import json
from typing import Sequence

from .game_frontier_session import FrontierSession


class CampaignError(ValueError):
    pass


@dataclass
class CampaignLedger:
    """Ordered record of frontier sessions under one campaign id."""

    campaign_id: str
    sessions: list[FrontierSession] = field(default_factory=list)
    head: str = ""

    def __post_init__(self) -> None:
        if type(self.campaign_id) is not str or not self.campaign_id or len(self.campaign_id) > 80:
            raise CampaignError("campaign_id required and bounded")

    def add(self, session: FrontierSession) -> str:
        if not isinstance(session, FrontierSession) or not session.verify():
            raise CampaignError("session must verify before campaign admission")
        if self.sessions and not self.verify():
            raise CampaignError("existing campaign failed verification")
        if any(prior.session_id == session.session_id for prior in self.sessions):
            raise CampaignError("duplicate session identity")
        session = deepcopy(session)
        payload = json.dumps(
            {
                "prev": self.head,
                "session": session.session_id,
                "head": session.head,
                "steps": len(session.admissions),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        self.head = sha256(payload.encode()).hexdigest()
        self.sessions.append(session)
        return self.head

    def verify(self) -> bool:
        if type(self.sessions) is not list or not self.sessions or type(self.head) is not str:
            return False
        head = ""
        seen = set()
        for session in self.sessions:
            if (not isinstance(session, FrontierSession) or not session.verify()
                    or session.session_id in seen):
                return False
            seen.add(session.session_id)
            payload = json.dumps(
                {
                    "prev": head,
                    "session": session.session_id,
                    "head": session.head,
                    "steps": len(session.admissions),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            head = sha256(payload.encode()).hexdigest()
        return head == self.head


def compare_campaigns(left: CampaignLedger, right: CampaignLedger) -> dict:
    """Flag divergences between two verified campaigns."""
    if not left.verify() or not right.verify():
        raise CampaignError("both campaigns must verify")
    return {
        "left": left.campaign_id,
        "right": right.campaign_id,
        "session_count_match": len(left.sessions) == len(right.sessions),
        "head_match": left.head == right.head,
        "left_sessions": len(left.sessions),
        "right_sessions": len(right.sessions),
    }


def audit_receipt(ledger: CampaignLedger) -> str:
    """Content-address a verified campaign for external audit."""
    if not ledger.verify():
        raise CampaignError("ledger must verify before audit")
    payload = json.dumps(
        {
            "campaign": ledger.campaign_id,
            "head": ledger.head,
            "sessions": [s.session_id for s in ledger.sessions],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode()).hexdigest()
