import hashlib
import pytest
from tests.test_learned_context_encoder import build_encoder
from skeleton.retrieval.semantic_long_context import ContextualRanker,SemanticPolicy,document_spans
from skeleton.retrieval.disk_semantic_ann import DiskANNPolicy,build_generation,DiskANN


@pytest.mark.parametrize("worker_mode",["thread","process"])
def test_disk_ann_real_shard_fanout_and_scope(tmp_path,worker_mode):
    enc=build_encoder(tmp_path)
    ranker=ContextualRanker(enc,SemanticPolicy(context_chars=128,min_cosine=.2))
    root=tmp_path/"index";root.mkdir(mode=0o700)
    spans=[]
    for i in range(24):
        text="cat" if i%2 else "motor"
        spans.extend(document_spans("source-"+str(i),hashlib.sha256(text.encode()).hexdigest(),
                   text,[(0,0,len(text),text)],ranker.policy))
    policy=DiskANNPolicy(shards=4,workers=2,worker_mode=worker_mode,bands=4,bits=6,probes=4,bucket_limit=32,global_candidate_limit=8)
    rows=((s,enc.spans(s.context,[(s.local_start,s.local_end)])[0]) for s in spans)
    made=build_generation(root,"generation",rows,space=ranker.identity,source_snapshot="a"*64,dimension=3,policy=policy)
    index=DiskANN(root/"generation",made["manifest_sha256"],expected_space=ranker.identity,expected_snapshot="a"*64)
    hits,receipt=index.search("feline",enc.query("feline").dense,limit=4)
    assert len(hits)==4 and all(int(h.source_id.split("-")[1])%2 for h in hits)
    assert receipt["shards_searched"]==4 and receipt["worker_mode"]==worker_mode and receipt["citation_authorized"] is False
    scoped,_=index.search("feline",enc.query("feline").dense,allowed_source_ids=["source-1"])
    assert scoped and all(h.source_id=="source-1" for h in scoped)
    with pytest.raises(ValueError,match="identity"):
        DiskANN(root/"generation",made["manifest_sha256"],expected_space=ranker.identity,expected_snapshot="b"*64)
    path=root/"generation"/"shard-000.sqlite"
    with path.open("ab") as stream:stream.write(b"changed")
    with pytest.raises(OSError,match="changed"):
        index.search("feline",enc.query("feline").dense)


def test_candidate_chunk_reader_preserves_order_and_detects_missing_rows():
    import sqlite3
    import time
    index=object.__new__(DiskANN)
    with sqlite3.connect(":memory:") as db:
        db.execute("CREATE TABLE leaves(id INTEGER PRIMARY KEY,span,source,revision,ordinal,start,end,vector)")
        db.executemany("INSERT INTO leaves VALUES(?,?,?,?,?,?,?,?)",
            ((i,str(i),"src","rev",i,0,1,b"v") for i in range(300)))
        calls=[]
        db.set_trace_callback(calls.append)
        order=list(range(299,-1,-1))
        rows=list(index._candidate_rows(db,order,time.monotonic()+30))
        assert [rid for rid,row in rows]==order
        assert all(row[0]==str(rid) for rid,row in rows)
        assert len([x for x in calls if x.startswith("SELECT")])==3
        with pytest.raises(ValueError,match="missing"):
            list(index._candidate_rows(db,[2,999],time.monotonic()+30))
        with pytest.raises(TimeoutError,match="deadline"):
            list(index._candidate_rows(db,[1],time.monotonic()-1))
