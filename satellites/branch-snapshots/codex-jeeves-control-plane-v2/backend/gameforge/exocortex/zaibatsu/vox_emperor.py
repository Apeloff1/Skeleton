from __future__ import annotations
"""
Warhammer-style Emperor organizational logic + VOX communication system.

Hierarchy of command:
  Emperor (user sovereignty) → High Lords (Boardroom) → Jeeves (Seneschal) → Agents (Astartes/servitors)

VOX: structured, priority-coded channels for Jeeves↔Agent and Jeeves↔Boardroom.
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class VoxPriority(str, Enum):
    Vox_Extremis = "extremis"      # emergency, ACC alarm, security
    Vox_Prioris = "prioris"        # judgement, schedule override
    Vox_Normalis = "normalis"      # standard task routing
    Vox_Minima = "minima"          # ambient, logs


class CommandSeal(str, Enum):
    """Emperor-style seals — only higher seal may countermand lower."""
    EMPEROR = "emperor"       # user direct
    HIGH_LORDS = "high_lords"  # boardroom consensus
    SENESCHAL = "seneschal"    # Jeeves
    CAPTAIN = "captain"        # lead agent
    BROTHER = "brother"        # agent


@dataclass
class VoxMessage:
    vox_id: str
    channel: str  # jeeves_agent | jeeves_boardroom | boardroom_agent | broadcast
    priority: str
    seal: str
    from_id: str
    to_id: str
    subject: str
    body: Dict[str, Any]
    requires_ack: bool = True
    acked: bool = False
    created_at: str = field(default_factory=_ts)

    def to_dict(self) -> dict:
        return asdict(self)


class VoxNetwork:
    """VOX casters between Jeeves, agents, and boardroom."""

    SEAL_RANK = {
        CommandSeal.EMPEROR.value: 100,
        CommandSeal.HIGH_LORDS.value: 80,
        CommandSeal.SENESCHAL.value: 60,
        CommandSeal.CAPTAIN.value: 40,
        CommandSeal.BROTHER.value: 20,
    }

    def __init__(self):
        self.inbox: List[VoxMessage] = []
        self.outbox: List[VoxMessage] = []
        self.log: List[dict] = []

    def transmit(
        self,
        channel: str,
        priority: VoxPriority | str,
        seal: CommandSeal | str,
        from_id: str,
        to_id: str,
        subject: str,
        body: Optional[Dict[str, Any]] = None,
        requires_ack: bool = True,
    ) -> VoxMessage:
        pri = priority.value if isinstance(priority, VoxPriority) else priority
        sel = seal.value if isinstance(seal, CommandSeal) else seal
        msg = VoxMessage(
            vox_id=str(uuid.uuid4())[:12],
            channel=channel,
            priority=pri,
            seal=sel,
            from_id=from_id,
            to_id=to_id,
            subject=subject,
            body=body or {},
            requires_ack=requires_ack,
        )
        self.outbox.append(msg)
        self.inbox.append(msg)
        self.log.append({"ts": _ts(), "event": "transmit", "vox_id": msg.vox_id, "priority": pri, "channel": channel})
        if len(self.inbox) > 5000:
            self.inbox = self.inbox[-5000:]
        return msg

    def ack(self, vox_id: str) -> Dict[str, Any]:
        for m in self.inbox:
            if m.vox_id == vox_id:
                m.acked = True
                self.log.append({"ts": _ts(), "event": "ack", "vox_id": vox_id})
                return {"ok": True, "vox_id": vox_id}
        return {"ok": False, "error": "not_found"}

    def can_countermand(self, challenger_seal: str, standing_seal: str) -> bool:
        return self.SEAL_RANK.get(challenger_seal, 0) > self.SEAL_RANK.get(standing_seal, 0)

    def boardroom_broadcast(self, subject: str, body: Dict[str, Any], seal: str = "seneschal") -> VoxMessage:
        return self.transmit(
            "jeeves_boardroom",
            VoxPriority.Vox_Prioris,
            seal,
            "jeeves",
            "boardroom",
            subject,
            body,
        )

    def agent_order(self, agent_id: str, subject: str, body: Dict[str, Any], priority: str = "normalis") -> VoxMessage:
        return self.transmit(
            "jeeves_agent",
            priority,
            CommandSeal.SENESCHAL,
            "jeeves",
            agent_id,
            subject,
            body,
        )

    def pending(self, to_id: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = self.inbox
        if to_id:
            rows = [m for m in rows if m.to_id == to_id and not m.acked]
        return [m.to_dict() for m in rows[-50:]]

    def status(self) -> Dict[str, Any]:
        return {
            "inbox": len(self.inbox),
            "unacked": sum(1 for m in self.inbox if m.requires_ack and not m.acked),
            "channels": ["jeeves_agent", "jeeves_boardroom", "boardroom_agent", "broadcast"],
            "seal_ranks": self.SEAL_RANK,
        }


class EmperorDoctrine:
    """
    Organizational logic: the Emperor (user) is sovereign.
    Jeeves is Seneschal — serves, never usurps.
    Boardroom advises; agents execute under VOX orders.
    """

    DOCTRINES = [
        "The Emperor's will is the user's expressed intent under reason.",
        "Jeeves may never countermand a direct Emperor seal without explicit user revocation protocol.",
        "Sacrifice of truth for comfort is heresy against the Sword of Truth laws.",
        "Agents do not freestyle strategic goals — they execute sealed orders.",
        "Boardroom may dissent via VOX Prioris; final seal rests with Emperor or delegated Seneschal under policy.",
        "In extremis (security, ACC cascade, sovereignty breach), Seneschal may freeze actions pending Emperor review.",
    ]

    def __init__(self):
        self.vox = VoxNetwork()

    def principles(self) -> List[str]:
        return list(self.DOCTRINES)
