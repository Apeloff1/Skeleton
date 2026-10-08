"""Canonical browser-to-analysis visual payload validation."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,math

from .dragon_frame_custody import CapturedFrame,FrameBatch,bind_extracted_frames
from .dragon_visual_features import VisualObservation,VisualFeatureBatch,bind_visual_observations
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from .dragon_canonical_wire import visual_wire_fingerprint

SCHEMA="dragon.visual-observations.v1"

@dataclass(frozen=True)
class BrowserVisualEnvelope:
    schema:str; owner:str; job_id:str; recording_digest:str
    consent_id:str; consent_scope_digest:str; retention_until:float
    frames:tuple[CapturedFrame,...]; observations:tuple[VisualObservation,...]
    payload_fingerprint:str

@dataclass(frozen=True)
class AcceptedBrowserVisual:
    envelope_fingerprint:str
    features:VisualFeatureBatch

def canonical_browser_visual_fingerprint(envelope:BrowserVisualEnvelope)->str:
    return visual_wire_fingerprint(envelope)

def accept_browser_visual(custody:ConsentBoundAnalysisQueue,envelope:BrowserVisualEnvelope,*,
    now:float,authorized:bool)->AcceptedBrowserVisual:
    if not authorized: raise PermissionError("browser visual import requires authorization")
    if envelope.schema!=SCHEMA: raise ValueError("unsupported browser visual schema")
    if not math.isfinite(envelope.retention_until) or now>=envelope.retention_until:
        raise PermissionError("browser visual retention expired")
    job=custody.require_active(envelope.owner,envelope.job_id,now=now,authorized=True)
    binding=custody.binding(envelope.owner,envelope.job_id,authorized=True)
    if envelope.recording_digest!=job.recording_digest: raise ValueError("recording substitution")
    if envelope.consent_id!=binding.consent_id or envelope.consent_scope_digest!=binding.scope_digest:
        raise ValueError("consent substitution")
    expected=canonical_browser_visual_fingerprint(envelope)
    if envelope.payload_fingerprint!=expected: raise ValueError("browser visual payload fingerprint mismatch")
    # Treat browser frame IDs as transport-local only. Reissue canonical custody IDs from
    # authoritative job/consent/recording state and immutable frame content metadata.
    extracted=tuple((x.captured_at_ms,x.frame_digest,x.source_locator) for x in envelope.frames)
    source=bind_extracted_frames(custody,envelope.owner,envelope.job_id,extracted,
      now=now,retention_until=envelope.retention_until,authorized=True)
    if len(source.frames)!=len(envelope.frames): raise ValueError("frame rebind cardinality mismatch")
    id_map={wire.frame_id:canonical.frame_id for wire,canonical in zip(envelope.frames,source.frames)}
    if len(id_map)!=len(envelope.frames): raise ValueError("duplicate browser frame identity")
    observations=tuple(VisualObservation(id_map[x.frame_id],x.frame_digest,x.luminance_mean,
      x.edge_density,x.motion_energy,x.scene_change) for x in envelope.observations
      if x.frame_id in id_map)
    if len(observations)!=len(envelope.observations): raise ValueError("observation references unknown browser frame")
    features=bind_visual_observations(custody,envelope.owner,envelope.job_id,source,
      observations,now=now,authorized=True)
    return AcceptedBrowserVisual(expected,features)
