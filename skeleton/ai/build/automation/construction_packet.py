"""Diffable machine-linked construction packets for VOL-111."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib,json,re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class PacketError(ValueError):pass
class PacketSection(str,Enum): OBJECTIVE="objective"; NON_GOALS="non_goals"; DEPENDENCIES="dependencies"; INTERFACES="interfaces"; AUTHORITY="authority"; STATE="state"; FAILURE="failure"; TESTS="tests"; ROLLBACK="rollback"; EVIDENCE="evidence"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise PacketError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise PacketError(f"{f} must be sha256")
 return v
def _dig(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
@dataclass(frozen=True,slots=True)
class PacketReference:
 reference_id:str;source_path:str;source_digest:str
 def __post_init__(self):
  object.__setattr__(self,"reference_id",_id(self.reference_id,"reference_id"));_sha(self.source_digest,"source_digest")
  if not self.source_path.strip():raise PacketError("source path required")
@dataclass(frozen=True,slots=True)
class SectionContent:
 section:PacketSection;text:str;references:tuple[PacketReference,...]=()
 def __post_init__(self):
  if not self.text.strip() and not self.references:raise PacketError("section requires content or machine reference")
@dataclass(frozen=True,slots=True)
class ConstructionPacket:
 packet_id:str;work_item_id:str;sections:tuple[SectionContent,...]
 def __post_init__(self):
  object.__setattr__(self,"packet_id",_id(self.packet_id,"packet_id"));object.__setattr__(self,"work_item_id",_id(self.work_item_id,"work_item_id"))
  by={s.section:s for s in self.sections}
  if len(by)!=len(self.sections):raise PacketError("duplicate packet section")
  missing=set(PacketSection)-set(by)
  if missing:raise PacketError("missing sections: "+",".join(sorted(x.value for x in missing)))
  object.__setattr__(self,"sections",tuple(sorted(self.sections,key=lambda s:s.section.value)))
 @property
 def digest(self):return _dig({"packet":self.packet_id,"work_item":self.work_item_id,"sections":[[s.section.value,s.text,[[r.reference_id,r.source_path,r.source_digest] for r in s.references]] for s in self.sections]})
 def validate_references(self,current_digests):
  stale=[]
  for s in self.sections:
   for r in s.references:
    if current_digests.get(r.source_path)!=r.source_digest:stale.append(r.reference_id)
  return tuple(sorted(stale))
