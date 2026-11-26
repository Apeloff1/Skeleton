"""Bounded hybrid retrieval over witnessed crawler text.

No model or remote service is required. Lexical BM25, phrase coverage, character
trigrams and deterministic sparse feature overlap complement each other. Scores
are candidate-local, never semantic/model accuracy claims. Raw text is not
persisted here. The canonical grant/policy gate must run before scoring.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import re
import unicodedata

MAX_TEXT = 24000
MAX_QUERY = 512
MAX_DOCS = 64
MAX_TOKENS = 12000
MAX_QUERY_TOKENS = 32
MAX_FEATURES = 2048
STOP = frozenset("a an and are as at be by for from in is it of on or that the to was were with".split())


def words(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())[:MAX_TOKENS])


def features(tokens: tuple[str, ...]) -> Counter:
    """Unicode word and bounded subword features, for typo/morphology recall."""
    out: Counter = Counter()
    for word in tokens:
        if word in STOP:
            continue
        out["w:" + word] += 1
        if 4 <= len(word) <= 48:
            padded = "^" + word + "$"
            for n in range(len(padded) - 2):
                out["g:" + padded[n:n+3]] += 1
    for a, b in zip(tokens, tokens[1:]):
        if a not in STOP and b not in STOP:
            out["b:" + a + " " + b] += 1
    return Counter(dict(sorted(out.items(), key=lambda p: (-p[1], p[0]))[:MAX_FEATURES]))


def query_words(query):
    if not isinstance(query, str) or not 1 <= len(query) <= MAX_QUERY:
        raise ValueError("query bounds")
    tokens = words(query)[:MAX_QUERY_TOKENS]
    if not tokens:
        raise ValueError("empty lexical query")
    return tokens


def _cosine(a, b):
    numerator = sum(value * b.get(k, 0) for k, value in a.items())
    norm = math.sqrt(sum(v*v for v in a.values()) * sum(v*v for v in b.values()))
    return numerator / norm if norm else 0.0


def _bm25(q, counts, df, n, avg):
    length = sum(counts.values())
    denom = 1.2 * (.25 + .75 * length / max(1, avg))
    return sum(math.log1p((n - df[w] + .5) / (df[w] + .5)) *
               counts[w] * 2.2 / (counts[w] + denom)
               for w in set(q) if counts[w])


@dataclass(frozen=True)
class Candidate:
    key: str
    title: str
    text: str


def rank(query, candidates, *, work=None):
    tokens = query_words(query)
    terms = tuple(t for t in tokens if t not in STOP) or tokens
    if len(candidates) > MAX_DOCS or len({c.key for c in candidates}) != len(candidates):
        raise ValueError("candidate bound")
    if not candidates:
        return []
    prepared = []
    for c in candidates:
        if not isinstance(c, Candidate) or len(c.title) > 2048 or len(c.text) > MAX_TEXT:
            raise ValueError("candidate invalid")
        if work is None:
            title, body = words(c.title), words(c.text)
            counts = Counter(body)
            counts.update({w: 3*n for w,n in Counter(title).items()})
            sparse = None
        else:
            title, body, counts, sparse = work.hybrid_prepare(c.title,c.text)
        prepared.append((c, title, body, counts, sparse))
    df = Counter(w for _,_,_,counts,_ in prepared for w in set(terms) if counts[w])
    avg = sum(sum(p[3].values()) for p in prepared)/len(prepared)
    qf = features(tokens)
    qphrase = " ".join(tokens)
    results = []
    for c,title,body,counts,sparse in prepared:
        lexical = _bm25(terms,counts,df,len(prepared),avg)
        coverage = sum(1 for w in set(terms) if counts[w])/len(set(terms))
        title_coverage = len(set(terms).intersection(title))/len(set(terms))
        phrase = int(len(tokens)>1 and qphrase in " ".join(body))
        subword = _cosine(qf,features(title+body) if sparse is None else sparse)
        if not coverage and subword < .2:
            continue
        score = lexical/(1+lexical) + .65*coverage + .35*title_coverage + .20*phrase + .45*subword
        results.append({"key":c.key,"score":round(score,8),"lexical":round(lexical,8),
                        "coverage":round(coverage,8),"title_coverage":round(title_coverage,8),
                        "phrase":bool(phrase),"subword":round(subword,8)})
    return sorted(results,key=lambda r:(-r["score"],r["key"]))


def fuse_ranked(lanes, *, limit=32, k=60):
    """Reciprocal rank fusion across independent candidate windows/lists."""
    if not 1 <= limit <= 256 or not 1 <= k <= 1000 or len(lanes)>16:
        raise ValueError("fusion bounds")
    scores = Counter()
    for lane in lanes:
        if len(lane)>256:
            raise ValueError("lane bounds")
        seen = set()
        for pos, item in enumerate(lane, 1):
            if not isinstance(item,str) or len(item)>256:
                raise ValueError("candidate id")
            if item not in seen:
                scores[item] += 1/(k+pos)
                seen.add(item)
    return sorted(scores,key=lambda item:(-scores[item],item))[:limit]


def fingerprint(text):
    """Exact and near-duplicate evidence hints; never merge source authority."""
    if not isinstance(text,str) or len(text)>MAX_TEXT:
        raise ValueError("fingerprint bounds")
    tokens=words(text)
    accum=[0]*64
    for term,count in Counter(tokens).items():
        bits=int.from_bytes(hashlib.blake2b(term.encode(),digest_size=8).digest(),"big")
        for i in range(64):
            accum[i] += min(count,16) if bits & (1<<i) else -min(count,16)
    simhash=sum(1<<i for i,x in enumerate(accum) if x>0)
    return {"sha256":hashlib.sha256(text.encode()).hexdigest(),
            "simhash64":f"{simhash:016x}","tokens":len(tokens)}


def select_passage(query, text, width):
    """Find a contiguous original Unicode span, not an invented summary."""
    tokens=query_words(query)
    if not isinstance(text,str) or not text or len(text)>MAX_TEXT or not 1<=width<=4000:
        raise ValueError("span bounds")
    width=min(width,len(text))
    step=max(1,width//2,(len(text)-width+126)//127)
    starts=list(range(0,len(text)-width+1,step))
    if starts[-1]!=len(text)-width:
        starts.append(len(text)-width)
    wanted=set(tokens)
    scored=[]
    for start in starts:
        span=text[start:start+width]
        st=words(span)
        overlap=len(wanted.intersection(st))
        if overlap:
            scored.append((overlap, sum(min(4,st.count(w)) for w in wanted), -start))
    if not scored:
        raise ValueError("no exact query token in passage")
    start=-max(scored)[2]
    return start,start+width


MAX_ROUTE_KEYS=8192
MAX_WORDS_PER_SOURCE=128
ROUTE_SCHEMA="skeleton.dragon.hybrid-route.v1"


def _route_token(scope,kind,term):
    from skeleton.ai.webcrawler.dragon_archive_scale import digest
    return digest({"scope":scope,"domain":ROUTE_SCHEMA,"kind":kind,"term":term})


def build_route(scope,snapshot,grant,policies,now,allowed):
    """Bounded per-source rare term/title index, derived only from eligible text."""
    from skeleton.ai.webcrawler.dragon_archive_scale import digest
    from skeleton.ai.webcrawler.dragon_archive_grant import archive_expiry
    chosen=set()
    counts=0
    for sid in sorted(allowed):
        s=snapshot["sources"][sid]
        expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=s,
                              policy=policies.get(sid,{"enabled":True,"version":0}),now=now)
        if expiry is None:
            continue
        title=tuple(dict.fromkeys(words(s["title"])))
        body=Counter(words(s["text"]))
        body_terms=sorted((w for w in body if w not in STOP and len(w)>2),
                          key=lambda w:(body[w],-len(w),w))
        lexical=tuple(dict.fromkeys(title[:32]+tuple(body_terms)))[:MAX_WORDS_PER_SOURCE]
        chosen.update(_route_token(scope,"word",w) for w in lexical)
        counts+=1
    if len(chosen)>MAX_ROUTE_KEYS:
        raise ValueError("route bound")
    value={"schema":ROUTE_SCHEMA,"snapshot_digest":snapshot["snapshot_digest"],
           "grant_digest":digest(grant),"policy_digest":digest(policies),
           "expires_at":grant["expires_at"],"tokens":sorted(chosen),"sources":counts}
    return {**value,"digest":digest(value)}


def route_terms(scope,query):
    return sorted({_route_token(scope,"word",w) for w in query_words(query)})


def validate_route(value,snapshot,grant,policies,now):
    from skeleton.ai.webcrawler.dragon_archive_scale import digest
    from skeleton.ai.webcrawler.dragon_treasury_vault import hash_identity
    if (not isinstance(value,dict) or set(value)!={"schema","snapshot_digest","grant_digest","policy_digest",
            "expires_at","tokens","sources","digest"} or value["schema"]!=ROUTE_SCHEMA
            or value["snapshot_digest"]!=snapshot["snapshot_digest"]
            or value["grant_digest"]!=digest(grant) or value["policy_digest"]!=digest(policies)
            or value["expires_at"]!=grant["expires_at"] or value["expires_at"]<=now
            or not isinstance(value["tokens"],list) or len(value["tokens"])>MAX_ROUTE_KEYS
            or not all(hash_identity(x) for x in value["tokens"])
            or value["tokens"]!=sorted(set(value["tokens"]))
            or type(value["sources"]) is not int or not 0<=value["sources"]<=MAX_DOCS
            or value["digest"]!=digest({k:v for k,v in value.items() if k!="digest"})):
        raise ValueError("hybrid route invalid or expired")
    return value
