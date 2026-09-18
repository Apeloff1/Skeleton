"""Plain JSON persistence envelope with canonical digest binding."""
from __future__ import annotations
import copy,json
from dataclasses import dataclass
from typing import Any,Mapping
from .canonical import digest
from .errors import ValidationError
@dataclass(frozen=True)
class EncodedDocument:
    schema:str;payload:Mapping[str,Any];payload_digest:str
    def to_record(self):return {"schema":self.schema,"payload":copy.deepcopy(dict(self.payload)),"payload_digest":self.payload_digest}
def encode_document(schema:str,payload:Mapping[str,Any])->str:
    if not isinstance(schema,str) or not schema:raise ValidationError("document schema required")
    if not isinstance(payload,Mapping):raise ValidationError("document payload must be mapping")
    record=EncodedDocument(schema,dict(payload),digest(dict(payload))).to_record()
    return json.dumps(record,sort_keys=True,separators=(",",":"),ensure_ascii=False)
def decode_document(text:str,*,expected_schema:str|None=None)->EncodedDocument:
    if not isinstance(text,str) or not text:raise ValidationError("document text required")
    try:node=json.loads(text)
    except json.JSONDecodeError as exc:raise ValidationError("invalid document json") from exc
    if not isinstance(node,dict) or set(node)!={"schema","payload","payload_digest"}:raise ValidationError("document fields mismatch")
    if expected_schema is not None and node["schema"]!=expected_schema:raise ValidationError("document schema mismatch")
    if not isinstance(node["payload"],dict):raise ValidationError("document payload must be object")
    if digest(node["payload"])!=node["payload_digest"]:raise ValidationError("document digest mismatch")
    return EncodedDocument(node["schema"],node["payload"],node["payload_digest"])
