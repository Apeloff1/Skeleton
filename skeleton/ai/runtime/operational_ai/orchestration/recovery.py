"""Read-only integrity review and explicitly approved audit reconciliation.

The canonical OfflineChatStore commits a turn first; the companion EventJournal
cannot be in the same transaction because it is another SQLite file. If the
process dies between those operations the conversation is authoritative and
has no audit record. This module verifies both stores *without inference*,
then permits only an explicit operator-approved backfill of missing events.

It never guesses a transcript, replays a native model, silently repairs a
conflict, or hides an unexpected journal event.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Any

from ..authority.canonical import ContractViolation
from ..authority.identity import require_id
from ..persistence.journal import JournalError

_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    session: str
    turns: int
    journal_events: int
    audit_head: str
    missing_audits: int
    status: str


def _authoritative(service: Any, session: str) -> tuple[dict[str, Any], ...]:
    """Require fully validated chat transcript before deriving a repair event."""
    require_id(session, field="conversation")
    with service.store.read_snapshot():
        snapshot = service.store.load(session, service.actor.model_digest,
                                      service.actor.tokenizer_digest)
        rows = service.store._db.execute(
            "SELECT request_id, request_digest, output_digest, revision "
            "FROM offline_turns WHERE session_id=? ORDER BY revision", (session,)
        ).fetchall()
    if len(rows) != snapshot.revision or snapshot.revision > 10_000:
        raise ContractViolation("authoritative chat history is incomplete or unbounded")
    receipts: list[dict] = []
    seen = set()
    for expected, row in enumerate(rows, start=1):
        rid, request_digest, output_digest, revision = row
        require_id(rid, field="request ID")
        if (rid in seen or type(revision) is not int or revision != expected
            or not isinstance(request_digest, str) or not _HEX.fullmatch(request_digest)
            or not isinstance(output_digest, str) or not _HEX.fullmatch(output_digest)):
            raise ContractViolation("authoritative turn receipt corruption")
        seen.add(rid)
        receipts.append({"request_id": rid, "request_digest": request_digest,
                         "output_digest": output_digest, "revision": revision,
                         "model_digest": service.actor.model_digest})
    return tuple(receipts)


def _inspect(service: Any, session: str):
    receipts = _authoritative(service, session)
    events = service.journal.replay(session)  # verifies the entire hash chain
    actual = {}
    for event in events:
        if event.kind == "ai.turn.committed":
            payload = event.payload
            rid = payload.get("request_id")
            if (rid in actual or event.event_id != "ai_turn_" + str(rid)):
                raise ContractViolation("journal contains duplicate or noncanonical turn receipt")
            actual[rid] = event
    planned = {receipt["request_id"]: receipt for receipt in receipts}
    if set(actual) - set(planned):
        raise ContractViolation("journal contains a turn absent from authoritative chat")
    for rid, event in actual.items():
        expected = planned[rid]
        if event.payload != expected:
            raise ContractViolation("audit and canonical chat receipt disagree")
    missing = tuple(item for item in receipts if item["request_id"] not in actual)
    head = service.journal.head(session)
    report = RecoveryReport(session, len(receipts), len(events), head[1], len(missing),
                            "audit-incomplete" if missing else "verified")
    return report, missing


def inspect(service: Any, session: str) -> RecoveryReport:
    """Read only, fail closed on any conflicting or missing authoritative turn."""
    return _inspect(service, session)[0]


def reconcile(service: Any, session: str, *, approved: bool = False,
              maximum_missing: int = 1000) -> RecoveryReport:
    """Backfill only verified missing *audit* entries; never repeat inference.

    Approval must originate in an independently authenticated operator action;
    the model API intentionally does not expose this function.
    """
    if approved is not True:
        raise ContractViolation("explicit independent audit reconciliation approval required")
    if type(maximum_missing) is not int or not 1 <= maximum_missing <= 1000:
        raise ContractViolation("invalid finite audit reconciliation ceiling")
    report, missing = _inspect(service, session)
    if len(missing) > maximum_missing:
        raise ContractViolation("too many missing audit entries for bounded repair")
    # The source rows and journal might change concurrently. Each repair uses an
    # idempotent event ID and append verifies the complete chain before commit.
    # Revalidate afterward, and refuse conflicts rather than guessing.
    for row in missing:
        service.journal.append(stream=session, event_id="ai_turn_" + row["request_id"],
                               kind="ai.turn.committed", payload=row)
    final = inspect(service, session)
    if final.missing_audits:
        raise ContractViolation("audit reconciliation was not complete")
    return final
