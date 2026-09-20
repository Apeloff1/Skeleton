"""Deep chain verification with evidence reports for OmniFabric.

``verify_chain`` on the core returns bool / raises. This module produces
structured ``ChainReport`` objects suitable for HTTP ``/fabric/verify-chain``
style surfaces (RS exposes proof as a route, not a promise).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from skeleton.kernel.omnifabric.codecs import GENESIS_HASH, sha256_hex, stable_json
from skeleton.kernel.omnifabric.errors import ChainBroken
from skeleton.kernel.omnifabric.events import FabricEvent


@dataclass
class ChainIssue:
    seq: int
    code: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "code": self.code, "detail": self.detail}


@dataclass
class ChainReport:
    ok: bool
    checked: int = 0
    genesis: str = GENESIS_HASH
    head_hash: str = GENESIS_HASH
    head_seq: int = 0
    issues: list[ChainIssue] = field(default_factory=list)
    contiguous: bool = True
    starts_at_genesis: bool = True
    content_digests_ok: int = 0
    link_ok: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "checked": self.checked,
            "genesis": self.genesis,
            "head_hash": self.head_hash,
            "head_seq": self.head_seq,
            "contiguous": self.contiguous,
            "starts_at_genesis": self.starts_at_genesis,
            "content_digests_ok": self.content_digests_ok,
            "link_ok": self.link_ok,
            "issues": [i.to_dict() for i in self.issues],
        }

    def raise_if_broken(self) -> None:
        if self.ok:
            return
        if self.issues:
            raise ChainBroken(self.issues[0].seq, self.issues[0].detail)
        raise ChainBroken(0, "chain report not ok")


def verify_events(
    events: Sequence[FabricEvent],
    *,
    require_genesis: bool = False,
    expected_prev: str | None = None,
) -> ChainReport:
    """Walk events in seq order and collect evidence."""
    report = ChainReport(ok=True)
    if not events:
        return report

    ordered = sorted(events, key=lambda e: e.seq)
    report.checked = len(ordered)
    first = ordered[0]
    report.starts_at_genesis = first.seq == 1 and first.prev_hash == GENESIS_HASH

    if require_genesis and not report.starts_at_genesis:
        report.ok = False
        report.issues.append(
            ChainIssue(first.seq, "missing_genesis", "stream does not start at genesis")
        )

    # contiguous seq check
    for a, b in zip(ordered, ordered[1:]):
        if b.seq != a.seq + 1:
            report.contiguous = False
            report.ok = False
            report.issues.append(
                ChainIssue(b.seq, "seq_gap", f"expected seq {a.seq + 1}, got {b.seq}")
            )

    prev = expected_prev if expected_prev is not None else (
        GENESIS_HASH if report.starts_at_genesis else first.prev_hash
    )
    if expected_prev is not None and first.prev_hash != expected_prev:
        report.ok = False
        report.issues.append(
            ChainIssue(
                first.seq,
                "prev_mismatch",
                f"expected prev {expected_prev}, got {first.prev_hash}",
            )
        )
        prev = first.prev_hash  # continue from actual to find further breaks

    for ev in ordered:
        if ev.prev_hash != prev:
            report.ok = False
            report.issues.append(
                ChainIssue(
                    ev.seq,
                    "prev_mismatch",
                    f"expected {prev}, got {ev.prev_hash}",
                )
            )
        else:
            report.link_ok += 1
        if ev.hash != ev.compute_hash():
            report.ok = False
            report.issues.append(
                ChainIssue(ev.seq, "content_hash", "event hash does not match its content")
            )
        else:
            report.content_digests_ok += 1
        prev = ev.hash

    report.head_hash = ordered[-1].hash
    report.head_seq = ordered[-1].seq
    return report


def merkle_root_of(events: Sequence[FabricEvent]) -> str:
    """Simple binary merkle root over event hashes (ordered by seq)."""
    leaves = [e.hash for e in sorted(events, key=lambda x: x.seq)]
    if not leaves:
        return sha256_hex("empty")
    while len(leaves) > 1:
        nxt: list[str] = []
        for i in range(0, len(leaves), 2):
            if i + 1 < len(leaves):
                nxt.append(sha256_hex(leaves[i] + leaves[i + 1]))
            else:
                nxt.append(sha256_hex(leaves[i] + leaves[i]))
        leaves = nxt
    return leaves[0]


def evidence_bundle(events: Sequence[FabricEvent]) -> dict[str, Any]:
    report = verify_events(events)
    return {
        "report": report.to_dict(),
        "merkle_root": merkle_root_of(events),
        "event_ids": [e.id for e in sorted(events, key=lambda x: x.seq)],
        "canonical_digest": sha256_hex(
            stable_json([e.to_dict() for e in sorted(events, key=lambda x: x.seq)])
        ),
    }
