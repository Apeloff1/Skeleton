"""Phase 5 action plane. Every AI-tree task lives here. Tools cross into side effects only with a receipt."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


AUTHORITY = ("read", "write", "destructive")


@dataclass(frozen=True)
class P5Tool:
    tool_id: str
    capability_id: str
    authority: str
    input_schema: str
    output_schema: str
    timeout_ms: int
    idempotent: bool
    secret_policy: str
    sandbox: str

    def card(self) -> dict:
        if self.authority not in AUTHORITY:
            raise ValueError(self.authority)
        return {
            "tool_id": self.tool_id,
            "capability_id": self.capability_id,
            "authority": self.authority,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "timeout_ms": self.timeout_ms,
            "idempotent": self.idempotent,
            "secret_policy": self.secret_policy,
            "sandbox": self.sandbox,
            "plane": "p5",
        }


@dataclass
class P5Task:
    task_id: str
    capability_id: str
    tool_id: str
    oracle: str
    status: str = "open"
    receipt: dict = field(default_factory=dict)

    def place(self) -> dict:
        return {
            "task_id": self.task_id,
            "capability_id": self.capability_id,
            "tool_id": self.tool_id,
            "oracle": self.oracle,
            "status": self.status,
            "plane": "p5",
            "receipt": self.receipt,
        }


def tool_for(capability_id: str, authority: str = "read") -> P5Tool:
    return P5Tool(
        tool_id=f"p5.{capability_id.lower()}",
        capability_id=capability_id,
        authority=authority,
        input_schema="pointer-stimulus",
        output_schema="card",
        timeout_ms=2000,
        idempotent=True,
        secret_policy="refuse-live-secret",
        sandbox="cpu-no-network",
    )


def ledger(tasks: list[P5Task]) -> dict:
    placed = [task.place() for task in tasks]
    return {
        "plane": "p5",
        "name": "action",
        "rule": "every task is placed in p5 before a receipt or a signature",
        "count": len(placed),
        "confirmed": sum(1 for row in placed if row["status"] == "confirmed"),
        "withheld": sum(1 for row in placed if row["status"] == "withheld"),
        "open": sum(1 for row in placed if row["status"] == "open"),
        "tasks": placed,
    }


def receipt(tool: P5Tool, result: Mapping[str, object], digest: str) -> dict:
    return {
        "tool_id": tool.tool_id,
        "authority": tool.authority,
        "timeout_ms": tool.timeout_ms,
        "idempotent": tool.idempotent,
        "digest": digest,
        "hit": result.get("hit", 1),
        "law": result.get("law", tool.capability_id),
        "sandbox": tool.sandbox,
    }
