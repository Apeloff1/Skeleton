"""Canonical full-record manifests for reviewed Dragon knowledge."""
from hashlib import sha256
import json
from .dragon_knowledge_normalization_worker import NormalizedKnowledge


def canonical_knowledge_id(record:NormalizedKnowledge)->str:
 identity=[record.hypothesis_id,record.ontology_version,record.verdict,record.probability,
  record.probability_semantics,record.calibration_artifact_fingerprint,
  record.evidence_fingerprint]
 return sha256(json.dumps(identity,separators=(",",":")).encode()).hexdigest()


def canonical_knowledge_manifest(records:tuple[NormalizedKnowledge,...])->str:
 seen=set();canonical=[]
 for r in sorted(records,key=lambda x:x.knowledge_id):
  if r.knowledge_id in seen:raise ValueError("duplicate normalized knowledge identity")
  seen.add(r.knowledge_id)
  if r.knowledge_id!=canonical_knowledge_id(r):
   raise ValueError("normalized knowledge identity is not canonical")
  canonical.append(vars(r))
 return sha256(json.dumps(canonical,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
