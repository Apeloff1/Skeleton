"""Multi-objective historical evidence matrix, one exact source pass per session.

Queries share grant revalidation, immutable source hashing and request-local
lexical features. All routing is approximate; no raw text, permanent model
context, training permission or live fact is returned by this operation.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import math

from core.dragon_archive_intelligence import ArchiveWork
from skeleton.ai.webcrawler import dragon_archive_scale as a
from skeleton.ai.webcrawler.dragon_archive_grant import archive_expiry

MAX_QUERIES=10
MAX_SOURCES=64
MAX_PAYLOADS=128
MAX_WITNESSES=4
MAX_PAGE=32


def prepare(scope,queries):
    from core.dragon_hybrid_rank import route_terms
    from core.dragon_passage_index import query_keys
    if not isinstance(queries,list) or not 1<=len(queries)<=MAX_QUERIES or any(
            not isinstance(q,str) or not 1<=len(q)<=512 for q in queries):
        raise ValueError("archive matrix objective bounds")
    result=[];seen=set()
    for query in queries:
        terms,tokens=a.query_terms(scope,query)
        key=a.digest(["archive-matrix-objective",query])
        if key in seen:raise ValueError("duplicate archive matrix objective")
        seen.add(key)
        result.append({"id":key,"terms":frozenset(terms),"exact":tuple(tokens),
                       "rare":tuple(route_terms(scope,query)),"passage":tuple(query_keys(scope,query))})
    return result


def routes(prepared):
    return {lane:sorted({token for query in prepared for token in query[lane]})
            for lane in ("exact","rare","passage")}


def evaluate(snapshot,grant,policies,allowed,now,prepared,work):
    if not isinstance(work,ArchiveWork) or len(allowed)>MAX_SOURCES or not 1<=len(prepared)<=MAX_QUERIES:
        raise ValueError("archive matrix computation bounds")
    by_term=defaultdict(list)
    for i,objective in enumerate(prepared):
        for term in objective["terms"]:by_term[term].append(i)
    matches=[];checks=0
    for sid in sorted(allowed):
        source=snapshot["sources"][sid]
        policy=policies.get(sid,{"enabled":True,"version":0})
        expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],
                             source=source,policy=policy,now=now)
        if expiry is None:continue
        body=source["text"]
        if not isinstance(body,str) or hashlib.sha256(body.encode()).hexdigest()!=source["preserved_text_hash"]:
            raise ValueError("archive matrix source checksum changed")
        checks+=1
        counts=work.exact_counts(source["title"],body)
        matched=defaultdict(int);frequency=defaultdict(int)
        # Invert the objective terms first: one source feature pass for
        # all ten objectives, rather than ten passes over source payloads.
        for term in set(counts).intersection(by_term):
            for i in by_term[term]:
                matched[i]+=1;frequency[i]+=min(8,counts[term])
        objectives=[]
        for i in sorted(matched):
            objective=prepared[i]
            coverage=matched[i]/len(objective["terms"])
            score=.8*coverage+.2*min(1.,frequency[i]/max(1,8*len(objective["terms"])))
            objectives.append({"objective_id":objective["id"],"matched_terms":matched[i],
                               "term_frequency":frequency[i],"coverage":round(coverage,8),
                               "score":round(score,8)})
        if objectives:
            matches.append({"source_id":sid,"payload":source["preserved_text_hash"],
                "captured_at":source["fetched_at"],"valid_until":expiry,
                "policy_version":policy["version"],"objectives":objectives})
    return matches,checks


def fuse(prepared,matches,*,limit):
    if type(limit) is not int or not 1<=limit<=MAX_PAYLOADS or len(matches)>MAX_PAGE*MAX_SOURCES:
        raise ValueError("archive matrix fusion bounds")
    payloads={}
    qids={x["id"] for x in prepared}
    for item in matches:
        payload=payloads.setdefault(item["payload"],{"payload":item["payload"],"witnesses":[],
                  "objectives":{},"witness_count":0})
        payload["witness_count"]+=1
        witness={k:item[k] for k in ("session_id","source_id","version","snapshot_digest",
                                     "valid_until","captured_at","policy_version")}
        payload["witnesses"].append(witness)
        for match in item["objectives"]:
            key=match["objective_id"]
            if key not in qids:raise ValueError("unbound matrix objective")
            old=payload["objectives"].get(key)
            if old is None or (match["score"],match["matched_terms"])>(old["score"],old["matched_terms"]):
                payload["objectives"][key]=match
    candidates=[]
    for p in payloads.values():
        p["witnesses"].sort(key=lambda w:(-w["captured_at"],w["session_id"],w["source_id"]))
        p["witnesses"]=p["witnesses"][:MAX_WITNESSES]
        p["objectives"]=sorted(p["objectives"].values(),key=lambda x:x["objective_id"])
        p["score"]=round(sum(x["score"] for x in p["objectives"])/len(prepared),8)
        p["independent_corroboration_verified"]=False
        candidates.append(p)
    # A max-marginal selector makes facet coverage explicit. A repeated
    # payload never contributes a second independent source or score vote.
    selected=[];coverage={key:0. for key in qids}
    while candidates and len(selected)<limit:
        def key(p):
            gain=sum(max(0.,x["score"]-coverage[x["objective_id"]]) for x in p["objectives"])/len(prepared)
            return (-round(.65*gain+.35*p["score"],12),p["payload"])
        best=min(candidates,key=key);candidates.remove(best)
        for x in best["objectives"]:
            coverage[x["objective_id"]]=max(coverage[x["objective_id"]],x["score"])
        selected.append(best)
    return {"payloads":selected,"matching_payloads":len(payloads),
            "objectives":[{"objective_id":query["id"],"estimated_coverage":round(coverage[query["id"]],8)}
                          for query in prepared],
            "result_truncated":bool(candidates),"coverage_is_estimated":True}
