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
DECODER_VERSION="dragon.local-visual.rgb64x36.v1"

@dataclass(frozen=True)
class BrowserVisualEnvelope:
    schema:str; owner:str; job_id:str; recording_digest:str
    consent_id:str; consent_scope_digest:str; decoder_version:str; retention_until:float
    frames:tuple[CapturedFrame,...]; observations:tuple[VisualObservation,...]
    payload_fingerprint:str

@dataclass(frozen=True)
class AcceptedBrowserVisual:
    envelope_fingerprint:str
    canonical_evidence_fingerprint:str
    features:VisualFeatureBatch

def canonical_browser_visual_fingerprint(envelope:BrowserVisualEnvelope)->str:
    return visual_wire_fingerprint(envelope)

def _hex64(value:str)->bool:
    return isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value)

def _preflight_envelope(envelope:BrowserVisualEnvelope,*,max_frames:int)->None:
    if not isinstance(max_frames,int) or not 1<=max_frames<=100000:
        raise ValueError("invalid browser visual frame budget")
    if not isinstance(envelope.owner,str) or not 1<=len(envelope.owner)<=128:
        raise ValueError("invalid browser visual owner")
    if not isinstance(envelope.job_id,str) or not 1<=len(envelope.job_id)<=256:
        raise ValueError("invalid browser visual job")
    if not _hex64(envelope.recording_digest) or not _hex64(envelope.consent_id) or not _hex64(envelope.consent_scope_digest):
        raise ValueError("invalid browser visual identity digest")
    if envelope.decoder_version!=DECODER_VERSION:
        raise ValueError("unsupported browser visual decoder version")
    if not 1<=len(envelope.frames)<=max_frames or len(envelope.observations)!=len(envelope.frames):
        raise ValueError("invalid browser visual coverage")
    seen_frames=set();last=-1
    for frame in envelope.frames:
        if not isinstance(frame.frame_id,str) or not 1<=len(frame.frame_id)<=256 or frame.frame_id in seen_frames:
            raise ValueError("invalid or duplicate browser frame id")
        seen_frames.add(frame.frame_id)
        if not _hex64(frame.frame_digest):
            raise ValueError("invalid browser frame digest")
        if not isinstance(frame.captured_at_ms,int) or frame.captured_at_ms<0 or frame.captured_at_ms<=last:
            raise ValueError("browser frame timestamps must increase strictly")
        if not isinstance(frame.source_locator,str) or not 1<=len(frame.source_locator)<=2048:
            raise ValueError("invalid browser source locator")
        last=frame.captured_at_ms
    seen_observations=set()
    for obs in envelope.observations:
        if obs.frame_id in seen_observations or obs.frame_id not in seen_frames:
            raise ValueError("invalid browser observation frame id")
        seen_observations.add(obs.frame_id)
        if not _hex64(obs.frame_digest):
            raise ValueError("invalid browser observation digest")
        values=(obs.luminance_mean,obs.edge_density,obs.motion_energy,obs.scene_change)
        if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 or x>1 for x in values):
            raise ValueError("invalid browser visual feature")
    if seen_observations!=seen_frames:
        raise ValueError("browser visual observation coverage mismatch")

def accept_browser_visual(custody:ConsentBoundAnalysisQueue,envelope:BrowserVisualEnvelope,*,
    now:float,authorized:bool,max_frames:int=1000)->AcceptedBrowserVisual:
    if not authorized: raise PermissionError("browser visual import requires authorization")
    if envelope.schema!=SCHEMA: raise ValueError("unsupported browser visual schema")
    _preflight_envelope(envelope,max_frames=max_frames)
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
    extracted=tuple((x.captured_at_ms,x.frame_digest,f"browser-frame://{i}")
      for i,x in enumerate(envelope.frames))
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
    canonical_evidence=sha256(json.dumps({"schema":"dragon.accepted-visual.v1",
      "owner":envelope.owner,"job_id":envelope.job_id,"recording_digest":job.recording_digest,
      "consent_id":binding.consent_id,"consent_scope_digest":binding.scope_digest,
      "decoder_version":envelope.decoder_version,"retention_until":envelope.retention_until,"source_batch":source.batch_fingerprint,
      "observations":features.observation_fingerprint},sort_keys=True,separators=(",",":"),
      allow_nan=False).encode()).hexdigest()
    return AcceptedBrowserVisual(expected,canonical_evidence,features)
