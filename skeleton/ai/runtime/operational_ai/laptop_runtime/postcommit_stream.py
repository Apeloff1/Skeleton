"""Post-commit output chunking with explicit no-live-token-stream guarantee.

This only partitions a *committed* model output; native streaming support
and backend cancellation must be certified separately.
"""
from __future__ import annotations
from .contracts import canonical,identifier,utf8,refuse
from hashlib import sha256

def chunks(receipt,*,chunk_bytes=4096,max_chunks=256):
    if type(receipt) is not dict or receipt.get("replayed") not in (True,False):
        refuse("native committed or replay receipt required")
    text=utf8(receipt.get("text"),maximum=262144)
    if type(chunk_bytes) is not int or not 1<=chunk_bytes<=16384:
        refuse("invalid postcommit frame bound")
    if type(max_chunks) is not int or not 1<=max_chunks<=256:
        refuse("invalid postcommit frame count")
    data=text.encode("utf-8")
    if sha256(data).hexdigest()!=receipt.get("output_sha256"):
        refuse("committed output digest mismatch")
    frames=[];offset=0
    while offset<len(data):
        end=min(offset+chunk_bytes,len(data))
        while end>offset:
            try:segment=data[offset:end].decode("utf-8","strict");break
            except UnicodeDecodeError:end-=1
        if end==offset:refuse("postcommit frame too small for Unicode codepoint")
        frames.append({"index":len(frames),"byte_start":offset,"byte_end":end,"text":segment})
        if len(frames)>max_chunks:refuse("bounded frame count exceeded")
        offset=end
    return {"mode":"postcommit-not-native-stream",
            "output_sha256":receipt["output_sha256"],
            "frames":frames,"total_bytes":len(data)}
