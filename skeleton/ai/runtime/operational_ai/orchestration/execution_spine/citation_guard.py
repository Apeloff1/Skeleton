"""Reject unsupported source tokens without asserting semantic truth.

This only checks citations and their existence in the independently admitted
context. It does not verify factual claims or turn sources into authority.
"""
from __future__ import annotations
import re
from .contracts import Conflict,SpineError,identifier
_TOKEN=re.compile(r"(?<![A-Za-z0-9_-])source:([A-Za-z0-9_-]{1,128})(?![A-Za-z0-9_-])")
def audit_citations(text:str,sources:tuple[dict,...])->dict:
    if not isinstance(text,str) or len(text.encode('utf8'))>262144:
        raise SpineError('invalid answer citation span')
    approved={item['source_id'] for item in sources}
    mentioned={m.group(1) for m in _TOKEN.finditer(text)}
    unknown=mentioned-approved
    if unknown:raise Conflict('output introduced unsupported local source identifier')
    return {'known_source_count':len(approved),'cited_source_count':len(mentioned),
        'status':'citation-identifiers-validated-not-semantic-verification'}
