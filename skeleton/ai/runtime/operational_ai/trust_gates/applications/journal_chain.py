"""Independent deterministic journal chain verifier for pre-read event records.

Unlike the lightweight journal gate, this module recomputes the hash of each
event and binds the actual predecessor, sequence, stream and epoch.
"""
from __future__ import annotations
import hashlib
from ..contracts import canonical,fail
from ..engine import validate

def journal_digest(*, stream, sequence, epoch, kind, payload_sha, prev_sha):
    canonical_record={"schema":"trust-journal-event.v1","stream":stream,
                      "sequence":sequence,"epoch":epoch,"kind":kind,
                      "payload_sha":payload_sha,"prev_sha":prev_sha}
    return hashlib.sha256(canonical(canonical_record)).hexdigest()

def verify_chain(records, *, stream, epoch, maximum=10000):
    if type(maximum) is not int or not 1<=maximum<=10000:
        fail("bad audit verification limit")
    expected="0"*64
    seen=0
    for record in records:
        seen+=1
        if seen>maximum or type(record) is not dict:
            fail("audit chain unbounded")
        if set(record)!={"stream","sequence","epoch","kind","payload_sha","prev_sha","event_sha"}:
            fail("audit record fields invalid")
        if record["stream"]!=stream or record["epoch"]!=epoch:
            fail("audit stream or epoch fork")
        if record["sequence"]!=seen or record["prev_sha"]!=expected:
            fail("audit sequence/parent fork")
        validate("journal",record)
        observed=journal_digest(stream=stream,sequence=seen,epoch=epoch,
                                kind=record["kind"],payload_sha=record["payload_sha"],
                                prev_sha=expected)
        if observed!=record["event_sha"]:
            fail("audit content hash mismatch")
        expected=observed
    if not seen: fail("no events in chain")
    return {"schema":"trust-journal-verified.v1","stream":stream,
            "epoch":epoch,"events":seen,"head_sha256":expected}
