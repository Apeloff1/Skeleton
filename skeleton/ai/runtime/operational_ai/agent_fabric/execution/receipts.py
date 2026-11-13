"""Canonical, privacy-preserving step completion records."""
from hashlib import sha256
from ..core.canonical import canonical,text,hex_digest,identifier
from ..core.errors import Invalid

def receipt(kind,output:bytes,metadata=None):
    if kind not in ('model','read','review','tool'):raise Invalid('invalid receipt kind')
    if not isinstance(output,bytes) or len(output)>1_048_576:raise Invalid('unbounded result data')
    m=metadata if metadata is not None else {}
    if not isinstance(m,dict):raise Invalid('invalid receipt metadata')
    # Store no free-form result text; a SHA and bounded typed metadata suffice
    # for audit, while authoritative model output remains in the spine store.
    if len(canonical(m,ceiling=8192))>8192:raise Invalid('oversized receipt metadata')
    return {'schema':'agent.step-result.v1','kind':kind,'output_sha256':sha256(output).hexdigest(),
            'status':'complete','metadata':m}
