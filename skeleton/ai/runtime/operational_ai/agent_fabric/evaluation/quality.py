"""Deterministic offline answer checks; never claim semantic correctness."""
import re
from ..core.canonical import text
from ..core.errors import Invalid
CITATION=re.compile(r'(?<![A-Za-z0-9])\[source:([A-Za-z0-9_-]{1,128})\]')
def inspect(text_output,sources,*,max_bytes=131072):
    answer=text(text_output,'answer',maximum=max_bytes)
    allowed={s['id'] for s in sources}
    mentions=set(CITATION.findall(answer))
    unknown=sorted(mentions-allowed)
    return {'status':'citation-identifier-audit-not-factual-truth',
            'citations':len(mentions),'unknown_citations':unknown,
            'grounded_claim_certified':False}
