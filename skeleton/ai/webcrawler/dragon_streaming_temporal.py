"""Chunk-invariant temporal segmentation with bounded live-consent checkpoints."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from statistics import median
import time
from typing import Callable

from .dragon_temporal_segmentation import FeatureFrame,TemporalEvent,SegmentationConfig
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue


@dataclass(frozen=True)
class StreamingTemporalTrace:
    events:tuple[TemporalEvent,...]
    checkpoints:int
    trace_fingerprint:str


def _validate_config(config:SegmentationConfig)->None:
    if not 3<=config.baseline_window<=1001:
        raise ValueError("invalid baseline window")
    if not 1<config.onset_multiplier<=100 or not 0<config.release_multiplier<config.onset_multiplier:
        raise ValueError("invalid hysteresis thresholds")
    if not math.isfinite(config.noise_floor) or not 0<config.noise_floor<=100:
        raise ValueError("invalid noise floor")
    if not 1<=config.min_event_frames<=config.max_event_frames<=100000:
        raise ValueError("invalid event frame bounds")
    if not 2<=config.max_frames<=1000000 or not 1<=config.max_features<=4096:
        raise ValueError("invalid feature budget")


class _TemporalSegmentationState:
    """Incremental equivalent of segment_feature_trace.

    Baseline history, hysteresis state and active-event custody survive chunk
    boundaries. A chunk boundary therefore changes cancellation latency only,
    never event semantics.
    """
    def __init__(self,config:SegmentationConfig):
        _validate_config(config)
        self.config=config
        self.previous:FeatureFrame|None=None
        self.dimension:int|None=None
        self.seen_ids:set[str]=set()
        self.history:deque[float]=deque(maxlen=config.baseline_window)
        self.change_count=0
        self.frame_count=0
        self.active_start:int|None=None
        self.active_frames:list[FeatureFrame]=[]
        self.peak_change=0.0
        self.peak_ms=0
        self.peak_indices:tuple[int,...]=()
        self.last_baseline=config.noise_floor
        self.events:list[TemporalEvent]=[]

    def _validate_frame(self,frame:FeatureFrame)->None:
        if self.frame_count>=self.config.max_frames:
            raise ValueError("frame budget exceeded")
        if not isinstance(frame.timestamp_ms,int) or frame.timestamp_ms<0:
            raise ValueError("invalid timestamp")
        if self.previous is not None and frame.timestamp_ms<=self.previous.timestamp_ms:
            raise ValueError("timestamps must increase strictly")
        if not isinstance(frame.source_frame_id,str) or not 1<=len(frame.source_frame_id)<=256:
            raise ValueError("invalid source frame id")
        if frame.source_frame_id in self.seen_ids:
            raise ValueError("duplicate source frame id")
        dimension=len(frame.features)
        if self.dimension is None:
            if not 1<=dimension<=self.config.max_features:
                raise ValueError("invalid feature dimension")
            self.dimension=dimension
        if dimension!=self.dimension or any(
            not math.isfinite(x) or not 0<=x<=1 for x in frame.features
        ):
            raise ValueError("invalid normalized feature vector")

    def _peak_features(self,a:FeatureFrame,b:FeatureFrame)->tuple[int,...]:
        return tuple(i for i,(x,y) in enumerate(zip(a.features,b.features))
                     if abs(x-y)>=self.config.noise_floor)

    def _close(self,baseline:float)->None:
        length=self.change_count-self.active_start
        if length>=self.config.min_event_frames:
            self.events.append(TemporalEvent(
                self.active_frames[0].timestamp_ms,
                self.peak_ms,
                self.active_frames[-1].timestamp_ms,
                round(self.peak_change,6),
                round(baseline,6),
                self.peak_indices,
                tuple(x.source_frame_id for x in self.active_frames),
            ))
        self.active_start=None
        self.active_frames=[]
        self.peak_change=0.0
        self.peak_ms=0
        self.peak_indices=()

    def feed(self,frames:tuple[FeatureFrame,...])->None:
        for frame in frames:
            self._validate_frame(frame)
            self.seen_ids.add(frame.source_frame_id)
            self.frame_count+=1
            if self.previous is None:
                self.previous=frame
                continue

            previous=self.previous
            change=max(abs(a-b) for a,b in zip(previous.features,frame.features))
            index=self.change_count
            baseline=median(self.history) if self.history else self.config.noise_floor
            self.last_baseline=baseline
            threshold=max(self.config.noise_floor,baseline)*self.config.onset_multiplier
            release=max(self.config.noise_floor,baseline)*self.config.release_multiplier

            if self.active_start is None:
                if change>=threshold:
                    self.active_start=index
                    self.active_frames=[previous,frame]
                    self.peak_change=change
                    self.peak_ms=frame.timestamp_ms
                    self.peak_indices=self._peak_features(previous,frame)
            else:
                self.active_frames.append(frame)
                if change>self.peak_change:
                    self.peak_change=change
                    self.peak_ms=frame.timestamp_ms
                    self.peak_indices=self._peak_features(previous,frame)
                length=index-self.active_start+1
                if change<=release or length>=self.config.max_event_frames:
                    self.change_count+=1
                    self.history.append(change)
                    self.previous=frame
                    self._close(baseline)
                    continue

            self.change_count+=1
            self.history.append(change)
            self.previous=frame

    def finish(self)->tuple[TemporalEvent,...]:
        if self.active_start is not None:
            last_index=self.change_count-1
            baseline=(self.config.noise_floor
                      if self.active_start==last_index else self.last_baseline)
            self._close(baseline)
        return tuple(self.events)


def segment_streaming_with_consent(custody:ConsentBoundAnalysisQueue,owner:str,job_id:str,
    frames:tuple[FeatureFrame,...],*,now:float|None=None,clock:Callable[[],float]|None=None,
    authorized:bool,checkpoint_frames:int=256,
    config:SegmentationConfig=SegmentationConfig())->StreamingTemporalTrace:
    if not authorized:
        raise PermissionError("streaming temporal analysis requires authorization")
    if not 2<=checkpoint_frames<=10000:
        raise ValueError("invalid checkpoint frame budget")
    _validate_config(config)
    if len(frames)>config.max_frames:
        raise ValueError("frame budget exceeded")
    if clock is not None and now is not None:
        raise ValueError("provide clock or now, not both")
    read_clock=clock or ((lambda: now) if now is not None else time.time)
    checkpoints=0
    last_now:float|None=None

    def checkpoint()->None:
        nonlocal checkpoints,last_now
        current=read_clock()
        if isinstance(current,bool) or not isinstance(current,(int,float)) or not math.isfinite(current):
            raise ValueError("invalid checkpoint clock")
        if last_now is not None and current<last_now:
            raise RuntimeError("checkpoint clock regressed")
        custody.require_active(owner,job_id,now=current,authorized=True)
        last_now=float(current)
        checkpoints+=1

    state=_TemporalSegmentationState(config)
    if not frames:
        checkpoint()
    else:
        for start in range(0,len(frames),checkpoint_frames):
            checkpoint()
            state.feed(frames[start:start+checkpoint_frames])
    checkpoint()
    events=state.finish()
    fp=sha256(json.dumps({
        "frames":[[f.timestamp_ms,f.features,f.source_frame_id] for f in frames],
        "events":[[e.start_ms,e.peak_ms,e.end_ms,e.peak_change,e.baseline_change,
                   e.feature_indices,e.source_frame_ids] for e in events],
        "config":vars(config),
    },sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return StreamingTemporalTrace(events,checkpoints,fp)
