"""Fail-closed trust classification for untrusted multimodal payloads."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import re
from skeleton.contracts.canonical import canonical_json_bytes
from .contracts import MediaError,MediaProvenance,Modality,ModalitySegment
MAX_PAYLOAD_BYTES=16_000_000
_PROMPT=re.compile(r"(?i)\b(ignore previous|system prompt|developer message|follow these instructions)\b")
@dataclass(frozen=True,slots=True)
class SanitizationReceipt:
 source_digest:str;payload_digest:str;policy_id:str;quarantined:bool;reason:str|None;transform_digest:str;authority_scope:str="sanitization-evidence-only"
 def __post_init__(self):
  if self.authority_scope!="sanitization-evidence-only": raise MediaError("sanitizer cannot grant authority")
def _d(v:bytes)->str:return sha256(v).hexdigest()
def sanitize_payload(*,segment_id:str,modality:Modality,payload:bytes,source_id:str,text:str|None=None,active_content:bool=False)->tuple[ModalitySegment,SanitizationReceipt]:
 if not isinstance(modality,Modality) or not isinstance(payload,bytes):raise MediaError("typed modality and bytes required")
 if len(payload)>MAX_PAYLOAD_BYTES:raise MediaError("payload budget exceeded")
 if not isinstance(active_content,bool):raise MediaError("active_content must be bool")
 if text is not None and not isinstance(text,str):raise MediaError("text must be string")
 embedded=bool(text and _PROMPT.search(text)); quarantined=active_content or embedded
 reason="active-content" if active_content else ("embedded-instruction" if embedded else None)
 source=_d(payload);safe=b"" if quarantined else payload;policy=f"multimodal-sanitize-{modality.value}-v1"
 transform=sha256(canonical_json_bytes({"policy":policy,"source":source,"result":_d(safe),"quarantined":quarantined,"reason":reason})).hexdigest()
 segment=ModalitySegment(segment_id,modality,_d(safe),MediaProvenance(source_id,source,transform),text=text,untrusted_metadata={"sanitization":"quarantined" if quarantined else "pass","policy_id":policy})
 return segment,SanitizationReceipt(source,_d(safe),policy,quarantined,reason,transform)
