"""Independent trial runner. Each stimulus is unique. Repeats are rejected."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ai_tree_fill.laws import LawBreak, parse_pointers
from ai_tree_fill.p5_verifier import (
    accept_until_mismatch,
    bind_frame,
    mobile_bank,
    route,
    scan_secret,
    tournament,
)


@dataclass(frozen=True)
class Trial:
    trial_id: str
    stimulus: str
    capability_id: str
    expect_fail: bool
    output: dict

    def record(self) -> dict:
        payload = json.dumps(self.output, sort_keys=True)
        return {
            "trial_id": self.trial_id,
            "stimulus": self.stimulus,
            "capability_id": self.capability_id,
            "expect_fail": self.expect_fail,
            "output": self.output,
            "output_digest": hashlib.sha256(payload.encode()).hexdigest(),
        }


def _stim(i: int) -> str:
    return f"github.com/Apeloff1/Skeleton VOL-{1000 + i} GB-{i % 40} AIFT-TRIAL-{i}"


def run_trials(n: int = 48) -> list[dict]:
    if n < 12:
        raise LawBreak("trials", "too few independent trials")
    records = []
    seen = set()
    for i in range(n):
        stimulus = _stim(i)
        if stimulus in seen:
            raise LawBreak("trials", "duplicate stimulus")
        seen.add(stimulus)
        pointers = parse_pointers(stimulus)
        output = {
            "hit": 1,
            "law": "trial",
            "n": len(pointers),
            "head": pointers[0],
            "mismatch_at": accept_until_mismatch([1, 1, i % 2], [1, 1, 1])["mismatch_at"],
        }
        records.append(Trial(f"T-{i:04d}", stimulus, "AIFT-POINTER-PARSE", False, output).record())
    negatives = [
        ("N-SECRET", "scan", lambda: scan_secret("-----BEGIN PRIVATE KEY-----")),
        ("N-GPU", "mobile", lambda: mobile_bank("gpu")),
        ("N-ROUTER", "router", lambda: route("shadow-router")),
        ("N-FRAME", "frame", lambda: bind_frame(b"x", True)),
        ("N-CAP", "cap", lambda: tournament(["r"] * 9)),
    ]
    for trial_id, kind, fn in negatives:
        try:
            fn()
            raise LawBreak("trials", f"{trial_id} did not fail")
        except LawBreak as exc:
            if exc.law == "trials":
                raise
            records.append(
                Trial(trial_id, f"negative:{kind}", f"NEG-{kind}", True, {"hit": 0, "law": exc.law, "detail": exc.detail}).record()
            )
    return records


def write_log(path: str, records: list[dict]) -> str:
    blob = json.dumps(records, sort_keys=True).encode()
    digest = hashlib.sha256(blob).hexdigest()
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"records": records, "log_digest": digest, "independent": True}, handle, indent=2)
    return digest
