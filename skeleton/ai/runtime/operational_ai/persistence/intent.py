"""Durable side-effect intent custody; uncertain operations never auto-retry."""
from __future__ import annotations
from dataclasses import dataclass
from ..authority.canonical import ContractViolation, digest, require_digest
from ..authority.identity import require_id
from .journal import EventJournal, JournalError


@dataclass(frozen=True, slots=True)
class Intent:
    intent_id: str
    action: str
    args_digest: str
    state: str
    receipt: str | None


class IntentLedger:
    """Explicit prepared -> committed/aborted terminal state machine.

    Recovery returns ``prepared`` as uncertainty. It cannot infer whether an
    external side effect occurred; an operator must reconcile externally.
    """

    def __init__(self, journal: EventJournal):
        self.journal = journal

    def status(self, stream: str, intent_id: str) -> Intent | None:
        require_id(intent_id, field="intent ID")
        entries = [event for event in self.journal.replay(stream)
                   if event.payload.get("intent_id") == intent_id]
        if not entries:
            return None
        if entries[0].kind != "intent.prepared":
            raise JournalError("intent missing preparation")
        base = entries[0].payload
        state = "prepared"
        receipt = None
        for event in entries[1:]:
            if state != "prepared" or event.kind not in {"intent.committed","intent.aborted"}:
                raise JournalError("invalid intent transition")
            if event.payload.get("args_digest") != base.get("args_digest"):
                raise JournalError("intent digest drift")
            state = event.kind.split(".")[1]
            receipt = event.payload.get("receipt")
        return Intent(intent_id,base["action"],base["args_digest"],state,receipt)

    def prepare(self, stream: str, intent_id: str, action: str, args: dict) -> Intent:
        require_id(intent_id, field="intent ID")
        require_id(action, field="action")
        arguments_digest = digest(args)
        prior = self.status(stream,intent_id)
        if prior is not None:
            if prior.action != action or prior.args_digest != arguments_digest:
                raise JournalError("intent reuse with different action")
            return prior
        self.journal.append(stream=stream,event_id=f"intent:{intent_id}:start",
                            kind="intent.prepared",payload={"intent_id":intent_id,
                            "action":action,"args_digest":arguments_digest})
        return self.status(stream,intent_id)

    def close(self, stream: str, intent_id: str, arguments_digest: str,
              *, receipt: str, committed: bool) -> Intent:
        require_digest(arguments_digest, field="argument digest")
        require_digest(receipt, field="effect receipt")
        prior = self.status(stream,intent_id)
        if prior is None or prior.args_digest != arguments_digest:
            raise JournalError("cannot finish unknown or mismatched intent")
        desired = "committed" if committed else "aborted"
        if prior.state != "prepared":
            if prior.state == desired and prior.receipt == receipt:
                return prior
            raise JournalError("intent terminal state cannot be changed")
        self.journal.append(stream=stream,event_id=f"intent:{intent_id}:terminal",
                            kind=f"intent.{desired}",payload={"intent_id":intent_id,
                            "args_digest":arguments_digest,"receipt":receipt})
        return self.status(stream,intent_id)

    def uncertain(self, stream: str) -> tuple[Intent, ...]:
        ids = {e.payload.get("intent_id") for e in self.journal.replay(stream)
               if e.kind == "intent.prepared"}
        return tuple(x for key in sorted(ids) if (x:=self.status(stream,key)) and x.state=="prepared")
