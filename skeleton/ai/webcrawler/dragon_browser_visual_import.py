"""Canonical browser-to-analysis visual payload validation."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,math

from .dragon_frame_custody import CapturedFrame,FrameBatch
from .dragon_visual_features import VisualObservation,VisualFeatureBatch,bind_visual_observations
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue

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
    body={"schema":envelope.schema,"owner":envelope.owner,"job_id":envelope.job_id,
      "recording_digest":envelope.recording_digest,"consent_id":envelope.consent_id,
      "consent_scope_digest":envelope.consent_scope_digest,
      "retention_until":envelope.retention_until,
      "frames":[[x.frame_id,x.frame_digest,x.captured_at_ms,x.source_locator] for x in envelope.frames],
      "observations":[[x.frame_id,x.frame_digest,x.luminance_mean,x.edge_density,
        x.motion_energy,x.scene_change] for x in envelope.observations]}
    return sha256(json.dumps(body,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

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
    # Reconstruct server-side custody fields; the browser cannot choose owner/job/consent bindings per frame.
    frames=tuple(CapturedFrame(x.frame_id,envelope.owner,envelope.job_id,job.recording_digest,
      binding.consent_id,binding.scope_digest,x.captured_at_ms,x.frame_digest,
      envelope.retention_until,x.source_locator) for x in envelope.frames)
    source=FrameBatch(frames,sha256("\n".join(x.frame_id for x in frames).encode()).hexdigest())
    features=bind_visual_observations(custody,envelope.owner,envelope.job_id,source,
      envelope.observations,now=now,authorized=True)
    return AcceptedBrowserVisual(expected,features)
