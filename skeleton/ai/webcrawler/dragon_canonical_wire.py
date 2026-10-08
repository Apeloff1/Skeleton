"""Cross-language canonical wire encoding for Dragon visual evidence."""
from __future__ import annotations
from decimal import Decimal,InvalidOperation
from hashlib import sha256
import json,math

WIRE="dragon.canonical-decimal.v1"

def decimal_wire(value:float|int)->str:
 if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
  raise ValueError("canonical decimal requires finite number")
 if value==0:return "0"
 try:d=Decimal(str(value))
 except InvalidOperation as e:raise ValueError("invalid canonical decimal") from e
 s=format(d.normalize(),"f")
 if "." in s:s=s.rstrip("0").rstrip(".")
 return s

def visual_wire_body(envelope)->dict:
 return {"wire":WIRE,"schema":envelope.schema,"owner":envelope.owner,"job_id":envelope.job_id,
  "recording_digest":envelope.recording_digest,"consent_id":envelope.consent_id,
  "consent_scope_digest":envelope.consent_scope_digest,"decoder_version":envelope.decoder_version,
  "retention_until":decimal_wire(envelope.retention_until),
  "frames":[[x.frame_id,x.frame_digest,str(x.captured_at_ms),x.source_locator] for x in envelope.frames],
  "observations":[[x.frame_id,x.frame_digest,decimal_wire(x.luminance_mean),
   decimal_wire(x.edge_density),decimal_wire(x.motion_energy),decimal_wire(x.scene_change)]
   for x in envelope.observations]}

def visual_wire_bytes(envelope)->bytes:
 return json.dumps(visual_wire_body(envelope),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()

def visual_wire_fingerprint(envelope)->str:
 return sha256(visual_wire_bytes(envelope)).hexdigest()
