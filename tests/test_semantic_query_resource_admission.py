import hashlib
import pytest
from tests.test_learned_context_encoder import build_encoder
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy,document_spans
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy
from skeleton.app.offline_resources import LocalResourceSnapshot,LocalResourcePressure
from skeleton.app.offline_semantic_resources import admit_semantic_fanout


def test_query_features_reused_with_exact_scope(tmp_path,monkeypatch):
    encoder=build_encoder(tmp_path)
    ranker=ContextualRanker(encoder,SemanticPolicy(context_chars=128,min_cosine=.2))
    text="cat "*20
    span=list(document_spans("source",hashlib.sha256(text.encode()).hexdigest(),text,[(0,0,len(text),text)],ranker.policy))[0]
    proof=ranker.prepare_query("feline")
    def unexpected(*args,**kwargs):raise AssertionError("duplicate query encoding")
    monkeypatch.setattr(encoder,"query",unexpected)
    rows,receipt=ranker.search("feline",[span],prepared=proof,limit=1)
    assert rows and receipt["query_feature_reused"]
    assert ranker.evidence_excerpt("feline",span,max_chars=32,prepared=proof)[1]>0
    with pytest.raises(ValueError,match="identity"):
        ranker.search("motor",[span],prepared=proof,limit=1)
    other=ContextualRanker(encoder,ranker.policy)
    with pytest.raises(ValueError,match="identity"):
        other.search("feline",[span],prepared=proof,limit=1)


def test_fanout_pressure_never_drops_shards():
    policy=DiskANNPolicy(shards=8,workers=8)
    good=LocalResourceSnapshot(16*1024**3,12*1024**3,100*1024**3,80*1024**3,16,.1)
    limited=LocalResourceSnapshot(16*1024**3,2*1024**3,100*1024**3,80*1024**3,16,.8)
    bad=LocalResourceSnapshot(16*1024**3,1024*1024,100*1024**3,80*1024**3,16,.9)
    assert admit_semantic_fanout(good,policy,384).workers==8
    plan=admit_semantic_fanout(limited,policy,384)
    assert 1<=plan.workers<8 and plan.all_shards_required
    with pytest.raises(LocalResourcePressure):admit_semantic_fanout(bad,policy,384)
