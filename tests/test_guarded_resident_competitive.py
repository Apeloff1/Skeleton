"""Holdout admission and guarded residency ownership regression fixtures."""
import hashlib,json
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest
from skeleton.ai.runtime.inference.competitive_holdout import Competitor, read_holdout
from skeleton.ai.runtime.inference.resident_gguf_batch import ResidentGGUFBatch,ResidentBatchPolicy
from skeleton.ai.runtime.inference.resident_guarded_gguf import ResidentGuardedGGUF
from skeleton.provider_runtime import ProviderPolicyError


def test_holdout_raw_pin_and_duplicate_prompt_rejected(tmp_path):
    path=tmp_path/"data.json"
    data=[dict(id=str(i),category="math",prompt=f"Question {i}",exact=str(i)) for i in range(4)]
    raw=json.dumps(data).encode()
    path.write_bytes(raw)
    assert read_holdout(path,hashlib.sha256(raw).hexdigest())==data
    with pytest.raises(ValueError,match="identity"):
        read_holdout(path,"0"*64)
    data[1]["prompt"]=data[0]["prompt"]
    raw=json.dumps(data).encode()
    path.write_bytes(raw)
    with pytest.raises(ValueError,match="duplicate"):
        read_holdout(path,hashlib.sha256(raw).hexdigest())
    with pytest.raises(ValueError):
        Competitor("bad label",Path("m"),"a"*64)


def test_guarded_resident_exclusive_owner_and_no_unprepared_infer():
    session=object.__new__(ResidentGGUFBatch)
    session._lock=threading.RLock()
    session._ready=threading.Event()
    session._ready.set()
    session._closed=False
    session._batches=0
    session._spill_temp=None
    session._guarded_owner=None
    session._assert_source=lambda:None
    session._policy=ResidentBatchPolicy(2,128,1,1024**3)
    session._model=SimpleNamespace(model_id="jeeves",model_digest="a"*64,execution_profile_digest="b"*64)
    session._server=SimpleNamespace(sha256="c"*64)
    session._pins=()
    backend=ResidentGuardedGGUF(session)
    with pytest.raises(ProviderPolicyError,match="fresh"):
        ResidentGuardedGGUF(session)
    with pytest.raises(ProviderPolicyError,match="prepared"):
        backend.infer(None,threading.Event())
    with pytest.raises(RuntimeError,match="guarded resident"):
        session.generate(["one","two"],max_new_tokens=1)


def test_matched_runtime_evidence_requires_token_parity_and_tail_bound():
    from skeleton.ai.runtime.inference.competitive_holdout import _runtime_summary
    def trial(label,repeat,seconds,response="same",tokens=10):
        return {"label":label,"repeat":repeat,"seconds":seconds,"cases":[
            {"case_sha256":"case","response_sha256":response,
             "exact":True,"output_tokens":tokens}]}
    data=[trial("base",0,2),trial("base",1,2),
          trial("fast",0,1),trial("fast",1,1),
          trial("drift",0,1,"different"),trial("drift",1,1),
          trial("tail",0,.1),trial("tail",1,2.1)]
    result=_runtime_summary(data,["base","fast","drift","tail"],"base",1.05,1.04)
    assert result["fast"]["eligible_for_operator_review"] is True
    assert result["fast"]["throughput_ratio"]==2
    assert result["drift"]["exact_response_parity"] is False
    assert result["drift"]["eligible_for_operator_review"] is False
    assert result["tail"]["eligible_for_operator_review"] is False
    assert result["base"]["eligible_for_operator_review"] is False
    with pytest.raises(ValueError,match="unpaired"):
        _runtime_summary(data[:-1],["base","tail"],"base",1.05,1.05)
    with pytest.raises(ValueError,match="duplicate"):
        _runtime_summary(data+[data[0]],["base","fast"],"base",1.05,1.05)


def test_runtime_variant_campaign_rejects_budget_changes_before_any_model_load(tmp_path):
    from dataclasses import replace
    from skeleton.ai.runtime.inference.competitive_holdout import compare_runtime_profiles
    model=Competitor("one",tmp_path/"manifest","a"*64)
    base=ResidentBatchPolicy(2,128,2,1024**3)
    with pytest.raises(ValueError,match="admission"):
        compare_runtime_profiles(model,tmp_path/"holdout",holdout_sha256="b"*64,
            server=tmp_path/"server",server_sha256="c"*64,
            policies={"base":base,"variant":replace(base,slots=3)},baseline="base")
    with pytest.raises(ValueError,match="distinct"):
        compare_runtime_profiles(model,tmp_path/"holdout",holdout_sha256="b"*64,
            server=tmp_path/"server",server_sha256="c"*64,
            policies={"base":base,"variant":base},baseline="base")
