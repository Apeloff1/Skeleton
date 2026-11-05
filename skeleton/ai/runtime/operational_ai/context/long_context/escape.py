"""Reference passage isolation prevents role-delimiter injection."""
from __future__ import annotations
import json
from .contracts import Span


def quote_evidence(span:Span)->str:
    return ('<reference-data id='+json.dumps(span.span_id)+' trust='+json.dumps(span.trust)+
            ' digest='+json.dumps(span.digest)+'>\n'+
            json.dumps(span.text,ensure_ascii=False)+'\n</reference-data>')
