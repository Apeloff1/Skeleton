"""Fake ExecutingModelRouter backed by the real contract helpers."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any, Callable

from skeleton.frontier.runtime.model_router_contract import (
    CallBudget, ProviderOutcome, RoutedCall, RouteStatus, RoutingReceipt, execute_receipt_chain,
)
from skeleton.frontier.runtime.model_runtime import ChatResponse
from skeleton.kernel.capsec import KernelCapabilityGate, TokenIssuer

GOOD = {"schema": "skeleton.forge.ai_builder.plan_proposal.v1", "title": "Ledge Runner",
        "core_loop": "Run, jump, and grab the switch before the tide rises"}


class FakeRouter:
    backend = "fake"

    def __init__(self, chain=("alpha", "beta"), reply: Callable[[str], Any] | None = None):
        self.chain = tuple(chain)
        self.reply = reply or (lambda pid: json.dumps(GOOD))
        self.invoked: list[str] = []
        self.requests: list[Any] = []

    async def execute(self, request, *, gate, cap, task_type="chat", budget=None):
        self.requests.append(request)
        planned = RoutingReceipt(
            request_id=request.request_id, task_type=task_type, backend=self.backend,
            status=RouteStatus.PLANNED, selected_provider_id=self.chain[0], fallback_chain=self.chain[1:],
            rejected={}, budget=budget or CallBudget(), decided_at=time.time())

        def invoke(pid):
            self.invoked.append(pid)
            value = self.reply(pid)
            if isinstance(value, Exception):
                raise value
            return ProviderOutcome(value=value, output_tokens=10)

        chained = await execute_receipt_chain(planned, invoke, gate=gate, cap=cap)
        result = None
        if chained.ok:
            result = SimpleNamespace(response=ChatResponse(model=chained.receipt.served_by, text=chained.value))
        return RoutedCall(chained.receipt, result)


def gate_and_issuer():
    issuer = TokenIssuer()
    return KernelCapabilityGate(issuer), issuer
