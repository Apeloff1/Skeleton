"""Pinned learned next-query predictor and measured cache utility.

Uses a local cross-encoder trained for next-query relevance. Candidate
questions are explicitly authorized; prediction never executes generation
or broadens document scope. Scores are uncalibrated ranking signals.
"""
from __future__ import annotations
from hashlib import sha256
import json
import math
from pathlib import Path

from skeleton.retrieval.learned_embeddings import LocalPairReranker,PairRerankerPolicy,_read_pinned
from skeleton.app.jeeves_prefetch import rank_questions,digest

MAX_CONTEXT_BYTES=4096


def load_predictor(path,pin):
    path=Path(path)
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:
                raise ValueError("duplicate forecast configuration key")
            result[k]=v
        return result
    cfg=json.loads(_read_pinned(path,pin,65536),object_pairs_hook=unique)
    if (type(cfg) is not dict or set(cfg)!={"schema","model_path","model_sha256",
             "tokenizer_path","tokenizer_sha256","policy"} or
            cfg["schema"]!="skeleton.jeeves.next-query-config.v1"):
        raise ValueError("explicit next-query predictor configuration required")
    def relative(s):
        if type(s) is not str or not s or Path(s).is_absolute() or ".." in Path(s).parts:
            raise ValueError("relative forecast artifact required")
        return path.parent/s
    return LocalPairReranker(relative(cfg["model_path"]),cfg["model_sha256"],
        relative(cfg["tokenizer_path"]),cfg["tokenizer_sha256"],PairRerankerPolicy(**cfg["policy"]))


def context_for_prediction(messages):
    """Bounded whole user-turn context, never generated assistant instructions."""
    history=[]
    bytes_used=0
    for item in reversed(messages[-16:]):
        if item["role"]!="user":
            continue
        text=item["content"].strip()
        size=len(text.encode("utf-8"))+1
        if not text or size>MAX_CONTEXT_BYTES:
            continue
        if size+bytes_used>MAX_CONTEXT_BYTES:
            break
        history.append(text);bytes_used+=size
        if len(history)>=6:
            break
    if not history:
        raise ValueError("learned forecasting needs committed user context")
    return "\n".join(reversed(history))


def learned_rank(messages,candidates,predictor):
    if not isinstance(predictor,LocalPairReranker):
        raise ValueError("pinned independent local predictor required")
    lexical=rank_questions(messages,candidates)
    # Preserve original authorization order for stable ties.
    by_index=sorted(lexical,key=lambda row:row[1])
    context=context_for_prediction(messages)
    if len(by_index)>predictor.policy.max_pairs:
        raise ValueError("prediction candidate batch exceeds configured predictor")
    scores=predictor.score(context,[row[2] for row in by_index])
    if len(scores)!=len(by_index) or any(not math.isfinite(x) or not 0<=x<=1 for x in scores):
        raise ValueError("invalid learned forecast scores")
    rows=[(round(score*1_000_000),index,query) for score,(_,index,query) in zip(scores,by_index)]
    ranked=sorted(rows,key=lambda r:(-r[0],r[1]))
    receipt={"schema":"skeleton.jeeves.learned-query-ranking.v1","predictor_identity":predictor.identity,
        "context_sha256":sha256(context.encode()).hexdigest(),
        "candidates":[{"query_sha256":sha256(q.encode()).hexdigest(),"score_ppm":s}
                      for s,_,q in ranked],
        "learned_inference_performed":True,"probabilities_calibrated":False,
        "prediction_accuracy_certified":False}
    receipt["receipt_sha256"]=digest(receipt)
    return ranked,receipt
