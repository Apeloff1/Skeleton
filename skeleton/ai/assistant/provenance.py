"""Deterministic provenance records for assistant synthesis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from .contracts import RoutingPlan, ToolReceipt, digest_json


@dataclass(frozen=True, slots=True)
class AssistantRunRecord:
    request_digest: str
    route_digest: str
    context_digest: str | None
    capability_ids: tuple[str, ...]
    tool_receipt_digests: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    response_digest: str
    created_at: datetime

    @property
    def digest(self) -> str:
        return digest_json(
            {
                "request_digest": self.request_digest,
                "route_digest": self.route_digest,
                "context_digest": self.context_digest,
                "capability_ids": list(self.capability_ids),
                "tool_receipt_digests": list(self.tool_receipt_digests),
                "evidence_refs": list(self.evidence_refs),
                "response_digest": self.response_digest,
                "created_at": self.created_at.isoformat(),
            }
        )


def receipt_digest(receipt: ToolReceipt) -> str:
    return digest_json(
        {
            "proposal_id": receipt.proposal_id,
            "capability_id": receipt.capability_id,
            "status": receipt.status,
            "output_ref": receipt.output_ref,
            "request_digest": receipt.request_digest,
            "arguments_digest": receipt.arguments_digest,
            "started_at": receipt.started_at.isoformat(),
            "finished_at": receipt.finished_at.isoformat(),
            "error_code": receipt.error_code,
            "provenance": list(receipt.provenance),
        }
    )


class ProvenanceBuilder:
    @staticmethod
    def build(
        *,
        request_digest: str,
        route: RoutingPlan,
        response_text: str,
        context_digest: str | None = None,
        capability_ids: Iterable[str] = (),
        tool_receipts: Iterable[ToolReceipt] = (),
        evidence_refs: Iterable[str] = (),
        created_at: datetime | None = None,
    ) -> AssistantRunRecord:
        if route.request_digest != request_digest:
            raise ValueError("route is bound to a different request")
        if not isinstance(response_text, str) or not response_text.strip():
            raise ValueError("response_text must be non-empty")

        capabilities = tuple(dict.fromkeys(str(item).strip() for item in capability_ids if str(item).strip()))
        receipts = tuple(tool_receipts)
        for receipt in receipts:
            if receipt.request_digest != request_digest:
                raise ValueError("tool receipt is bound to a different request")
        evidence = tuple(dict.fromkeys(str(item).strip() for item in evidence_refs if str(item).strip()))
        instant = datetime.now(timezone.utc) if created_at is None else created_at.astimezone(timezone.utc)

        return AssistantRunRecord(
            request_digest=request_digest,
            route_digest=route.digest,
            context_digest=context_digest,
            capability_ids=capabilities,
            tool_receipt_digests=tuple(receipt_digest(item) for item in receipts),
            evidence_refs=evidence,
            response_digest=digest_json({"response_text": response_text.strip()}),
            created_at=instant,
        )


__all__ = ["AssistantRunRecord", "ProvenanceBuilder", "receipt_digest"]
