"""Canonical appendix cross-reference and terminology registry for VOL-121."""
from __future__ import annotations
from dataclasses import dataclass
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class AppendixError(ValueError):pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise AppendixError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v):raise AppendixError(f"{f} must be sha256")
 return v
@dataclass(frozen=True,slots=True)
class AppendixReference:
 reference_id:str;canonical_path:str;canonical_digest:str;label:str
 def __post_init__(self):
  object.__setattr__(self,"reference_id",_id(self.reference_id,"reference_id"));_sha(self.canonical_digest,"canonical_digest")
  if not self.canonical_path.strip() or not self.label.strip():raise AppendixError("reference path and label required")
@dataclass(frozen=True,slots=True)
class TermDefinition:
 term_id:str;term:str;definition:str;owner_id:str;version:int
 def __post_init__(self):
  object.__setattr__(self,"term_id",_id(self.term_id,"term_id"));object.__setattr__(self,"owner_id",_id(self.owner_id,"owner_id"))
  if not self.term.strip() or not self.definition.strip() or self.version<1:raise AppendixError("normative term definition invalid")
class ReferenceIndex:
 def __init__(self,references,terms):
  refs=tuple(references);ts=tuple(terms);self.references={x.reference_id:x for x in refs};self.terms={x.term_id:x for x in ts}
  if len(self.references)!=len(refs):raise AppendixError("duplicate appendix reference")
  if len(self.terms)!=len(ts):raise AppendixError("duplicate normative term id")
  names=[x.term.casefold() for x in ts]
  if len(set(names))!=len(names):raise AppendixError("duplicate normative term definition")
 def stale_references(self,current_digests):
  return tuple(sorted(r.reference_id for r in self.references.values() if current_digests.get(r.canonical_path)!=r.canonical_digest))
 def resolve_term(self,term_id):return self.terms[_id(term_id,"term_id")]
