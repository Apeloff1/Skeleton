"""Fail-closed, run-scoped no-found compaction for Jeeves delivery context.

Only typed tool outcomes can be compacted. Original observations and evidence
remain in the authoritative run/checkpoint; only the final model prompt gets
a shorter view. These notes are not evidence of global nonexistence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .types import Goal, ToolObservation, canonical_json, stable_fingerprint


def _base36(number: int) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    digits = ""
    while number:
        number, digit = divmod(number, 36)
        digits = alphabet[digit] + digits
    return (digits or "0").rjust(6, "0")


class PageClicker:
    """Monotonic page click and alphanumeric serials within one run."""

    def __init__(self) -> None:
        self.count = 0

    def click(self) -> str:
        self.count += 1
        return f"JVS-{_base36(self.count)}-P{self.count:06d}"


def observation_digest(observation: ToolObservation) -> str:
    return stable_fingerprint({
        "id": observation.call_id,
        "tool": observation.tool_name,
        "ok": observation.ok,
        "payload": observation.payload,
        "error": observation.error,
        "evidence": [ref.evidence_id for ref in observation.evidence],
    })


def is_no_found(observation: ToolObservation) -> bool:
    """Avoid confusing denied, failed, timed-out or partial searches with absence."""
    if observation.ok:
        value = observation.payload
        if not isinstance(value, dict):
            return False
        if value.get("partial") is True or value.get("truncated") is True:
            return False
        if value.get("status") in {"not_found", "no_results", "no_matches"}:
            return True
        return value.get("found") is False and value.get("complete") is True
    error = (observation.error or "").strip().lower()
    forbidden = ("permission", "forbidden", "timeout", "unavailable", "rate limit", "unauthorized")
    return bool(error) and not any(word in error for word in forbidden) and bool(
        re.search(r"\b(?:404|not found|no matches|no results)\b", error)
    )


def _scope(observation: ToolObservation) -> str:
    payload = observation.payload
    if isinstance(payload, dict):
        for key in ("query", "search_query", "path", "target", "resource"):
            item = payload.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()[:192]
    return "(scope not supplied by tool)"


@dataclass(frozen=True, slots=True)
class NoFoundNote:
    call_id: str
    tool_name: str
    scope: str
    source_digest: str
    serial: str

    @property
    def text(self) -> str:
        return (f"{self.serial}: {self.tool_name} returned no result for "
                f"{self.scope}. Scope-limited observation only; "
                "do not infer global nonexistence.")

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "call_id": self.call_id, "tool_name": self.tool_name,
            "scope": self.scope, "source_digest": self.source_digest,
            "serial": self.serial,
        })


@dataclass(frozen=True, slots=True)
class CycleReceipt:
    sequence: int
    serial: str
    action: str
    subject_digest: str
    previous: str
    digest: str

    @classmethod
    def issue(cls, sequence: int, serial: str, action: str,
              subject_digest: str, previous: str) -> "CycleReceipt":
        digest = stable_fingerprint({
            "sequence": sequence, "serial": serial, "action": action,
            "subject_digest": subject_digest, "previous": previous,
        })
        return cls(sequence, serial, action, subject_digest, previous, digest)


@dataclass(frozen=True, slots=True)
class PreparedDelivery:
    goal_digest: str
    original_digests: tuple[tuple[str, str], ...]
    active_observations: tuple[ToolObservation, ...]
    notes: tuple[NoFoundNote, ...]
    receipts: tuple[CycleReceipt, ...]
    page_count: int
    freed_chars: int
    refill: str

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "goal": self.goal_digest,
            "sources": self.original_digests,
            "active": [item.call_id for item in self.active_observations],
            "notes": [note.fingerprint for note in self.notes],
            "receipt": self.receipts[-1].digest if self.receipts else None,
            "pages": self.page_count,
            "refill": self.refill,
        })

    def prompt_note(self) -> str:
        if not self.notes:
            return ""
        return canonical_json({
            "kind": "temporary_run_working_memory",
            "scope": "This attempt did not find a match, not proof of absence.",
            "notes": [note.text for note in self.notes[-16:]],
            "older_note_count": max(0, len(self.notes) - 16),
            "older_notes_digest": stable_fingerprint([
                note.fingerprint for note in self.notes[:-16]
            ]),
            "total_note_count": len(self.notes),
            "original_user_goal_digest": self.goal_digest,
            "reclaimed_chars_estimate": self.freed_chars,
            "page_counter": self.page_count,
            "last_serial": self.receipts[-1].serial,
            "audit_receipt": self.fingerprint,
            "continuation": self.refill,
        })


class WorkingContextCycle:
    """Pre-delivery compaction and verified hand-off; never edits the source ledger."""

    def __init__(self, *, max_notes: int = 8192, max_refill_chars: int = 4096) -> None:
        if not isinstance(max_notes, int) or isinstance(max_notes, bool) or not 1 <= max_notes <= 50000:
            raise ValueError("invalid max_notes")
        if not isinstance(max_refill_chars, int) or isinstance(max_refill_chars, bool) or not 128 <= max_refill_chars <= 65536:
            raise ValueError("invalid max_refill_chars")
        self.max_notes = max_notes
        self.max_refill_chars = max_refill_chars

    def prepare(self, goal: Goal, observations: Sequence[ToolObservation],
                *, refill_text: str = "") -> PreparedDelivery:
        original = tuple(observations)
        ids = [item.call_id for item in original]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate tool observation IDs in delivery")
        if any(not isinstance(item, ToolObservation) for item in original):
            raise TypeError("observations must be ToolObservation")
        failed = tuple(item for item in original if is_no_found(item))
        if len(failed) > self.max_notes:
            # Do not silently drop evidence: on overflow, the unabridged context remains.
            raise ValueError("no-found note capacity exceeded")
        pages = PageClicker()
        notes: list[NoFoundNote] = []
        receipts: list[CycleReceipt] = []
        previous = "0" * 64

        def record(action: str, subject: str) -> str:
            nonlocal previous
            serial = pages.click()
            receipt = CycleReceipt.issue(len(receipts) + 1, serial, action, subject, previous)
            receipts.append(receipt)
            previous = receipt.digest
            return serial

        for item in failed:
            digest = observation_digest(item)
            serial = record("no_found_compacted", digest)
            notes.append(NoFoundNote(item.call_id, item.tool_name, _scope(item), digest, serial))
        kept = tuple(item for item in original if item.call_id not in {note.call_id for note in notes})
        cleaned_refill = refill_text.strip()[:self.max_refill_chars] if notes else ""
        if notes:
            record("refill_context", stable_fingerprint({"goal": goal.goal_id, "refill": cleaned_refill,
                                                          "active": [item.call_id for item in kept]}))
            record("delivery_audit_pending", stable_fingerprint([note.fingerprint for note in notes]))
        freed = max(0, sum(len(canonical_json({
            "payload": item.payload, "error": item.error, "tool": item.tool_name,
            "call": item.call_id
        })) for item in failed) - sum(len(note.text) for note in notes))
        return PreparedDelivery(
            goal_digest=stable_fingerprint({
                "goal_id": goal.goal_id, "objective": goal.objective,
                "criteria": list(goal.success_criteria), "constraints": list(goal.constraints),
            }),
            original_digests=tuple((item.call_id, observation_digest(item)) for item in original),
            active_observations=kept,
            notes=tuple(notes),
            receipts=tuple(receipts),
            page_count=pages.count,
            freed_chars=freed,
            refill=cleaned_refill,
        )


class IntegrityVerifier:
    """Verifier 1: independent source/compaction and hash-chain reconstruction."""

    @staticmethod
    def verify(prepared: PreparedDelivery, goal: Goal,
               observations: Sequence[ToolObservation]) -> None:
        expected_goal = stable_fingerprint({
            "goal_id": goal.goal_id, "objective": goal.objective,
            "criteria": list(goal.success_criteria), "constraints": list(goal.constraints),
        })
        if prepared.goal_digest != expected_goal:
            raise ValueError("working context changed the original goal")
        original = tuple(observations)
        if prepared.original_digests != tuple((x.call_id, observation_digest(x)) for x in original):
            raise ValueError("working context observation digest mismatch")
        removed = {note.call_id for note in prepared.notes}
        if removed != {x.call_id for x in original if is_no_found(x)}:
            raise ValueError("working context removed non-no-found observation")
        if tuple(x.call_id for x in prepared.active_observations) != tuple(
            x.call_id for x in original if x.call_id not in removed
        ):
            raise ValueError("working context lost active evidence")
        by_id = {x.call_id: x for x in original}
        if any(note.source_digest != observation_digest(by_id[note.call_id]) for note in prepared.notes):
            raise ValueError("no-found note source was modified")
        previous = "0" * 64
        for sequence, receipt in enumerate(prepared.receipts, 1):
            expected = CycleReceipt.issue(sequence, receipt.serial,
                                          receipt.action, receipt.subject_digest, previous)
            if receipt != expected or receipt.serial != (
                f"JVS-{_base36(sequence)}-P{sequence:06d}"
            ):
                raise ValueError("page counter or chained receipt mismatch")
            previous = receipt.digest
        if prepared.page_count != len(prepared.receipts):
            raise ValueError("page counter disagrees with receipts")


class ScopeVerifier:
    """Verifier 2: scope, limits, continuity and unsupported-existence assertions."""

    @staticmethod
    def verify(prepared: PreparedDelivery, goal: Goal,
               observations: Sequence[ToolObservation], *,
               answer: str | None = None) -> None:
        original = {x.call_id: x for x in observations}
        if len(original) != len(tuple(observations)):
            raise ValueError("observation IDs are not unique")
        if len(prepared.notes) > 50000 or len(prepared.refill) > 65536:
            raise ValueError("working memory exceeds bounds")
        for note in prepared.notes:
            obs = original.get(note.call_id)
            # Deliberately re-evaluate source assertions independently of
            # the IntegrityVerifier classifier and hash-chain parser.
            valid_negative = False
            if obs is not None:
                if obs.ok and isinstance(obs.payload, dict):
                    data = obs.payload
                    complete = data.get("partial") is not True and data.get("truncated") is not True
                    valid_negative = complete and (
                        data.get("status") in ("not_found", "no_results", "no_matches")
                        or (data.get("found") is False and data.get("complete") is True)
                    )
                elif not obs.ok:
                    description = (obs.error or "").lower()
                    valid_negative = (
                        bool(re.search(r"\b(?:404|not found|no matches|no results)\b", description))
                        and not any(token in description for token in (
                            "permission", "forbidden", "timeout", "unavailable",
                            "rate limit", "unauthorized"
                        ))
                    )
            if not valid_negative:
                raise ValueError("note has no independently confirmed no-found source")
            if note.scope != _scope(obs) or "do not infer global nonexistence" not in note.text:
                raise ValueError("source scope or epistemic warning was lost")
            if not note.serial.startswith("JVS-"):
                raise ValueError("note has no page serial")
        if prepared.notes and len(prepared.receipts) != len(prepared.notes) + 2:
            raise ValueError("missing continuation/audit receipt")
        if not prepared.notes and (prepared.receipts or prepared.refill):
            raise ValueError("refill has no negative search to compact")
        if answer and prepared.notes:
            # A failed scoped lookup cannot license an unqualified universal assertion.
            absolute = r"\b(?:does not exist|never existed|no such thing exists)\b"
            if re.search(absolute, answer, flags=re.IGNORECASE):
                raise ValueError("unqualified nonexistence asserted from no-found search")
        if not goal.objective.strip():
            raise ValueError("original user request must remain pinned")


def verify_delivery(prepared: PreparedDelivery, goal: Goal,
                    observations: Sequence[ToolObservation],
                    *, answer: str | None = None) -> tuple[str, str]:
    """Both separately implemented verifiers must pass before delivery."""
    IntegrityVerifier.verify(prepared, goal, observations)
    ScopeVerifier.verify(prepared, goal, observations, answer=answer)
    return (
        stable_fingerprint({"verifier": "integrity", "receipt": prepared.fingerprint}),
        stable_fingerprint({"verifier": "scope", "receipt": prepared.fingerprint, "answer": answer}),
    )
