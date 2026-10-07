"""Multimodal ports — text, image, audio, video all speak Thought.

Every modality collapses to a house dialect string plus a fixed-width
embedding the callosum can fuse. Missing codecs degrade to caption
stand-ins. Zero crash: every decode returns a Thought.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

from skeleton.cortex.port import Thought


def _embed(blob: bytes, dim: int = 8) -> list:
    h = hashlib.sha256(blob or b"\x00").digest()
    out = []
    i = 0
    while len(out) < dim:
        chunk = h[i % len(h)]
        out.append(((chunk / 255.0) * 2.0) - 1.0)
        i += 1
        if i % 32 == 0:
            h = hashlib.sha256(h).digest()
    return out


class ModalityPort:
    name = "modality"
    scale = "injected"
    modality = "text"

    def __init__(self, slot: str = "right", *, name: str | None = None) -> None:
        self.slot = slot
        self.name = name or self.modality

    def think(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        return self.decode_thought(stimulus or "", context or {})

    def decode_thought(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        return Thought(
            slot=self.slot, kind=f"modal-{self.modality}",
            text=(stimulus or self.modality)[:400],
            confidence=0.55, tags=("modal", self.modality, self.slot),
        )

    def fit(self, text: str) -> int:
        return 0

    def decode(self, stimulus: str, *, n: int = 8, seed: int = 0) -> str:
        return self.decode_thought(stimulus or "", {}).text

    def snapshot(self) -> Dict[str, Any]:
        return {"kind": "modality", "modality": self.modality, "slot": self.slot, "name": self.name}

    @classmethod
    def from_snapshot(cls, data: Dict[str, Any], *, slot: str | None = None) -> "ModalityPort":
        return cls(slot=slot or str((data or {}).get("slot") or "right"))

    def perplexity(self, texts) -> float:
        return 1.0


class TextPort(ModalityPort):
    modality = "text"

    def decode_thought(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        return Thought(
            slot=self.slot, kind="modal-text",
            text=(stimulus or "")[:400],
            confidence=0.9, tags=("modal", "text", self.slot),
        )


class ImagePort(ModalityPort):
    modality = "image"

    def decode_thought(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        raw = context.get("image_bytes") or context.get("image") or b""
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        emb = _embed(bytes(raw) or (stimulus or "").encode(), 8)
        caption = stimulus or context.get("caption") or "image gestalt spatial era"
        return Thought(
            slot=self.slot, kind="modal-image",
            text=f"IMAGE {caption[:200]}",
            confidence=0.78, tags=("modal", "image", "gestalt", self.slot),
            numbers=tuple(emb),
        )


class AudioPort(ModalityPort):
    modality = "audio"

    def decode_thought(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        raw = context.get("audio_bytes") or b""
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        emb = _embed(bytes(raw) or (stimulus or "audio").encode(), 8)
        return Thought(
            slot=self.slot, kind="modal-audio",
            text=f"AUDIO {stimulus[:200] or 'wave'}",
            confidence=0.74, tags=("modal", "audio", self.slot),
            numbers=tuple(emb),
        )


class VideoPort(ModalityPort):
    modality = "video"

    def decode_thought(self, stimulus: str, context: Dict[str, Any]) -> Thought:
        n = int(context.get("frames") or 1)
        raw = context.get("video_bytes") or b""
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        emb = _embed(bytes(raw) or f"{stimulus}:{n}".encode(), 8)
        return Thought(
            slot=self.slot, kind="modal-video",
            text=f"VIDEO frames={n} {stimulus[:160]}",
            confidence=0.7, tags=("modal", "video", "spatial", self.slot),
            numbers=tuple(emb),
        )


PORTS = {"text": TextPort, "image": ImagePort, "audio": AudioPort, "video": VideoPort}


def open_modality(modality: str, *, slot: str = "right") -> ModalityPort:
    cls = PORTS.get((modality or "text").lower(), TextPort)
    return cls(slot=slot)
