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
