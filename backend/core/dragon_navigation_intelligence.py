"""Budget-aware deliberation over owner-authorized navigation metadata.

Jeeves decomposes an objective into independently measurable facets.
Dragon balances coverage, novelty, historical uncertainty and exploration.
No plan changes grants, review state, robots, host policy or network authority.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import math
import re
from urllib.parse import unquote,urlsplit

from core import dragon_navigation_graph as graph
from skeleton.ai.webcrawler.navigation_semantics import (
    words,concepts,CONCEPTS,semantic_features,digest,
)

MAX_FACETS=8
MAX_POOL=144
MAX_BUDGET=48
MAX_PRIOR=128
STOP=frozenset({"the","and","for","with","from","into","about","what","how","can","does",
                "have","that","this","which","where","when","all","find","research","show"})


def objective_facets(query):
    if not isinstance(query,str) or not query.strip() or len(query)>512:
        raise ValueError("research objective bounds")
    # Preserve objective phrases and concept groups rather than inventing
    # factual requirements. Facets are search hypotheses only.
    parts=re.split(r"[,;!?\n]+|\b(?:and|versus|vs|plus)\b",query.casefold())
    result=[];seen=set()
    for part in parts:
        terms=tuple(t for t in words(part) if t not in STOP)
        if not terms:
            continue
        for group in (terms, *((t,) for t in terms if len(terms)>2)):
            tag=tuple(sorted(concepts(group)))
            key=(group,tag)
            if key in seen:continue
            seen.add(key)
            result.append({"id":digest([group,tag])[:16],"terms":list(group),
                           "concepts":list(tag),"query":" ".join(group)})
            if len(result)>=MAX_FACETS:break
        if len(result)>=MAX_FACETS:break
    if not result:
        terms=words(query)
        if not terms:raise ValueError("research objective has no terms")
        result=[{"id":digest(terms)[:16],"terms":list(terms),"concepts":[],
                 "query":" ".join(terms)}]
    return result


def _coverage(facet,url):
    f=semantic_features(facet["query"],url)
    return min(1.,.50*f["exact"]+.35*f["concept"]+.15*f["trigram"])


def _bounded_feedback(feedback):
    settled=sum(feedback["phases"].get(k,0) for k in
        ("captured","duplicate","discovered","rejected","retry","error","restricted"))
    # Beta(1,1) prior, with uncertainty widest when facts are scarce.
    good=feedback["phases"].get("captured",0)+feedback["phases"].get("discovered",0)
    bad=max(0,settled-good)
    a,b=1+good,1+bad
    mean=a/(a+b)
    sigma=math.sqrt(a*b/((a+b)**2*(a+b+1)))
    downside=feedback["phases"].get("rejected",0)+feedback["phases"].get("error",0)+feedback["phases"].get("restricted",0)
    cost=1+int(downside>=2)+int(feedback["phases"].get("retry",0)>=2)
    return mean,sigma,cost,settled


def plan(db,owner,*,query,now,budget=16,mode="balanced",previous=None,learned=False,campaign_id=None,initial_coverage=None,exploration_round=0):
    if type(learned) is not bool:raise ValueError("learned semantics flag")
    if type(budget) is not int or not 1<=budget<=MAX_BUDGET:
        raise ValueError("research advisory budget")
    if mode not in {"balanced","coverage","exploration","conservation"}:
        raise ValueError("research advisory mode")
    previous=[] if previous is None else previous
    if not isinstance(previous,list) or len(previous)>MAX_PRIOR or len(set(previous))!=len(previous):
        raise ValueError("research prior selection bound")
    old={graph._id(x) for x in previous}
    facets=objective_facets(query)
    if type(exploration_round) is not int or not 0<=exploration_round<=128:raise ValueError("research round bound")
    epoch=int(now)//3600
    if initial_coverage is not None and (not isinstance(initial_coverage,list) or len(initial_coverage)!=len(facets)
            or any(type(x) not in (int,float) or not 0<=x<=1 for x in initial_coverage)):
        raise ValueError("research coverage bound")
    # A global retrieval lane and bounded sub-objectives compete rather
    # than taking the first large lexical bucket repeatedly.
    pool={};truncated=False;incomplete=False
    for ix,text in enumerate([query]+[x["query"] for x in facets]):
        page=graph.retrieve(db,owner,query=text,now=now,limit=24,per_term=24,
                            due_only=True,exploration_epoch=epoch*129+exploration_round+ix if campaign_id is not None else epoch+ix,
                            campaign_id=campaign_id)
        truncated|=page["lane_truncated"];incomplete|=page["index_backfill_pending"]
        for row in page["targets"]:
            if row["id"] in old:continue
            prior=pool.get(row["id"])
            if prior is None or row["score"]>prior["score"]:
                pool[row["id"]]=row
    candidates=sorted(pool.values(),key=lambda x:(-x["score"],x["id"]))[:MAX_POOL]
    truncated|=len(pool)>len(candidates)
    for row in candidates:
        feedback=graph.outcomes(db,owner,row["id"],now=now)
        mean,sigma,cost,settled=_bounded_feedback(feedback)
        parent=graph.neighbors(db,owner,row["id"],direction="parents",limit=4,now=now)
        row.update(coverage=[_coverage(f,row["url"]) for f in facets],
                   feedback=feedback,mean=mean,sigma=sigma,cost=cost,
                   settled=settled,lineage=min(1,len(parent["neighbors"])/4),
                   terms=set(words(unquote(urlsplit(row["url"]).path,errors="replace"))))
    learning=None;dense={};calibrated={}
    if learned:
        from core.dragon_navigation_learning import dense_scores,calibrate
        from core.dragon_local_embeddings import EmbeddingHeld
        dense_receipt={"status":"empty_pool"}
        if candidates:
            try:dense,dense_receipt=dense_scores(query,candidates)
            except (EmbeddingHeld,ValueError,RuntimeError,OSError):
                dense_receipt={"status":"local_encoder_held","source_bodies_encoded":False}
        for row in candidates:
            if row["id"] in dense:row["dense_similarity"]=dense[row["id"]]
        calibrated,fit_receipt=calibrate(candidates,query)
        learning={"dense":dense_receipt,"calibration":fit_receipt}
    weights={"balanced":(.62,.38),"coverage":(.82,.18),
             "exploration":(.42,.58),"conservation":(.78,.22)}[mode]
    selected=[];host_counts=Counter();coverage=list(initial_coverage) if initial_coverage is not None else [0.]*len(facets);remaining=budget
    while remaining and candidates and len(selected)<24:
        proposals=[]
        for row in candidates:
            if row["cost"]>remaining:continue
            novelty=sum(max(0.,score-covered) for score,covered in zip(row["coverage"],coverage))/len(facets)
            relevance=sum(row["coverage"])/len(facets)
            redundancy=max((len(row["terms"] & chosen["terms"])/max(1,len(row["terms"] | chosen["terms"]))
                            for chosen in selected),default=0.)
            expected=.48*novelty+.22*relevance+.20*row["mean"]+.10*row["lineage"]
            if row["id"] in dense:expected=.85*expected+.15*dense[row["id"]]
            if row["id"] in calibrated:expected=.90*expected+.10*calibrated[row["id"]]
            exploration=.35*min(1.,row["sigma"]*3)+.30/(1+host_counts[row["host"]])+                         .20*row["feedback"]["exploration_prior"]+.15/(1+row["settled"])
            joint=(weights[0]*expected+weights[1]*exploration-.20*redundancy)/row["cost"]
            if mode=="conservation":joint*=row["mean"]
            proposals.append((joint,row["id"],expected,exploration,novelty,redundancy,row))
        if not proposals:break
        score,_,jeeves,dragon,novelty,redundancy,row=min(proposals,key=lambda x:(-x[0],x[1]))
        candidates.remove(row);selected.append(row)
        host_counts[row["host"]]+=1;remaining-=row["cost"]
        coverage=[max(a,b) for a,b in zip(coverage,row["coverage"])]
        row["decision"]={"target_id":row["id"],"url":row["url"],"host":row["host"],
            "jeeves":round(jeeves,8),"dragon":round(dragon,8),"joint":round(score,8),
            "estimated_work_units":row["cost"],"coverage_gain":round(novelty,8),
            "redundancy_penalty":round(redundancy,8),"historical_yield_prior":round(row["mean"],8),
            "historical_uncertainty":round(row["sigma"],8),"supporting_lineage":row["lineage"],
            "facet_scores":[{"id":f["id"],"score":round(v,8)} for f,v in zip(facets,row["coverage"])],
            **({"dense_similarity":round(dense[row["id"]],8)} if row["id"] in dense else {}),
            **({"calibrated_yield":round(calibrated[row["id"]],8)} if row["id"] in calibrated else {}),
            "network_authorized":False,"reviewed":False}
    body={"schema":"skeleton.dragon.navigation-plan.v1","mode":mode,"epoch":epoch,
        "facets":[{"id":f["id"],"terms":f["terms"],"concepts":f["concepts"],
                   "estimated_coverage":round(v,8)} for f,v in zip(facets,coverage)],
        "targets":[r["decision"] for r in selected],"budget":budget,"remaining":remaining,
        "distinct_hosts":len(host_counts),"excluded_prior_targets":len(old),
        **({"campaign_id":campaign_id,"exploration_round":exploration_round,"initial_coverage":initial_coverage} if campaign_id is not None else {}),
        "pool_truncated":truncated,"index_backfill_pending":incomplete,
        "objective_coverage_is_estimated":True,"cost_is_advisory":True,
        "network_authorized":False,"training_permission":False,
        **({"learning":learning} if learning is not None else {})}
    return {**body,"receipt":digest(body)}
