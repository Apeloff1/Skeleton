"""Local learned semantic ranking and telemetry-only calibration.

The pinned encoder sees only objective terms and admitted public locator
path terms. Operational labels are active-grant acquisition outcomes, not
source bodies, human relevance judgments or model training permission.
The calibrated classifier is transient and never persisted across owners.
"""
from __future__ import annotations

import hashlib
import math
from urllib.parse import urlsplit,unquote

from skeleton.ai.webcrawler.navigation_semantics import words,semantic_features


MAX_ROWS=144
MAX_STEPS=80
MAX_DIMENSIONS=1024
MIN_LABELS=12


def _unit(value):
    return min(1.,max(0.,value))


def _features(row,query):
    semantic=semantic_features(query,row["url"])
    return (1.,semantic["exact"],semantic["concept"],semantic["trigram"],
            _unit(row.get("lineage",0)),_unit(row.get("dense_similarity",0)))


def _sigmoid(x):
    return 1/(1+math.exp(-max(-30.,min(30.,x))))


def _predict(weights,features):
    return _sigmoid(sum(a*b for a,b in zip(weights,features)))


def _labels(row):
    phases=row["feedback"]["phases"]
    good=phases.get("captured",0)+phases.get("discovered",0)
    bad=phases.get("rejected",0)+phases.get("error",0)+phases.get("restricted",0)
    # Retry and duplicate are ambiguous; do not manufacture negative labels.
    return min(good,8),min(bad,8)


def _loss(weights,records):
    total=mass=0.
    for features,good,bad in records:
        p=min(1-1e-9,max(1e-9,_predict(weights,features)))
        total-=good*math.log(p)+bad*math.log1p(-p)
        mass+=good+bad
    return total/max(1.,mass)


def _fit(records):
    weights=[0.]*6
    mass=sum(g+b for _,g,b in records)
    for step in range(MAX_STEPS):
        grad=[0.]*6
        for features,good,bad in records:
            error=(good+bad)*_predict(weights,features)-good
            for i,x in enumerate(features):grad[i]+=error*x
        rate=.35/(1+step/40)
        for i in range(len(weights)):
            weights[i]=max(-8.,min(8.,weights[i]-rate*(grad[i]/max(1,mass)+(.04*weights[i] if i else 0))))
    return weights


def calibrate(rows,query):
    if len(rows)>MAX_ROWS:
        raise ValueError("learning candidate bound")
    train=[];holdout=[]
    for row in rows:
        good,bad=_labels(row)
        if not good+bad:continue
        record=(_features(row,query),good,bad)
        # Split by immutable target identity, never by occurrence; all labels
        # on one target remain in one partition.
        (holdout if int(row["id"][:8],16)%5==0 else train).append(record)
    total_good=sum(r[1] for r in train);total_bad=sum(r[2] for r in train)
    receipt={"status":"insufficient_outcomes","training_targets":len(train),
        "holdout_targets":len(holdout),"holdout_log_loss":None,"baseline_log_loss":None,
        "telemetry_only":True,"persisted":False,"production_quality_verified":False}
    if len(train)<MIN_LABELS or len(holdout)<4 or min(total_good,total_bad)<4:
        return {},receipt
    weights=_fit(train)
    prior=(total_good+1)/(total_good+total_bad+2)
    baseline=[math.log(prior/(1-prior)),0,0,0,0,0]
    measured=_loss(weights,holdout);reference=_loss(baseline,holdout)
    receipt.update(holdout_log_loss=round(measured,8),baseline_log_loss=round(reference,8))
    if measured>=reference:
        receipt["status"]="baseline_retained"
        return {},receipt
    receipt["status"]="heldout_improvement"
    return {row["id"]:_predict(weights,_features(row,query)) for row in rows},receipt


def _normalized(value,dimensions):
    if (not isinstance(value,(tuple,list)) or len(value)!=dimensions
            or any(type(x) not in (float,int) or not math.isfinite(x) for x in value)):
        raise ValueError("local embedding vector invalid")
    norm=math.sqrt(sum(x*x for x in value))
    if not norm>1e-9:raise ValueError("zero embedding")
    return [x/norm for x in value]


def dense_scores(query,rows,*,model=None):
    """Run configured pinned ONNX encoder; fail closed, no remote fallback."""
    if not 1<=len(rows)<=MAX_ROWS:raise ValueError("embedding candidate bound")
    if model is None:
        from core.dragon_local_embeddings import encoder
        model=encoder()
    dims=model.dimensions
    if type(dims) is not int or not 32<=dims<=MAX_DIMENSIONS:
        raise ValueError("embedding dimension")
    query_text=" ".join(words(query))
    if not query_text:raise ValueError("empty semantic objective")
    q=_normalized(model.encode([query_text])[0],dims)
    unique={}
    for row in rows:
        # No query parameters, source title/body, arbitrary instructions,
        # user credentials or destination are supplied to the encoder.
        parsed=urlsplit(row["url"])
        text=" ".join(words(unquote(parsed.path,errors="replace"))) or "public reference"
        unique.setdefault(text,[]).append(row["id"])
    items=list(unique);result={};calls=1
    for offset in range(0,len(items),8):
        batch=items[offset:offset+8]
        vectors=model.encode(batch);calls+=1
        if len(vectors)!=len(batch):raise ValueError("embedding batch mismatch")
        for text,value in zip(batch,vectors):
            vector=_normalized(value,dims)
            score=_unit((1+sum(a*b for a,b in zip(q,vector)))/2)
            for identifier in unique[text]:result[identifier]=score
    return result,{"status":"encoded","model_digest":model.identity,"dimensions":dims,
        "batches":calls,"unique_locator_representations":len(items),
        "source_bodies_encoded":False,"production_quality_verified":False}
