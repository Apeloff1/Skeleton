"""Aggregate disjoint real-answer capture shards, not self-reported scores."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from typing import Iterable

from .jeeves_chat_quality import Case, QualificationRejected, qualify, _hash, _stable
from .jeeves_chat_eval_scenarios import inventory
from .jeeves_chat_benchmark import _strict_json, _REPORT_LIMIT

_SHA=re.compile(r"[a-f0-9]{64}\Z")
MAX_SHARDS=1024


def _read_capture(path: Path) -> tuple[dict,str]:
    with path.open("rb") as handle:
        raw=handle.read(_REPORT_LIMIT+1)
    if len(raw)>_REPORT_LIMIT:
        raise QualificationRejected("capture shard exceeds input limit")
    try:
        value=_strict_json(raw.decode("utf-8"))
    except (ValueError,UnicodeError,RecursionError):
        raise QualificationRejected("invalid capture shard encoding") from None
    if (type(value) is not dict or value.get("schema")!="skeleton.jeeves.local-benchmark-capture.v1"
            or value.get("live_endpoint_observed") is not True
            or value.get("independent_receipt_verification") is not False
            or type(value.get("captures")) is not list or type(value.get("report")) is not dict
            or not 1<=len(value["captures"])<=4000):
        raise QualificationRejected("invalid local capture shard")
    for name in ("model_digest","tokenizer_digest","protocol_digest"):
        if type(value.get(name)) is not str or not _SHA.fullmatch(value[name]):
            raise QualificationRejected("incomplete capture model/protocol identity")
    return value,sha256(raw).hexdigest()


def aggregate_shards(cases: tuple[Case,...],paths: Iterable[Path]) -> dict:
    """Regenerate each shard score from its actual captured text.

    The full expected suite is supplied independently. A missing, overlapping,
    mismatched, or duplicated shard is rejected rather than treated as a
    partial qualification. External execution receipts are still unverified.
    """
    expected=inventory(cases)
    registry={case.case_id:case for case in cases}
    if len(registry)!=len(cases):
        raise QualificationRejected("duplicate expected case identity")
    from itertools import islice
    sources=list(islice(paths,MAX_SHARDS+1))
    if not 1<=len(sources)<=MAX_SHARDS:
        raise QualificationRejected("invalid capture shard count")
    first,first_hash=_read_capture(sources[0])
    model=first["model_digest"];tokenizer=first["tokenizer_digest"];protocol=first["protocol_digest"]
    seen_cases=set();seen_inputs=set();provenance=[]

    def captures():
        for index,path in enumerate(sources):
            data,digest=(first,first_hash) if index==0 else _read_capture(path)
            if digest in seen_inputs:
                raise QualificationRejected("duplicate exact input shard")
            seen_inputs.add(digest)
            if (data["model_digest"],data["tokenizer_digest"],data["protocol_digest"])!=(model,tokenizer,protocol):
                raise QualificationRejected("incompatible shard model/tokenizer/protocol")
            ids=set()
            for row in data["captures"]:
                if type(row) is not dict or type(row.get("case_id")) is not str:
                    raise QualificationRejected("invalid captured case identity")
                ids.add(row["case_id"])
            if not ids or not ids<=registry.keys() or ids&seen_cases:
                raise QualificationRejected("unexpected or overlapping captured case inventory")
            subset=tuple(registry[key] for key in sorted(ids))
            # Require all turns of every shard case, and recompute every
            # deterministic check from answer text rather than trust scores.
            known=qualify(subset,data["captures"],model_digest=model,protocol_digest=protocol)
            if known!=data["report"]:
                raise QualificationRejected("source shard score/receipt differs from captured answers")
            if "suite_inventory" in data and data["suite_inventory"]!=inventory(subset):
                raise QualificationRejected("source shard inventory differs")
            seen_cases.update(ids)
            provenance.append({"input_sha256":digest,"report_sha256":known["report_sha256"],
                               "suite_sha256":known["suite_sha256"],"cases":known["cases"],
                               "turns":known["turns"]})
            yield from data["captures"]
        if seen_cases!=set(registry):
            raise QualificationRejected("expected full suite is incomplete")

    report=qualify(cases,captures(),model_digest=model,protocol_digest=protocol)
    if report["suite_sha256"]!=expected["suite_sha256"]:
        raise QualificationRejected("aggregate suite identity mismatch")
    del report["report_sha256"]
    report["tokenizer_digest"]=tokenizer
    report["shard_provenance"]=sorted(provenance,key=lambda x:x["input_sha256"])
    report["source_shards_rescored"]=True
    report["report_sha256"]=_hash(_stable(report))
    return report
