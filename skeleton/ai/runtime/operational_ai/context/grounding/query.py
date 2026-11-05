"""Normal-form lexical queries with no untrusted SQLite FTS query syntax."""
from __future__ import annotations
import re,unicodedata,math
from collections import Counter
from .documents import GroundingError
_TERM=re.compile(r'\w{2,48}',re.UNICODE)


def words(text:str,*,cap:int=128)->tuple[str,...]:
    if not isinstance(text,str) or len(text.encode('utf8'))>64_000:
        raise GroundingError('query string too large')
    if type(cap) is not int or not 1<=cap<=1024:raise GroundingError('invalid query token cap')
    normalized=unicodedata.normalize('NFKC',text).casefold()
    return tuple(_TERM.findall(normalized)[:cap])


def escaped_fts_query(text:str,*,max_terms:int=16)->str:
    tokens=words(text,cap=max_terms)
    # Only quoted literal terms, never raw FTS5 query operators.
    unique=list(dict.fromkeys(t.replace('"','') for t in tokens if t))
    return ' OR '.join('"'+token+'"' for token in unique)


def counts(text:str)->dict[str,int]:
    return dict(Counter(words(text,cap=1024)))


def overlap_score(query:str,body:str)->float:
    q=set(words(query));b=set(words(body))
    return len(q&b)/max(1,len(q))
