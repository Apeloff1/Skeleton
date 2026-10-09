"""Streaming video session state with strict time and resource budgets."""
from __future__ import annotations
from dataclasses import dataclass,field
from .video_digest import VideoObservation,VideoKnowledgeChunk,digest_video_observations,validate_observation

@dataclass
class VideoStreamSession:
    source_url:str
    window_ms:int=30_000
    max_observations:int=10_000
    max_lateness_ms:int=10_000
    _buffer:list[VideoObservation]=field(default_factory=list)
    _watermark_ms:int=0
    _closed:bool=False
    _accepted:int=0

    def push(self,observation:VideoObservation)->None:
        if self._closed:raise RuntimeError("video stream is closed")
        validate_observation(observation)
        if self._accepted>=self.max_observations:raise ValueError("video observation budget exhausted")
        if observation.start_ms+self.max_lateness_ms<self._watermark_ms:
            raise ValueError("late observation exceeds watermark tolerance")
        self._buffer.append(observation)
        self._accepted+=1
        self._watermark_ms=max(self._watermark_ms,observation.start_ms)

    def flush_ready(self)->tuple[VideoKnowledgeChunk,...]:
        """Flush complete time windows; late-arrival allowance prevents premature sealing."""
        cutoff=max(0,self._watermark_ms-self.max_lateness_ms)
        ready_before=(cutoff//self.window_ms)*self.window_ms
        ready=[o for o in self._buffer if ((o.start_ms//self.window_ms)+1)*self.window_ms<=ready_before and o.end_ms<=ready_before]
        self._buffer=[o for o in self._buffer if not (((o.start_ms//self.window_ms)+1)*self.window_ms<=ready_before and o.end_ms<=ready_before)]
        return digest_video_observations(self.source_url,ready,window_ms=self.window_ms)

    def close(self)->tuple[VideoKnowledgeChunk,...]:
        if self._closed:raise RuntimeError("video stream already closed")
        self._closed=True
        result=digest_video_observations(self.source_url,self._buffer,window_ms=self.window_ms)
        self._buffer.clear()
        return result
