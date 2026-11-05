"""Finite, deterministic numerical primitives without numpy or GPU assumptions."""
from __future__ import annotations
import math
from .contracts import number,integer,refuse
def vector(x,*,maximum=4096):
    if type(x) not in (list,tuple) or not 1<=len(x)<=maximum:
        refuse("bounded dense vector required")
    return tuple(number(v,minimum=-1e9,maximum=1e9) for v in x)
def cosine(a,b):
    a=vector(a);b=vector(b)
    if len(a)!=len(b):refuse("embedding dimensions differ")
    norm_a=math.sqrt(sum(v*v for v in a))
    norm_b=math.sqrt(sum(v*v for v in b))
    if norm_a==0 or norm_b==0:refuse("zero vector has undefined cosine")
    return max(-1.0,min(1.0,sum(x*y for x,y in zip(a,b))/(norm_a*norm_b)))
def normalize_weights(weights):
    if type(weights) not in (tuple,list) or not 1<=len(weights)<=4096:
        refuse("bounded weight vector required")
    numbers=tuple(number(x) for x in weights)
    total=sum(numbers)
    if not math.isfinite(total) or total<=0:refuse("empty/overflow weight distribution")
    return tuple(v/total for v in numbers)
def entropy(probabilities):
    p=normalize_weights(probabilities)
    return -sum(x*math.log2(x) for x in p if x>0)
def softmax(scores,*,temperature=1.0):
    scores=vector(scores)
    temperature=number(temperature,minimum=1e-6,maximum=1000)
    offset=max(scores)
    exps=tuple(math.exp((v-offset)/temperature) for v in scores)
    return normalize_weights(exps)
def weighted_average(values,weights):
    values=vector(values);weights=normalize_weights(weights)
    if len(values)!=len(weights):refuse("weighted average dimension mismatch")
    return sum(v*w for v,w in zip(values,weights))
def reciprocal_rank_fusion(rankings,*,k=60,limit=1000):
    integer(k,minimum=1,maximum=100000)
    integer(limit,minimum=1,maximum=10000)
    if type(rankings) not in (tuple,list) or not 1<=len(rankings)<=64:
        refuse("bounded ranking sources required")
    scores={}
    for ranking in rankings:
        if type(ranking) not in (tuple,list) or len(ranking)>limit:
            refuse("ranking source is over limit")
        seen=set()
        for position,key in enumerate(ranking,1):
            if type(key) is not str or not key or len(key)>128:
                refuse("invalid ranked identity")
            if key in seen:refuse("ranking contains duplicate evidence")
            seen.add(key)
            scores[key]=scores.get(key,0.0)+1.0/(k+position)
    return tuple(sorted(scores,key=lambda key:(-scores[key],key)))
def mmr(items,query,*,similarity,lam=0.7,limit=10):
    lam=number(lam,minimum=0,maximum=1)
    integer(limit,minimum=1,maximum=1000)
    if type(items) not in (tuple,list) or len(items)>2000:
        refuse("MMR item budget exceeded")
    candidates=list(items)
    if len(set(candidates))!=len(candidates):refuse("duplicate retrieval IDs")
    selected=[]
    while candidates and len(selected)<limit:
        def score(key):
            rel=number(similarity(query,key),minimum=-1,maximum=1)
            redundancy=max((number(similarity(key,chosen),minimum=-1,maximum=1)
                            for chosen in selected),default=0)
            return lam*rel-(1-lam)*redundancy
        best=max(candidates,key=lambda key:(score(key),str(key)))
        selected.append(best);candidates.remove(best)
    return tuple(selected)
