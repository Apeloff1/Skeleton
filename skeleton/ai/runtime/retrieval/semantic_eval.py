"""Paired independent local retrieval evaluation (no generated answer judgments)."""
from __future__ import annotations
from collections import Counter,defaultdict
import hashlib
import math
import statistics
import time

from .semantic_long_context import ContextualRanker,SemanticSpan,terms
from .learned_embeddings import _digest


def _lexical(query,spans,limit):
    q=set(terms(query))
    rows=[Counter(terms(row.text)) for row in spans]
    df=Counter(t for row in rows for t in q.intersection(row))
    n=len(rows)
    avg=sum(sum(row.values()) for row in rows)/max(1,n) or 1
    scores=[]
    for i,row in enumerate(rows):
        length=sum(row.values())
        score=sum(math.log(1+(n-df[t]+.5)/(df[t]+.5))*row[t]*2.2/
                  (row[t]+1.2*(.25+.75*length/avg)) for t in q if row[t])
        if score>0:scores.append((i,score))
    return [spans[i] for i,_ in sorted(scores,key=lambda x:(-x[1],spans[x[0]].identity))[:limit]]


def _key(span):
    return (span.source_id,span.ordinal)


def _metrics(rows,expected,k):
    found=[_key(row) for row in rows]
    if len(found)!=len(set(found)):
        raise ValueError("duplicate ranked evidence")
    binary=[int(key in expected) for key in found]
    discounts=sum(hit/math.log2(i+2) for i,hit in enumerate(binary))
    ideal=sum(1/math.log2(i+2) for i in range(min(k,len(expected))))
    return {"recall":sum(binary)/len(expected),"precision":sum(binary)/k,
            "mrr":next((1/(i+1) for i,hit in enumerate(binary) if hit),0.0),
            "ndcg":discounts/ideal,"all_required":all(key in found for key in expected)}


def evaluate(ranker,spans,questions,*,holdout_sha256,k=5,repeats=2,cache=None,interrupt=None):
    """A complete measurement matrix, with paired lexical baseline and relevance labels.

    Labels are operator-supplied (not an independent third-party benchmark).
    Every expected key must be present in the exact admitted source corpus.
    No question, source text or answer text is emitted into the receipt.
    """
    if not isinstance(ranker,ContextualRanker) or not 1<=len(spans)<=ranker.policy.max_spans:
        raise ValueError("bounded pinned semantic corpus required")
    if not isinstance(holdout_sha256,str) or len(holdout_sha256)!=64 or any(c not in "0123456789abcdef" for c in holdout_sha256):
        raise ValueError("exact holdout digest required")
    if type(k) is not int or not 1<=k<=min(64,ranker.policy.candidate_pool) or type(repeats) is not int or not 1<=repeats<=5:
        raise ValueError("invalid retrieval measurement bounds")
    if not isinstance(questions,list) or not 1<=len(questions)<=256 or len(questions)*repeats>1024:
        raise ValueError("retrieval holdout ceiling exceeded")
    corpus={}
    for span in spans:
        if not isinstance(span,SemanticSpan) or _key(span) in corpus:
            raise ValueError("invalid or duplicate corpus span")
        corpus[_key(span)]=span
    seen=set()
    qseen=set()
    validated=[]
    for row in questions:
        if not isinstance(row,dict) or set(row)!={"id","question","group","expected"}:
            raise ValueError("invalid retrieval holdout row")
        if any(not isinstance(row[v],str) or not row[v].strip() for v in ("id","question","group")) or len(row["id"])>128 or len(row["group"])>64 or len(row["question"].encode())>16384:
            raise ValueError("invalid holdout identity/text")
        if not isinstance(row["expected"],list) or not 1<=len(row["expected"])<=64:
            raise ValueError("bounded positive relevance labels required")
        if any(not isinstance(x,list) or len(x)!=2 or not isinstance(x[0],str) or type(x[1]) is not int for x in row["expected"]):
            raise ValueError("invalid relevance key")
        expected={tuple(x) for x in row["expected"]}
        query_hash=hashlib.sha256(row["question"].encode()).hexdigest()
        if len(expected)!=len(row["expected"]) or not expected.issubset(corpus) or row["id"] in seen or query_hash in qseen:
            raise ValueError("duplicate or absent holdout relevance")
        seen.add(row["id"]);qseen.add(query_hash)
        overlap=any(set(terms(row["question"]))&set(terms(corpus[x].text)) for x in expected)
        validated.append((row,expected,overlap))
    measurements=[]
    for repeat in range(repeats):
        for row,expected,overlap in validated:
            if interrupt:interrupt()
            data={}
            order=("lexical","semantic") if repeat%2==0 else ("semantic","lexical")
            for method in order:
                started=time.perf_counter()
                if method=="semantic":
                    ranked,proof=ranker.search(row["question"],spans,limit=k,cache=cache,interrupt=interrupt)
                    hits=[item for item,_ in ranked]
                    calls=proof.get("encoded_calls")
                else:
                    hits=_lexical(row["question"],spans,k)
                    calls=None
                elapsed=time.perf_counter()-started
                data[method]={"metrics":_metrics(hits,expected,k),"seconds":elapsed,
                              "ranked_sha256":[x.identity for x in hits],"encoder_calls":calls}
            measurements.append({"case_sha256":_digest(row["id"]),"group_sha256":_digest(row["group"]),
                                 "lexical_overlap":overlap,"repeat":repeat,**data})
    def summarize(items):
        result={}
        for method in ("lexical","semantic"):
            vals=[r[method] for r in items]
            latency=sorted(r["seconds"] for r in vals)
            result[method]={m:statistics.mean(r["metrics"][m] for r in vals)
                            for m in ("recall","precision","mrr","ndcg","all_required")}
            result[method].update(median_seconds=statistics.median(latency),p95_seconds=latency[math.ceil(.95*len(latency))-1])
        return result
    groups=defaultdict(list)
    for r in measurements:
        groups[r["group_sha256"]].append(r)
    nonoverlap=[r for r in measurements if not r["lexical_overlap"]]
    report={"schema":"skeleton.semantic-holdout.v1","ranker_sha256":ranker.identity,
            "operator_holdout_sha256":holdout_sha256,"corpus_sha256":_digest(sorted(x.identity for x in spans)),
            "k":k,"repeats":repeats,"cases":len(questions),"aggregate":summarize(measurements),
            "no_lexical_overlap":summarize(nonoverlap) if nonoverlap else None,
            "groups":{key:summarize(rows) for key,rows in sorted(groups.items())},
            "rows":measurements,"activation_authorized":False,"external_quality_certified":False}
    report["report_sha256"]=_digest(report)
    return report
