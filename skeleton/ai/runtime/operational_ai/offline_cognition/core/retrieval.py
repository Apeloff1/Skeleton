"""Bounded lexical BM25 + dense rerank without opaque provider calls."""
from __future__ import annotations
import math
from collections import Counter
from dataclasses import dataclass
from .contracts import identifier,integer,number,refuse,sha
from .text import words
from .math import cosine,reciprocal_rank_fusion
@dataclass(frozen=True,slots=True)
class IndexedDocument:
    document_id:str
    scope:str
    source_sha256:str
    text:str
    def __post_init__(self):
        identifier(self.document_id)
        identifier(self.scope)
        sha(self.source_sha256)
        words(self.text,maximum=262144)
class BM25:
    def __init__(self,documents,*,k1=1.5,b=0.75):
        if type(documents) not in (tuple,list) or not 1<=len(documents)<=10000:
            refuse("bounded retrieval inventory required")
        self.k1=number(k1,minimum=0.01,maximum=10)
        self.b=number(b,minimum=0,maximum=1)
        self.documents={}
        self.tokens={}
        self._df_by_scope={}
        self._count_by_scope=Counter()
        self._total_lengths_by_scope=Counter()
        total_bytes=0
        for doc in documents:
            if type(doc) is not IndexedDocument or doc.document_id in self.documents:
                refuse("duplicate/invalid index document")
            total_bytes+=len(doc.text.encode("utf-8","strict"))
            if total_bytes>64*1024*1024:
                refuse("lexical source corpus exceeds 64 MiB private laptop budget")
            self.documents[doc.document_id]=doc
            counter=Counter(words(doc.text,maximum=262144))
            self.tokens[doc.document_id]=counter
            self._df_by_scope.setdefault(doc.scope,Counter()).update(counter.keys())
            self._count_by_scope[doc.scope]+=1
            self._total_lengths_by_scope[doc.scope]+=sum(counter.values())
        self._average_by_scope={
            scope:self._total_lengths_by_scope[scope]/count
            for scope,count in self._count_by_scope.items()
        }
    def search(self,query,*,scope,limit=10):
        identifier(scope)
        integer(limit,minimum=1,maximum=1000)
        query_tokens=tuple(words(query))
        if not query_tokens:refuse("search query has no terms")
        count=self._count_by_scope.get(scope,0)
        if count==0:return ()
        df=self._df_by_scope[scope]
        average=self._average_by_scope[scope]
        results=[]
        for key,doc in self.documents.items():
            if doc.scope!=scope:continue
            tokens=self.tokens[key]
            length=sum(tokens.values())
            score=0.0
            for term in set(query_tokens):
                tf=tokens.get(term,0)
                if not tf:continue
                idf=math.log(1+(count-df[term]+0.5)/(df[term]+0.5))
                denominator=tf+self.k1*(1-self.b+self.b*length/max(1,average))
                score+=idf*(tf*(self.k1+1)/denominator)
            if score>0:results.append((key,score))
        results.sort(key=lambda x:(-x[1],x[0]))
        return tuple(results[:limit])
def hybrid(lexical,dense,*,scope,max_results=10,k=60):
    identifier(scope)
    integer(max_results,minimum=1,maximum=1000)
    integer(k,minimum=1,maximum=1000)
    for ranked in (lexical,dense):
        if type(ranked) not in (tuple,list):refuse("ranked inputs required")
        if len(ranked)>10000:refuse("unbounded ranking volume")
        for item in ranked:
            if type(item) not in (tuple,list) or len(item)!=3:
                refuse("ranked row needs id, score, exact scope")
            identifier(item[0]);number(item[1],minimum=-1e12,maximum=1e12)
            if item[2]!=scope:refuse("cross-principal retrieval result")
    fused=reciprocal_rank_fusion([[x[0] for x in lexical],[x[0] for x in dense]],k=k)
    return fused[:max_results]
