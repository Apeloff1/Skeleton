from tests.test_learned_context_encoder import build_encoder
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy,document_spans
import hashlib


def test_semantic_excerpt_finds_late_paraphrase(tmp_path):
    enc=build_encoder(tmp_path)
    rank=ContextualRanker(enc,SemanticPolicy(context_chars=640,min_cosine=.2))
    text="motor "*40+"cat "*12
    pin=hashlib.sha256(text.encode()).hexdigest()
    row=list(document_spans("source",pin,text,[(0,0,len(text),text)],rank.policy))[0]
    left,right=rank.evidence_excerpt("feline",row,max_chars=64)
    assert "cat" in text[left:right] and right-left==64
    assert left>0
