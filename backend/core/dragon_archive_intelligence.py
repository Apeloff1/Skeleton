"""Request-local archive optimization and revision analysis.

The archive grant and exact checkpoint remain the only authority. Feature
memoization is deliberately local to one authorized search/maintenance
operation; it never stores a body or token map on disk or across requests.
Hashes are verified against actual input, and no cache result can grant use.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
import hashlib
import math
import re

from skeleton.ai.webcrawler.dragon_archive_grant import archive_expiry
from skeleton.ai.webcrawler.dragon_archive_scale import digest
from skeleton.ai.webcrawler.dragon_companion import _lexemes

MAX_TEXT = 24000
MAX_TITLE = 2048
MAX_ENTRIES = 192
MAX_WEIGHT = 12 * 1024 * 1024
MAX_SHINGLES = 2048
MAX_BLOCKS = 128
MAX_BLOCK_BYTES = 1536
MAX_COMPARE = 64
HEX = re.compile(r"[a-f0-9]{64}\Z")


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _valid_text(value,maximum):
    if not isinstance(value,str) or len(value)>maximum:
        raise ValueError("archive text bounds")
    return value


@dataclass(frozen=True)
class WorkReceipt:
    requests: int
    hits: int
    misses: int
    evictions: int
    resident_entries: int
    estimated_feature_bytes: int
    persistent: bool = False


class ArchiveWork:
    """Bounded weighted LRU for exact-content work, not an authority cache."""

    def __init__(self,*,max_entries=MAX_ENTRIES,max_weight=MAX_WEIGHT):
        if (type(max_entries) is not int or not 1<=max_entries<=MAX_ENTRIES
                or type(max_weight) is not int or not 1024<=max_weight<=MAX_WEIGHT):
            raise ValueError("archive work bounds")
        self.max_entries=max_entries
        self.max_weight=max_weight
        self._memory=OrderedDict()
        self.weight=0
        self.requests=self.hits=self.misses=self.evictions=0

    def get(self,kind,texts,build,weight):
        self.requests+=1
        # Domain separation prevents lexical and passage representations
        # from aliasing. Each key hashes actual bytes, never a caller's claim.
        key=(kind,tuple(sha(t) for t in texts))
        if key in self._memory:
            self.hits+=1
            self._memory.move_to_end(key)
            return self._memory[key][0]
        self.misses+=1
        value=build()
        size=weight(value)
        if type(size) is not int or size<0:
            raise ValueError("invalid archive work weight")
        if size<=self.max_weight:
            while self._memory and (len(self._memory)>=self.max_entries or self.weight+size>self.max_weight):
                _,(_,old)=self._memory.popitem(last=False)
                self.weight-=old
                self.evictions+=1
            self._memory[key]=(value,size)
            self.weight+=size
        return value

    def exact_counts(self,title,text):
        _valid_text(title,MAX_TITLE);_valid_text(text,MAX_TEXT)
        return self.get("exact-lexical-v1",(title,text),
            lambda:Counter(_lexemes(title+" "+text)),_counter_weight)

    def passage_counts(self,text):
        from core.dragon_hybrid_rank import words
        _valid_text(text,MAX_TEXT)
        return self.get("passage-lexical-v1",(text,),lambda:Counter(words(text)),_counter_weight)

    def hybrid_prepare(self,title,text):
        from core.dragon_hybrid_rank import words,features
        _valid_text(title,MAX_TITLE);_valid_text(text,MAX_TEXT)
        def build():
            head,body=words(title),words(text)
            counts=Counter(body)
            counts.update({w:3*n for w,n in Counter(head).items()})
            return head,body,counts,features(head+body)
        def weight(value):
            head,body,counts,sparse=value
            return (256+sum(64+4*len(t) for t in head+body)
                +_counter_weight(counts)+_counter_weight(sparse))
        return self.get("hybrid-prepare-v1",(title,text),build,weight)

    def receipt(self):
        return WorkReceipt(self.requests,self.hits,self.misses,self.evictions,
                           len(self._memory),self.weight).__dict__.copy()


def _counter_weight(counter):
    # Conservative accounting rather than a measured Python RSS promise.
    return 128+sum(160+4*len(k) for k in counter)


def rank_exact(snapshot,grant,policies,now,terms,allowed,work):
    """Same exact coverage contract as canonical archive_scale.rank_exact."""
    wanted=set(terms)
    result=[]
    for sid in sorted(allowed):
        source=snapshot["sources"][sid]
        policy=policies.get(sid,{"enabled":True,"version":0})
        expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],
            source=source,policy=policy,now=now)
        if expiry is None:
            continue
        text=source["text"]
        if sha(text)!=source["preserved_text_hash"]:
            raise ValueError("archive source checksum changed")
        counts=work.exact_counts(source["title"],text)
        overlap=wanted.intersection(counts)
        if overlap:
            result.append({"source_id":sid,"preserved_text_hash":source["preserved_text_hash"],
                "captured_at":source["fetched_at"],"valid_until":expiry,
                "matched_terms":len(overlap),"term_frequency":sum(min(8,counts[t]) for t in overlap),
                "policy_version":policy["version"]})
    return result


def eligible_material(snapshot,grant,policies,allowed,now):
    """Project only qualified material; never treat a similarity hint as proof."""
    if len(allowed)>MAX_COMPARE:
        raise ValueError("archive material bound")
    result=[]
    for sid in sorted(allowed):
        source=snapshot["sources"][sid]
        expiry=archive_expiry(grant,snapshot_digest=snapshot["snapshot_digest"],source=source,
            policy=policies.get(sid,{"enabled":True,"version":0}),now=now)
        if expiry is None:
            continue
        text=_valid_text(source["text"],MAX_TEXT)
        if sha(text)!=source["preserved_text_hash"]:
            raise ValueError("archive source checksum changed")
        result.append((sid,source,expiry))
    return result


def _sketch(text):
    """Bottom-k exact hashed word shingles, bounded and order-sensitive."""
    from core.dragon_hybrid_rank import words
    tokens=words(text)
    hashed={hashlib.blake2b("\x00".join(tokens[i:i+3]).encode(),digest_size=8).hexdigest()
        for i in range(max(0,len(tokens)-2))}
    if not hashed:
        hashed={hashlib.blake2b(t.encode(),digest_size=8).hexdigest() for t in tokens}
    sampled=tuple(sorted(hashed)[:MAX_SHINGLES])
    return sampled,len(hashed)>MAX_SHINGLES,len(tokens)


def _blocks(text):
    """Content-defined chunks over UTF-8, with bounded scanning and size.

    A rolling 32-bit gear-style boundary recovers after inserted text rather
    than moving every fixed-size block. No chunk bytes leave this function.
    """
    raw=text.encode("utf-8")
    state=0;start=0;parts=[]
    for i,byte in enumerate(raw):
        state=((state<<1)+((byte+1)*0x9e3779b1)) & 0xffffffff
        length=i+1-start
        if length>=256 and ((state&0x1ff)==0 or length>=MAX_BLOCK_BYTES):
            parts.append((hashlib.sha256(raw[start:i+1]).hexdigest(),length))
            start=i+1;state=0
            if len(parts)>=MAX_BLOCKS:
                return parts,True
    if start<len(raw):
        parts.append((hashlib.sha256(raw[start:]).hexdigest(),len(raw)-start))
    return parts,False


def compare_text(old,new):
    _valid_text(old,MAX_TEXT);_valid_text(new,MAX_TEXT)
    a,b=sha(old),sha(new)
    left,right=_blocks(old),_blocks(new)
    sketches=(_sketch(old),_sketch(new))
    x,y=set(sketches[0][0]),set(sketches[1][0])
    # Bottom-k union truncation makes the comparison consistent when
    # one revision contributes more shingles than the other.
    sample=set(sorted(x|y)[:MAX_SHINGLES])
    similarity=len((x&y)&sample)/max(1,len(sample))
    lc=Counter(k for k,_ in left[0]);rc=Counter(k for k,_ in right[0])
    sizes=dict(left[0]+right[0])
    reused=sum(sizes[k]*min(n,lc[k]) for k,n in rc.items())
    old_size=len(old.encode("utf-8"));new_size=len(new.encode("utf-8"))
    if a==b:
        classification="identical"
        similarity=1.
    elif min(sketches[0][2],sketches[1][2])<12:
        classification="changed_short_text"
    elif similarity>=.88:
        classification="near_duplicate"
    elif similarity>=.45:
        classification="related_revision"
    else:
        classification="substantially_changed"
    return {"classification":classification,"old_sha256":a,"new_sha256":b,
        "shingle_similarity":round(similarity,8),"old_bytes":old_size,"new_bytes":new_size,
        "reusable_chunk_bytes_estimate":reused,
        "new_chunk_bytes_estimate":max(0,new_size-reused),
        "chunk_window_truncated":left[1] or right[1],
        "shingle_sampled":sketches[0][1] or sketches[1][1],
        "near_duplicate_is_advisory":True,"physical_storage_modified":False}


def archive_report(material,*,snapshot_digest,grant):
    """Efficient exact grouping and near-duplicate work suggestions.

    Group by exact content identity before computing an expensive sketch.
    Compare a bounded candidate set using shared chunk hashes, never
    perform destructive archive compaction from approximate similarity.
    """
    if len(material)>MAX_COMPARE:
        raise ValueError("archive report bound")
    grouped={}
    for sid,source,expiry in material:
        grouped.setdefault(source["preserved_text_hash"],[]).append((sid,source,expiry))
    sketches={};blocks={};sources=[];unique_bytes=logical_bytes=0
    for hash_,group in sorted(grouped.items()):
        sid,source,expiry=group[0];text=source["text"]
        size=len(text.encode("utf-8"))
        unique_bytes+=size;logical_bytes+=size*len(group)
        sketches[hash_]=_sketch(text)
        blocks[hash_]=_blocks(text)
        sources.append({"text_digest":hash_,"source_ids":[row[0] for row in group],
            "text_bytes":size,"copies":len(group),"valid_until":min(row[2] for row in group)})
    block_refs=Counter()
    distinct_blocks={}
    for hash_,(items,truncated) in blocks.items():
        for block,size in items:
            block_refs[block]+=1
            distinct_blocks[block]=size
    pairs=[]
    hashes=sorted(sketches)
    # At most 2016 pairs for the canonical 64-source archive.
    for i,left in enumerate(hashes):
        a=set(sketches[left][0])
        for right in hashes[i+1:]:
            b=set(sketches[right][0])
            union=set(sorted(a|b)[:MAX_SHINGLES])
            score=len((a&b)&union)/max(1,len(union))
            if score>=.45 and min(sketches[left][2],sketches[right][2])>=12:
                pairs.append({"left":left,"right":right,"similarity":round(score,8),
                    "classification":"near_duplicate" if score>=.88 else "related"})
    pairs.sort(key=lambda row:(-row["similarity"],row["left"],row["right"]))
    result={"snapshot_digest":snapshot_digest,"grant_digest":digest(grant),
        "qualified_sources":len(material),"unique_texts":len(grouped),
        "logical_utf8_bytes":logical_bytes,"unique_text_utf8_bytes":unique_bytes,
        "exact_duplicate_bytes_estimate":logical_bytes-unique_bytes,
        "unique_chunk_bytes_estimate":sum(distinct_blocks.values()),
        "shared_chunk_count":sum(n>1 for n in block_refs.values()),
        "chunk_window_truncated":any(x[1] for x in blocks.values()),
        "groups":sources,"similarity_pairs":pairs[:32],"pair_window_truncated":len(pairs)>32,
        "history_only":True,"network_authorized":False,"training_permission":False,
        "physical_storage_modified":False}
    return {**result,"receipt":digest(result)}


def build_index_bundle(scope,snapshot,grant,policies,now,allowed,*,work=None):
    """Generate the existing three exact route contracts in a single pass.

    The three historical route formats and their individual digests remain
    byte-for-byte equivalent to the canonical builders. No route grants
    source authority. Only independently admitted material participates.
    """
    from skeleton.ai.webcrawler import dragon_archive_scale as a
    from core import dragon_hybrid_rank as h
    from core import dragon_passage_index as p
    if len(allowed)>a.MAX_SOURCES or len(snapshot["sources"])>a.MAX_SOURCES:
        raise ValueError("archive route source bound")
    work=ArchiveWork() if work is None else work
    material=eligible_material(snapshot,grant,policies,allowed,now)
    exact=set();hybrid=set();passage_tokens=set();passages=[];truncated=0
    for sid,source,expiry in material:
        title,text=source["title"],source["text"]
        counts=work.exact_counts(title,text)
        head=list(dict.fromkeys(_lexemes(title)))
        ordered=list(dict.fromkeys(head+sorted(counts,key=lambda x:(-counts[x],x))))
        truncated+=int(len(ordered)>a.TERMS_PER_SOURCE)
        exact.update(a.token(scope,t) for t in ordered[:a.TERMS_PER_SOURCE])
        def rare_terms():
            title_words=tuple(dict.fromkeys(h.words(title)))
            body=Counter(h.words(text))
            body_terms=sorted((w for w in body if w not in h.STOP and len(w)>2),
                             key=lambda w:(body[w],-len(w),w))
            return tuple(dict.fromkeys(title_words[:32]+tuple(body_terms)))[:h.MAX_WORDS_PER_SOURCE]
        lexical=work.get("rare-route-v1",(title,text),rare_terms,
            lambda value:128+sum(64+4*len(t) for t in value))
        hybrid.update(h._route_token(scope,"word",w) for w in lexical)
        if not text:continue
        for start,end in p.ranges(text):
            span=text[start:end]
            # Scope is part of the key for scope-hashed persistent tokens.
            scope_key=digest(scope)
            keys=work.get("passage-route-v1",(scope_key,span),lambda:p._keys(scope,span),
                lambda value:128+sum(128+4*len(t) for t in value))
            if not keys:continue
            passage_tokens.update(keys)
            passages.append({"source_id":sid,"start":start,"end":end,
                "passage_digest":sha(span),"keys":keys,"expires_at":expiry})
    if (len(exact)>a.MAX_TERMS or len(hybrid)>h.MAX_ROUTE_KEYS
            or len(passages)>p.MAX_PASSAGES or len(passage_tokens)>p.MAX_KEYS):
        raise ValueError("archive route bound")
    shared={"snapshot_digest":snapshot["snapshot_digest"],"grant_digest":digest(grant),
            "policy_digest":digest(policies),"expires_at":grant["expires_at"]}
    values=({"schema":a.INDEX,**shared,"tokens":sorted(exact),"eligible_sources":len(material),
             "truncated_sources":truncated},
            {"schema":h.ROUTE_SCHEMA,**shared,"tokens":sorted(hybrid),"sources":len(material)},
            {"schema":p.SCHEMA,**shared,"tokens":sorted(passage_tokens),"records":passages})
    index,hybrid_route,passage_route=({**v,"digest":digest(v)} for v in values)
    a.validate_index(index,snapshot,grant,policies,now)
    h.validate_route(hybrid_route,snapshot,grant,policies,now)
    p.validate_passage_route(passage_route,snapshot,grant,policies,now)
    return index,hybrid_route,passage_route
