import hashlib
from tests.test_learned_context_encoder import build_encoder
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy,document_spans
from skeleton.retrieval.semantic_eval import evaluate


def test_semantic_holdout_retains_paired_zero_overlap_measurements(tmp_path):
    ranker=ContextualRanker(build_encoder(tmp_path),SemanticPolicy(context_chars=128,min_cosine=.4))
    spans=[]
    for source,text in (("animals","cat"),("machinery","motor")):
        spans.extend(document_spans(source,hashlib.sha256(text.encode()).hexdigest(),text,[(0,0,len(text),text)],ranker.policy))
    questions=[{"id":"paraphrase","question":"feline","group":"zero-overlap","expected":[["animals",0]]}]
    proof=evaluate(ranker,spans,questions,holdout_sha256="a"*64,k=1,repeats=2)
    assert len(proof["rows"])==2
    assert proof["no_lexical_overlap"]["semantic"]["recall"]==1
    assert proof["no_lexical_overlap"]["lexical"]["recall"]==0
    assert proof["external_quality_certified"] is False
    assert "feline" not in repr(proof)
