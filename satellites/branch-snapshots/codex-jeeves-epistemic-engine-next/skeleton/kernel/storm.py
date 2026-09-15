"""Storm gate — drop identical stimuli / tool calls inside a short window. F-9.

Text stimuli use :meth:`admit` (wired from ``orchestrator.dispatch``).
Tool calls use :meth:`admit_tool` / :meth:`batch_tools` — identity is
``name`` + a stable args hash, composed with :class:`DedupLedger`.

Wire point: ``Orchestrator.admit_tool`` / ``Orchestrator.batch_tools``
(and bank kernel ``storm``) — there is no separate tool-call bus yet;
issuers should gate through orch/storm before spending a tool slot.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from skeleton.kernel.dedup import DedupLedger


def _canonical_args(args: Any) -> str:
    """Stable JSON for tool-call identity (order-independent for mappings)."""
    try:
        return json.dumps(args, sort_keys=True, default=str, separators=(",", ":"))
    except TypeError:
        return repr(args)


class Storm:
    def __init__(
        self,
        *,
        ttl_s: float = 8.0,
        capacity: int = 256,
        tool_ttl_s: Optional[float] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.ledger = DedupLedger(ttl_s=ttl_s, capacity=capacity, clock=clock)
        # Turn-window ledger for tool calls; defaults to the same TTL as stimuli.
        self.tool_ledger = DedupLedger(
            ttl_s=ttl_s if tool_ttl_s is None else tool_ttl_s,
            capacity=capacity,
            clock=clock,
        )
        self.seen_n = 0
        self.drop_n = 0
        self.tool_seen_n = 0
        self.tool_drop_n = 0
        self.tool_batch_collapsed_n = 0

    def key(self, text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:24]

    def tool_key(self, name: str, args: Any = None) -> str:
        """Identity for a tool call: name + canonical args digest."""
        blob = f"{name or ''}\0{_canonical_args(args)}"
        return "t:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]

    def admit(self, text: str) -> bool:
        kid = self.key(text)
        if self.ledger.seen(kid):
            self.drop_n += 1
            return False
        self.ledger.record(kid)
        self.seen_n += 1
        return True

    def admit_tool(self, name: str, args: Any = None) -> bool:
        """Admit one tool call; False if an identical call is still in the turn window."""
        kid = self.tool_key(name, args)
        if self.tool_ledger.seen(kid):
            self.tool_drop_n += 1
            return False
        self.tool_ledger.record(kid)
        self.tool_seen_n += 1
        return True

    def batch_tools(
        self,
        calls: Sequence[Mapping[str, Any]],
        *,
        name_key: str = "name",
        args_key: str = "args",
    ) -> List[Dict[str, Any]]:
        """Collapse identical tool calls within one turn; record survivors in the ledger.

        Each input mapping needs at least ``name`` (or ``name_key``). Args default
        to ``{}`` when missing. Survivors keep first-seen order and gain
        ``batch_n`` (how many identical inputs collapsed into that slot).
        Duplicates increment ``tool_drop_n`` / ``tool_batch_collapsed_n`` and are
        omitted from the return list.
        """
        out: List[Dict[str, Any]] = []
        index_by_key: Dict[str, int] = {}
        for raw in calls:
            name = str(raw.get(name_key) or "")
            args = raw.get(args_key, {})
            kid = self.tool_key(name, args)
            if kid in index_by_key:
                idx = index_by_key[kid]
                out[idx]["batch_n"] = int(out[idx].get("batch_n") or 1) + 1
                self.tool_drop_n += 1
                self.tool_batch_collapsed_n += 1
                continue
            if self.tool_ledger.seen(kid):
                # Identical call already admitted earlier in the turn window.
                self.tool_drop_n += 1
                self.tool_batch_collapsed_n += 1
                continue
            self.tool_ledger.record(kid)
            self.tool_seen_n += 1
            item = dict(raw)
            item.setdefault(name_key, name)
            item.setdefault(args_key, args if args is not None else {})
            item["batch_n"] = 1
            index_by_key[kid] = len(out)
            out.append(item)
        return out

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "kernel-storm",
            "seen": self.seen_n,
            "drop": self.drop_n,
            "tool_seen": self.tool_seen_n,
            "tool_drop": self.tool_drop_n,
            "tool_batch_collapsed": self.tool_batch_collapsed_n,
            "stored_prose": 0,
        }
