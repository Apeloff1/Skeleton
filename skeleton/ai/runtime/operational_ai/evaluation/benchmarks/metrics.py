"""Inspectable deterministic text, token and citation metrics (not an LLM judge)."""
from __future__ import annotations
from dataclasses import dataclass
from collections import Counter
from difflib import SequenceMatcher
import math,re,unicodedata
from .dataset import EvalError

_WORD=re.compile(r'\w+',re.UNICODE)

def normalize(text:str)->str:
    if not isinstance(text,str):raise EvalError('text metric requires Unicode string')
    return ' '.join(_WORD.findall(unicodedata.normalize('NFKC',text).casefold()))


def _f1(predicted:list[str],expected:list[str])->float:
    if not predicted and not expected:return 1.0
    if not predicted or not expected:return 0.0
    shared=sum((Counter(predicted)&Counter(expected)).values())
    if not shared:return 0.0
    precision=shared/len(predicted);recall=shared/len(expected)
    return 2*precision*recall/(precision+recall)

@dataclass(frozen=True,slots=True)
class EvaluationScore:
    exact_match:float
    normalized_match:float
    token_f1:float
    sequence_similarity:float
    answer_length_bytes:int


def eval_text(actual:str,reference:str)->EvaluationScore:
    if not isinstance(actual,str) or not isinstance(reference,str):
        raise EvalError('text scores require strings')
    if len(actual.encode())>1_000_000 or len(reference.encode())>1_000_000:
        raise EvalError('evaluation result exceeds bounded metric size')
    actual_norm=normalize(actual);ref_norm=normalize(reference)
    return EvaluationScore(float(actual==reference),float(actual_norm==ref_norm),
         _f1(actual_norm.split(),ref_norm.split()),
         SequenceMatcher(None,actual_norm[:8192],ref_norm[:8192],autojunk=False).ratio(),
         len(actual.encode()))
