import sqlite3
import threading
import hashlib
from tests.test_learned_context_encoder import build_encoder
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy,document_spans
from skeleton.retrieval.semantic_vector_cache import DerivedVectorCache


def leaves(name,text,policy):
    pin=hashlib.sha256(text.encode()).hexdigest()
    return list(document_spans(name,pin,text,[(0,0,len(text),text)],policy))


def test_hybrid_semantic_no_lexical_overlap_and_persistent_cache(tmp_path):
    enc=build_encoder(tmp_path)
    policy=SemanticPolicy(context_chars=128,min_cosine=.4)
    ranker=ContextualRanker(enc,policy)
    spans=leaves("animals","cat",policy)+leaves("machinery","motor",policy)
    path=tmp_path/"derived.sqlite"
    scope="a"*64
    db=sqlite3.connect(path)
    cache=DerivedVectorCache(db,threading.RLock(),scope,dimension=3,segments=4)
    ranked,proof=ranker.search("feline",spans,limit=1,cache=cache)
    assert ranked[0][0].text=="cat" and proof["encoded_calls"]==2
    db.close()
    db=sqlite3.connect(path)
    cache=DerivedVectorCache(db,threading.RLock(),scope,dimension=3,segments=4)
    again,receipt=ranker.search("feline",spans,limit=1,cache=cache)
    assert again[0][0]==ranked[0][0] and receipt["encoded_calls"]==0
    other=DerivedVectorCache(db,threading.RLock(),"b"*64,dimension=3,segments=4)
    assert other.get(ranker.identity,spans[0].identity) is None
    db.close()


def test_exact_identifier_overrides_semantic_neighbor(tmp_path):
    enc=build_encoder(tmp_path)
    policy=SemanticPolicy(context_chars=128,min_cosine=-1)
    ranker=ContextualRanker(enc,policy)
    spans=leaves("other","feline",policy)+leaves("correct","motor TS-999",policy)
    ranked,_=ranker.search("feline TS-999",spans,limit=1)
    assert ranked[0][0].source_id=="correct"
