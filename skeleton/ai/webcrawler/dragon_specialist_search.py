"""Bounded diversity-aware lookahead for an independently trained ranker.

The ranker predicts pair preferences from candidate metadata; this planner
uses a limited beam to avoid locally attractive but redundant sequences.
No learned output can invent a candidate or authorize a request.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from .navigation_semantics import concepts,grams,validate_packet,ROLE_GROUP,parse_rank
import json

BEAM_WIDTH=12
MAX_EVALUATIONS=384
HORIZON=4


@dataclass(frozen=True)
class Candidate:
    index:int
    terms:frozenset
    tags:frozenset
    exact:float
    related:float
    fuzzy:float
    semantic:float
    novelty:float
    depth:float
    retry:float
    first_rank:float


@dataclass(frozen=True)
class State:
    order:tuple
    terms:frozenset
    tags:frozenset
    utility:float
    decisions:tuple


def beam_rank(model,group,first):
    ids=validate_packet(group)
    if len(ids)>ROLE_GROUP:raise ValueError("specialist beam candidate bound")
    first=parse_rank(json.dumps(first),len(ids))
    q=frozenset(group["objective"]);qc=frozenset(concepts(q));qg=grams(q)
    rank={n:1/(1+i) for i,n in enumerate(first)}
    anchor=frozenset(group["candidates"][first[0]-1]["terms"])
    candidates=[]
    for i,row in enumerate(group["candidates"],1):
        terms=frozenset(row["terms"]);tags=frozenset(concepts(terms));tg=grams(terms)
        candidates.append(Candidate(i,terms,tags,len(q&terms)/max(1,len(q)),
            len(qc&tags)/max(1,len(qc)),len(qg&tg)/max(1,len(qg|tg)),
            row["semantic"]/1000,len(terms-anchor)/max(1,len(terms)),
            row["depth"]/3,row["attempts"]/3,rank.get(i,0)))
    memo={};evaluations=0
    def proposal(state,c,position):
        nonlocal evaluations
        # Feature state depends on selected membership, not order. Share
        # numeric evaluations across equivalent search prefixes.
        mask=sum(1<<(i-1) for i in state.order)
        key=(mask,c.index)
        if key not in memo:
            if evaluations>=MAX_EVALUATIONS:
                raise ValueError("specialist evaluation budget exceeded")
            features=(c.semantic,c.exact,c.related,c.fuzzy,c.novelty,c.depth,c.retry,c.first_rank,
                      len(c.terms-state.terms)/max(1,len(c.terms)),
                      len((q-state.terms)&c.terms)/max(1,len(q-state.terms)))
            score,spread=model.score_detail(features)
            if not math.isfinite(score) or not math.isfinite(spread) or not 0<=score<=1 or spread<0:
                raise ValueError("specialist numeric output")
            memo[key]=(features,score,spread);evaluations+=1
        features,score,spread=memo[key]
        # Marginal gain, not a synthetic label or expected byte count.
        lexical_gain=len((q-state.terms)&c.terms)/max(1,len(q))
        concept_gain=len((qc-state.tags)&c.tags)/max(1,len(qc))
        redundancy=max((len(c.terms&other.terms)/max(1,len(c.terms|other.terms))
                        for other in candidates if other.index in state.order),default=0.)
        relevance=.5*c.exact+.5*c.related
        gain=.72*score+.18*lexical_gain+.15*concept_gain-.14*redundancy*(1-relevance)-.06*c.retry
        # All candidates are retained in the final rank. Earlier positions
        # matter more; beam lookahead cannot create an external target.
        discount=1/math.log2(position+2)
        choice={"index":c.index,"score":round(score,10),"features":[round(x,10) for x in features],
                "ensemble_logit_spread":round(spread,10),"lexical_gain":round(lexical_gain,8),
                "concept_gain":round(concept_gain,8),"redundancy":round(redundancy,8)}
        return State((*state.order,c.index),state.terms|c.terms,state.tags|c.tags,
                     state.utility+discount*gain,(*state.decisions,choice))
    beam=[State((),frozenset(),frozenset(),0.,())]
    horizon=min(HORIZON,len(candidates))
    for position in range(horizon):
        next_states={}
        for state in beam:
            for c in candidates:
                if c.index in state.order:continue
                child=proposal(state,c,position)
                # Future state is identical for equal sets; keep the best
                # prefix, including deterministic tie-breaking.
                key=tuple(sorted(child.order))
                prior=next_states.get(key)
                if prior is None or (-child.utility,child.order)<(-prior.utility,prior.order):
                    next_states[key]=child
        beam=sorted(next_states.values(),key=lambda state:(-state.utility,state.order))[:BEAM_WIDTH]
    best=beam[0]
    # Complete the tail with bounded greedy marginal ordering.
    while len(best.order)<len(candidates):
        best=min((proposal(best,c,len(best.order)) for c in candidates if c.index not in best.order),
                 key=lambda state:(-state.utility,state.order))
    if set(best.order)!=set(range(1,len(ids)+1)):
        raise ValueError("specialist ranking identity")
    return list(best.order),list(best.decisions),{
        "planner":"bounded_marginal_beam_v1","beam_width":BEAM_WIDTH,"lookahead":horizon,
        "numeric_evaluations":evaluations,"evaluation_limit":MAX_EVALUATIONS,
        "estimated_objective_coverage":round(len(q&best.terms)/max(1,len(q)),8),
        "estimated_concept_coverage":round(len(qc&best.tags)/max(1,len(qc)),8),
        "utility_estimate":round(best.utility,8),
        "network_authorized":False}
