"""Per-case actual native generation receipts, never the raw private model text."""
from __future__ import annotations
from dataclasses import dataclass
from .challenge_executor import ProbeResult
from .canonical import digest
from .errors import reject


def receipt_collection(run)->dict:
    from .challenge_runner import ChallengeRun
    if type(run) is not ChallengeRun:
        reject("receipt-run")
    data=[item.record() for item in run.results]
    if len({x["case_id"] for x in data})!=len(data):
        reject("receipt-duplicate")
    return {
        "schema":"skeleton.native-supervised.receipts.v1",
        "model_sha256":run.model_sha256,
        "challenge_source_sha256":run.source_sha256,
        "count":len(data),"data_sha256":digest(data),
        "raw_user_prompts_included":False,
        "raw_model_outputs_included":False,
        "evidence_records":data,
        "production_authorized":False,
    }
