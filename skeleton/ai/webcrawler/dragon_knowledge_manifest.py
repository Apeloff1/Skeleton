"""Canonical full-record manifests for human-reviewed Dragon knowledge."""
from hashlib import sha256
import json
from .dragon_knowledge_normalization_worker import NormalizedKnowledge

def canonical_knowledge_manifest(records:tuple[NormalizedKnowledge,...])->str:
 seen=set();canonical=[]
 for r in sorted(records,key=lambda x:x.knowledge_id):
  if r.knowledge_id in seen:raise ValueError("duplicate normalized knowledge identity")
  seen.add(r.knowledge_id)
  identity=[r.hypothesis_id,r.ontology_version,r.verdict,r.probability,
   r.probability_semantics,r.calibration_artifact_fingerprint,r.evidence_fingerprint]
  expected=sha256(json.dumps(identity,separators=(",",":")).encode()).hexdigest()
  if r.knowledge_id!=expected:raise ValueError("normalized knowledge identity is not canonical")
  canonical.append(vars(r))
 return sha256(json.dumps(canonical,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
