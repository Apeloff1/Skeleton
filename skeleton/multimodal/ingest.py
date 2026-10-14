"""Converged bounded ingestion into canonical multimodal artifacts."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
from .contracts import CrossModalReference,MediaArtifact,MediaError,Modality,ModalitySegment
from .sanitize import sanitize_payload

MAX_INPUTS=4096
@dataclass(frozen=True,slots=True)
class MediaInput:
 segment_id:str;modality:Modality;payload:bytes;source_id:str;text:str|None=None;active_content:bool=False

@dataclass(frozen=True,slots=True)
class IngestionReceipt:
 artifact_digest:str;segment_digests:tuple[str,...];quarantined_segments:tuple[str,...];authority_scope:str="ingestion-evidence-only"
 def __post_init__(self):
  if self.authority_scope!="ingestion-evidence-only":raise MediaError("ingestion cannot grant authority")

def ingest_media(*,artifact_id:str,inputs:tuple[MediaInput,...],references:tuple[CrossModalReference,...]=())->tuple[MediaArtifact,IngestionReceipt]:
 if not isinstance(inputs,tuple) or not inputs or len(inputs)>MAX_INPUTS:raise MediaError("input budget exceeded")
 if not isinstance(references,tuple):raise MediaError("references must be tuple")
 segments:list[ModalitySegment]=[];quarantined=[];seen=set()
 for item in inputs:
  if not isinstance(item,MediaInput):raise MediaError("typed MediaInput required")
  if item.segment_id in seen:raise MediaError("duplicate input segment")
  seen.add(item.segment_id)
  segment,receipt=sanitize_payload(segment_id=item.segment_id,modality=item.modality,payload=item.payload,source_id=item.source_id,text=item.text,active_content=item.active_content)
  segments.append(segment)
  if receipt.quarantined:quarantined.append(item.segment_id)
 artifact=MediaArtifact(artifact_id,tuple(segments),references)
 receipt=IngestionReceipt(artifact.digest,tuple(s.digest for s in artifact.segments),tuple(sorted(quarantined)))
 return artifact,receipt
