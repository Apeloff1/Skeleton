"""Bounded source selection without converting document instructions into authority."""
from hashlib import sha256
from ..core.canonical import text
from ..core.errors import Invalid

def select(hits,*,owner,max_hits=6,max_bytes=16384):
    if type(max_hits)is not int or not 1<=max_hits<=32:raise Invalid('bad hit ceiling')
    if type(max_bytes)is not int or not 256<=max_bytes<=1048576:raise Invalid('bad context budget')
    selected=[];consumed=0;seen=set()
    for hit in hits:
        if not isinstance(hit,dict) or set(hit)!={'id','owner','text','sha256','trust'}:raise Invalid('unknown source shape')
        if hit['owner']!=owner:raise Invalid('cross-owner knowledge forbidden')
        from ..core.canonical import identifier,hex_digest
        identifier(hit['id'],'source ID');hex_digest(hit['sha256'])
        content=text(hit['text'],maximum=max_bytes)
        if sha256(content.encode('utf8')).hexdigest()!=hit['sha256']:raise Invalid('source digest mismatch')
        if hit['trust'] not in ('user-supplied','approved-document','tool-result'):raise Invalid('model-created source cannot self-trust')
        if hit['id'] in seen:continue
        size=len(content.encode('utf8'))
        if consumed+size>max_bytes:break
        selected.append(hit);seen.add(hit['id']);consumed+=size
        if len(selected)>=max_hits:break
    return tuple(selected)
