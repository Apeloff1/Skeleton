import hashlib
from skeleton.retrieval.evidence_walk import EvidenceWalkPolicy,walk


def hit(doc,text,score=1):
    pin=hashlib.sha256(text.encode()).hexdigest()
    return {"document_id":doc,"title":doc,"document_sha256":pin,"chunk_index":0,"char_start":0,
            "char_end":len(text),"passage":text,"score":score,"citation":f"local:{doc}:0:{pin[:16]}"}


def test_bridge_retrieval_is_literal_bounded_and_source_linked():
    seed=hit("seed","The project contains module XA-193 for recovery.")
    second=hit("second","XA-193 restores backup state after interruption.")
    calls=[]
    def retrieve(query,limit):
        calls.append(query)
        return [seed,second] if "xa-193" in query else [seed]
    result,proof=walk("How can I recover my project?",retrieve,policy=EvidenceWalkPolicy(max_queries=4,max_hops=1))
    assert len(calls)<=4 and any("xa-193" in q for q in calls)
    assert {r["document_id"] for r in result}=={"seed","second"}
    assert proof["queries"][1]["parent_citation"]==seed["citation"]
    assert proof["semantic_entailment_verified"] is False
    assert all(q.startswith("How can I recover my project?") for q in calls)


def test_invalid_evidence_cannot_become_bridge():
    import pytest
    row=hit("seed","sample evidence")
    row["char_end"]=999
    with pytest.raises(ValueError,match="offset"):
        walk("sample",lambda *_:[row])
