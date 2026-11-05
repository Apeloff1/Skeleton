"""Unicode-aware bounded lexical normalization, passage partitioning and tokens.

Token estimates are only advisory; real model admission uses the authoritative
native tokenizer and cannot rely on these estimates as actual GGUF counts.
"""
from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass
from .contracts import text,integer,refuse,hash_bytes

_WORD=re.compile(r"\w+(?:['’]\w+)?",re.UNICODE)
_SENTENCE=re.compile(r"(?<=[.!?])\s+",re.UNICODE)

def normalize(value,*,maximum=32768):
    value=text(value,maximum=maximum)
    value=unicodedata.normalize("NFKC",value)
    if "\x00" in value:refuse("invalid normalized text")
    return " ".join(value.split())

def words(value,*,maximum=32768):
    return tuple(piece.casefold() for piece in _WORD.findall(normalize(value,maximum=maximum)))

def sentences(value,*,maximum=262144):
    value=normalize(value,maximum=maximum)
    pieces=tuple(p.strip() for p in _SENTENCE.split(value) if p.strip())
    return pieces or (value,)

@dataclass(frozen=True,slots=True)
class Passage:
    ordinal:int
    text:str
    start_word:int
    end_word:int
    sha256:str
    def __post_init__(self):
        integer(self.ordinal,maximum=1000000)
        integer(self.start_word,maximum=100000000)
        integer(self.end_word,minimum=self.start_word+1,maximum=100000000)
        if hash_bytes(self.text.encode("utf-8"))!=self.sha256:
            refuse("passage digest differs from actual bytes")

def passages(value,*,target_words=160,overlap=24,maximum_passages=1024):
    integer(target_words,minimum=16,maximum=4096)
    integer(overlap,maximum=1024)
    integer(maximum_passages,minimum=1,maximum=10000)
    if overlap>=target_words:refuse("overlap must be strictly smaller than chunk")
    tokenized=tuple(words(value,maximum=262144))
    if not tokenized:refuse("source contains no lexical content")
    result=[]
    step=target_words-overlap
    for start in range(0,len(tokenized),step):
        if len(result)>=maximum_passages:refuse("source would exceed passage bound")
        end=min(len(tokenized),start+target_words)
        piece=" ".join(tokenized[start:end])
        result.append(Passage(len(result),piece,start,end,
                              hash_bytes(piece.encode("utf-8"))))
        if end==len(tokenized):break
    return tuple(result)

def gram_frequency(value,*,width=3,maximum=32768):
    integer(width,minimum=1,maximum=12)
    tokens=words(value,maximum=maximum)
    result={}
    for i in range(max(0,len(tokens)-width+1)):
        gram=tuple(tokens[i:i+width])
        result[gram]=result.get(gram,0)+1
    return result

def near_duplicate_jaccard(a,b,*,width=3):
    left=set(gram_frequency(a,width=width))
    right=set(gram_frequency(b,width=width))
    if not left and not right:return 1.0
    return len(left&right)/max(1,len(left|right))
