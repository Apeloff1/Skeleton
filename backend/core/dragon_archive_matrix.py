"""Multi-objective historical evidence matrix, one exact source pass per session.

Queries share grant revalidation, immutable source hashing and request-local
lexical features. All routing is approximate; no raw text, permanent model
context, training permission or live fact is returned by this operation.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import math
import heapq

from core.dragon_archive_intelligence import ArchiveWork
from skeleton.ai.webcrawler import dragon_archive_scale as a
from skeleton.ai.webcrawler.dragon_archive_grant import archive_expiry

MAX_QUERIES=100
MAX_SOURCES=64
MAX_PAYLOADS=128
MAX_WITNESSES=4
MAX_PAGE=32
MAX_RESULT_EDGES=4096


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


class MatrixAccumulator:
    """Stream verified session results into a compact payload/objective matrix.

    Every source row contributes exact witnesses, but only the strongest
    objective record and four representative witnesses survive in memory.
    No hit body, query string or redundant witness list is persisted.
    """
    def __init__(self,prepared):
        if not 1<=len(prepared)<=MAX_QUERIES:
            raise ValueError("archive matrix objective bounds")
        self.prepared=prepared
        self.ids={x["id"]:i for i,x in enumerate(prepared)}
        if len(self.ids)!=len(prepared):raise ValueError("duplicate objective identity")
        self.payloads={}
        self.rows=0
        self.earliest_expiry=None

    def add(self,matches):
        if self.rows+len(matches)>MAX_PAGE*MAX_SOURCES:
            raise ValueError("archive matrix source bound")
        for item in matches:
            self.rows+=1
            p=self.payloads.setdefault(item["payload"],{"witnesses":[],"objectives":{},"count":0})
            p["count"]+=1
            w=tuple(item[k] for k in ("session_id","source_id","version","snapshot_digest",
                                     "valid_until","captured_at","policy_version"))
            if self.earliest_expiry is None or w[4]<self.earliest_expiry:self.earliest_expiry=w[4]
            p["witnesses"].append(w)
            p["witnesses"].sort(key=lambda r:(-r[5],r[0],r[1]))
            del p["witnesses"][MAX_WITNESSES:]
            for match in item["objectives"]:
                if match["objective_id"] not in self.ids:raise ValueError("unbound matrix objective")
                i=self.ids[match["objective_id"]]
                old=p["objectives"].get(i)
                record=(match["score"],match["matched_terms"],match["term_frequency"],match["coverage"],w)
                if old is None or record[:2]>old[:2]:p["objectives"][i]=record

    @staticmethod
    def _witness(row):
        return dict(zip(("session_id","source_id","version","snapshot_digest",
                         "valid_until","captured_at","policy_version"),row))

    def result(self,*,limit):
        if type(limit) is not int or not 1<=limit<=MAX_PAYLOADS:
            raise ValueError("archive matrix result bound")
        size=len(self.prepared);coverage=[0.]*size
        scores={key:round(sum(r[0] for r in value["objectives"].values())/size,8)
                for key,value in self.payloads.items()}
        def priority(key):
            rows=self.payloads[key]["objectives"]
            gain=sum(max(0.,r[0]-coverage[i]) for i,r in rows.items())/size
            return -round(.65*gain+.35*scores[key],12)
        # Marginal gain can only decrease as objective coverage increases.
        # A lazy max-heap recomputes the top stale bound before selecting,
        # retaining exact greedy semantics without repeated full-pool scans.
        heap=[(priority(key),key,0) for key in self.payloads]
        heapq.heapify(heap)
        selected=[];edges=0;epoch=0;evaluations=len(heap);edge_truncated=False
        while heap and len(selected)<limit:
            bound,key,seen=heapq.heappop(heap)
            p=self.payloads[key];rows=p["objectives"]
            if edges+len(rows)>MAX_RESULT_EDGES:
                edge_truncated=True;continue
            if seen!=epoch:
                heapq.heappush(heap,(priority(key),key,epoch));evaluations+=1
                continue
            objectives=[]
            for i,row in sorted(rows.items(),key=lambda x:self.prepared[x[0]]["id"]):
                score,matched,frequency,cov,witness=row
                coverage[i]=max(coverage[i],score)
                objectives.append({"objective_id":self.prepared[i]["id"],"matched_terms":matched,
                    "term_frequency":frequency,"coverage":cov,"score":score,"best_witness":self._witness(witness)})
            selected.append({"payload":key,"witnesses":[self._witness(w) for w in p["witnesses"]],
                "objectives":objectives,"witness_count":p["count"],"score":scores[key],
                "independent_corroboration_verified":False})
            edges+=len(rows);epoch+=1
        return {"payloads":selected,"matching_payloads":len(self.payloads),
                "objectives":[{"objective_id":query["id"],"estimated_coverage":round(coverage[i],8)}
                              for i,query in enumerate(self.prepared)],
                "result_truncated":len(selected)<len(self.payloads),"coverage_is_estimated":True,
                "objective_edges_returned":edges,"objective_edge_limit":MAX_RESULT_EDGES,
                "objective_edge_limit_reached":edge_truncated,
                "candidate_score_evaluations":evaluations}


def fuse(prepared,matches,*,limit):
    accumulator=MatrixAccumulator(prepared)
    accumulator.add(matches)
    return accumulator.result(limit=limit)
