"""Predictive local retrieval prefetch, exact scoped reuse, and bounded LRU.

Predictions rank operator-approved candidate questions from recent dialogue.
Only explicitly selected source documents are read. No speculative writes,
network, model generation, or automatic query submission. Reuse must verify
the entire selected source snapshot and exact question/session/revision key.
"""
from __future__ import annotations

from collections import OrderedDict,Counter
from hashlib import sha256
import json
import re
import threading
import time
import unicodedata

from skeleton.app.offline_grounding import normalized_document_scope, _citation

MAX_CANDIDATES=12
MAX_WARM=4
MAX_ENTRIES=48
MAX_CACHE_BYTES=512*1024
TTL_SECONDS=180
_WORD=re.compile(r"[^\W_]+",re.UNICODE)


def digest(value):
    return sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,
        separators=(",",":"),allow_nan=False).encode()).hexdigest()


def _words(text):
    return Counter(_WORD.findall(unicodedata.normalize("NFKC",text[:4096]).casefold())[:256])


def _query(value):
    if type(value) is not str or not value.strip() or len(value.encode("utf-8"))>1024 or "\x00" in value:
        raise ValueError("bounded explicit candidate question required")
    return value.strip()


def rank_questions(messages,candidates):
    if type(candidates) is not list or not 1<=len(candidates)<=MAX_CANDIDATES:
        raise ValueError("bounded prediction inventory required")
    candidates=[_query(x) for x in candidates]
    if len(set(candidates))!=len(candidates):
        raise ValueError("duplicate prediction query")
    prior=[row["content"] for row in messages[-16:] if row["role"]=="user"]
    context=Counter()
    for index,text in enumerate(reversed(prior[-6:])):
        weight=6-index
        context.update({word:min(count,3)*weight for word,count in _words(text).items()})
    result=[]
    for index,q in enumerate(candidates):
        words=_words(q)
        score=sum(context[token]*min(count,2) for token,count in words.items())
        result.append((score,index,q))
    return sorted(result,key=lambda x:(-x[0],x[1]))


class PredictiveReferenceCache:
    def __init__(self,library):
        self.library=library
        self._cache=OrderedDict()
        self._lock=threading.RLock()
        self._bytes=0
        self._hits=0
        self._misses=0
        self._warmups=0
        self._invalidated=0

    def _scope(self,scope):
        normalized=normalized_document_scope(scope)
        if normalized is None:
            raise ValueError("prefetch requires explicit selected local documents")
        return normalized

    def _snapshot(self,scope):
        docs,_=self.library._verified_snapshot(scope)
        return {r[0]:(r[2],r[3],r[1]) for r in docs}

    @staticmethod
    def _pin(snapshot):
        return digest(sorted((k,v[0],v[2]) for k,v in snapshot.items()))

    def _key(self,sid,revision,question,scope):
        return digest({"schema":"skeleton.jeeves.prefetch-key.v1",
            "session":sid,"revision":revision,"q":question,"scope":scope,
            "model":self.library.model_digest,"tokenizer":self.library.tokenizer_digest})

    def _evict(self,key):
        record=self._cache.pop(key,None)
        if record is not None:
            self._bytes-=record[2]

    def _prune(self):
        now=time.monotonic()
        for key in list(self._cache):
            if self._cache[key][0]<=now:
                self._evict(key)
        while len(self._cache)>MAX_ENTRIES or self._bytes>MAX_CACHE_BYTES:
            self._evict(next(iter(self._cache)))

    @staticmethod
    def _verify_hits(hits,snapshot,scope):
        if type(hits) is not list or len(hits)>3:
            raise ValueError("invalid scoped prefetch hits")
        for item in hits:
            row=_citation(item)
            source=snapshot.get(row["document_id"])
            if (row["document_id"] not in scope or source is None or source[0]!=row["document_sha256"]
                    or source[2]!=row["title"] or source[1][row["char_start"]:row["char_end"]]!=row["passage"]):
                raise ValueError("prefetch result no longer matches exact source")

    def warm(self,sid,revision,messages,candidates,scope,*,maximum_queries=2,search,recheck,predictor=None):
        scope=self._scope(scope)
        if type(maximum_queries) is not int or not 1<=maximum_queries<=MAX_WARM or not callable(search) or not callable(recheck):
            raise ValueError("invalid prefetch budget")
        forecast=None
        if predictor is None:
            ranked=rank_questions(messages,candidates)
        else:
            from skeleton.app.jeeves_learned_prefetch import learned_rank
            ranked,forecast=learned_rank(messages,candidates,predictor)
        snapshot=self._snapshot(scope)
        pin=self._pin(snapshot)
        receipts=[]
        for score,_index,question in ranked[:maximum_queries]:
            recheck()
            hits=search(question,scope)
            self._verify_hits(hits,snapshot,scope)
            current=self._snapshot(scope)
            if self._pin(current)!=pin:
                raise ValueError("source scope changed during prefetch")
            recheck()
            key=self._key(sid,revision,question,scope)
            payload=json.dumps({"snapshot":pin,"hits":hits},sort_keys=True,ensure_ascii=True,
                               separators=(",",":"),allow_nan=False)
            size=len(payload.encode())
            if size>MAX_CACHE_BYTES:
                raise ValueError("prefetch item exceeds memory ceiling")
            with self._lock:
                self._prune()
                self._evict(key)
                # Cache contains verified source excerpts only; not prompt
                # strings, credentials, generated text or arbitrary objects.
                self._cache[key]=(time.monotonic()+TTL_SECONDS,payload,size)
                self._bytes+=size
                self._warmups+=1
                self._prune()
            receipts.append({"query_sha256":sha256(question.encode()).hexdigest(),
                "prediction_score":score,"hit_count":len(hits),"source_snapshot_sha256":pin,
                "cache_key":key,"retrieval_executed":True})
        report={"schema":"skeleton.jeeves.predictive-prefetch.v1",
            "session_revision":revision,"selected_document_ids":list(scope),
            "candidate_count":len(ranked),"warmed":receipts,
            "maximum_queries":maximum_queries,"ttl_seconds":TTL_SECONDS,
            "forecast_method":"recency_weighted_lexical_candidate_ranking" if forecast is None else "pinned_neural_cross_encoder_next_query",
            "learned_forecast":forecast,
            "generation_performed":False,"network_called":False,"transcript_committed":False}
        report["receipt_sha256"]=digest(report)
        return report

    def consume(self,sid,revision,question,scope):
        if scope is None:
            return None
        scope=self._scope(scope)
        question=_query(question)
        key=self._key(sid,revision,question,scope)
        with self._lock:
            self._prune()
            record=self._cache.get(key)
            if record is None:
                self._misses+=1
                return None
            # Single use avoids stale reuse across multiple generations.
            self._evict(key)
        payload=json.loads(record[1])
        try:
            current=self._snapshot(scope)
            if payload["snapshot"]!=self._pin(current):
                with self._lock:
                    self._invalidated+=1
                return None
            self._verify_hits(payload["hits"],current,scope)
        except Exception:
            with self._lock:
                self._invalidated+=1
            raise
        with self._lock:
            self._hits+=1
        return payload["hits"]

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._bytes=0

    def stats(self):
        with self._lock:
            self._prune()
            return {"entries":len(self._cache),"bytes":self._bytes,
                    "maximum_entries":MAX_ENTRIES,"maximum_bytes":MAX_CACHE_BYTES,
                    "warmups":self._warmups,"verified_consumptions":self._hits,
                    "cache_misses":self._misses,"source_invalidations":self._invalidated,
                    "predictions_certified":False,"latency_gain_certified":False}
