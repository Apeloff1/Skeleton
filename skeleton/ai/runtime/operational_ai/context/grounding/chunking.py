"""Deterministic, overlap-aware Unicode passage spans preserving exact offsets."""
from __future__ import annotations
from hashlib import sha256
from .documents import Document,Passage,GroundingError


def segment(doc:Document,*,max_chars:int=1200,overlap:int=120)->tuple[Passage,...]:
    if type(max_chars) is not int or type(overlap) is not int or not 64<=max_chars<=16_000 or not 0<=overlap<max_chars//2:
        raise GroundingError('invalid segmentation bounds')
    text=doc.text
    if not text:return ()
    spans=[];start=0
    while start<len(text):
        cap=min(len(text),start+max_chars)
        end=cap
        if cap<len(text):
            # Prefer paragraph boundaries, then whitespace; keep byte-exact spans.
            paragraph=text.rfind('\n\n',start+max_chars//2,cap)
            if paragraph>start+max_chars//2:
                end=paragraph+2
            else:
                gap=max(text.rfind(' ',start+max_chars//2,cap),text.rfind('\n',start+max_chars//2,cap))
                if gap>start+max_chars//2:end=gap+1
        if end<=start:raise GroundingError('non-progressing passage segmentation')
        body=text[start:end]
        if len(body.encode('utf8'))>32_000:
            raise GroundingError('single passage exceeds bounded byte limit')
        idx=len(spans)+1
        spans.append(Passage(doc.doc_id,f'{doc.doc_id}_{idx}',start,end,body,doc.sha256,doc.revision,doc.trust))
        if end==len(text):break
        start=max(start+1,end-overlap)
        if len(spans)>20_000:
            raise GroundingError('document chunk count excessive')
    return tuple(spans)


def verify_spans(doc:Document,passages:tuple[Passage,...])->bool:
    last=-1
    for passage in passages:
        if (passage.doc_id!=doc.doc_id or passage.sha256!=doc.sha256
            or passage.revision!=doc.revision or passage.start<=last
            or doc.text[passage.start:passage.end]!=passage.body):
            return False
        last=passage.start
    return bool(passages) if doc.text else not passages
