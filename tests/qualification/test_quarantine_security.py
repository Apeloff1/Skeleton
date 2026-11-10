"""Recovery adversarial qualification: no synthetic release or truncated replay pass."""
from __future__ import annotations
import math
import pytest
from skeleton.qualification import parse_case
from skeleton.qualification.evidence import parse_evidence
from skeleton.qualification.errors import SchemaError
from skeleton.qualification.gates import evaluate
from skeleton.qualification.runner import run_case
from skeleton.qualification.verdict import Verdict

HEAD = "a" * 40
CASE = parse_case({"id":"GFM-FPS-77","gate":"fps","title":"FPS",
    "todo_ref":"P0","severity":"sev1","requires_hardware":True,
    "params":{"profiles":[60],"sim_hz":60,"min_ratio":0.9}})


def test_forged_device_label_cannot_satisfy_hardware_attestation():
    e = parse_evidence({"case_id":CASE.id,"head_sha":HEAD,"source":"device",
        "data":{"runs":{"60":{"frame_ms":[16.0],"sim_hz":60,"sim_state_hash":"x"}}}})
    assert run_case(CASE,e,HEAD).verdict is Verdict.BLOCKED
    assert run_case(CASE,e,HEAD,device_verifier=lambda evidence: False).verdict is Verdict.BLOCKED
    assert run_case(CASE,e,HEAD,device_verifier=lambda evidence: True).verdict is Verdict.PASS


def test_invalid_fps_and_latency_do_not_forge_green():
    params={"profiles":[60],"sim_hz":60,"min_ratio":0.9}
    for frames in ([float("nan")],[-1],[float("inf")],["16"]):
        why,_=evaluate("fps",params,{"runs":{"60":{"frame_ms":frames,
             "sim_hz":60,"sim_state_hash":"x"}}})
        assert why
    perf={"metric":"time","budgets_ms":{"p95":10.0},"min_samples":1}
    for samples in ([float("nan")],[-1.0],["3"]):
        assert evaluate("perf",perf,{"samples_ms":samples})[0]


def test_replay_rejects_short_prefix():
    original=[str(n) for n in range(25)]
    reasons,_=evaluate("replay",{"min_ticks":10},
                       {"original":original,"restored":original[5:15],"snapshot_tick":5})
    assert any("tail length" in item for item in reasons)


def test_empty_promotion_and_negative_soak_are_not_passes():
    assert evaluate("promotion",{"max_canary_regression":0.1},{"stages":[]})[0]
    params={"min_hours":24.0,"max_rss_mb_per_hour":1.0,"max_error_rate":0.1,"max_restarts":0}
    assert evaluate("soak",params,{"hours":24,"rss_mb":[2,2,2],
       "requests":-10,"errors":0,"restarts":-1})[0]


def test_evidence_rejects_nonfinite_and_bad_identity():
    base={"case_id":"GFM-X-01","head_sha":HEAD,"source":"ci","data":{"samples_ms":[1]}}
    for payload in (dict(base,data={"samples_ms":[math.nan]}),
                    dict(base,head_sha=["a"*40]),
                    dict(base,source={"device":True})):
        with pytest.raises(SchemaError):
            parse_evidence(payload)
