"""Asset kind taxonomy + quality gates for Media Studio deepen."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Sequence, Tuple


class AssetKind(str, Enum):
    TEXTURE = "texture"
    AUDIO = "audio"
    VIDEO = "video"
    MESH = "mesh"
    SHADER = "shader"
    FONT = "font"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class QualityGate:
    name: str
    min_bytes: int
    max_bytes: int
    required_exts: Tuple[str, ...]
    checksum_required: bool = True

    def check(self, size: int, ext: str, has_checksum: bool) -> List[str]:
        issues: List[str] = []
        if size < self.min_bytes:
            issues.append("too_small")
        if size > self.max_bytes:
            issues.append("too_large")
        if self.required_exts and ext.lower().lstrip(".") not in self.required_exts:
            issues.append("bad_ext")
        if self.checksum_required and not has_checksum:
            issues.append("missing_checksum")
        return issues


GATES: Dict[AssetKind, QualityGate] = {
    AssetKind.TEXTURE: QualityGate("texture", 64, 50_000_000, ("png", "jpg", "jpeg", "webp", "ktx2")),
    AssetKind.AUDIO: QualityGate("audio", 256, 200_000_000, ("wav", "ogg", "mp3", "flac")),
    AssetKind.VIDEO: QualityGate("video", 1024, 2_000_000_000, ("mp4", "webm", "mkv")),
    AssetKind.MESH: QualityGate("mesh", 128, 500_000_000, ("gltf", "glb", "obj", "fbx")),
    AssetKind.SHADER: QualityGate("shader", 16, 1_000_000, ("glsl", "hlsl", "wgsl", "spv")),
    AssetKind.FONT: QualityGate("font", 64, 50_000_000, ("ttf", "otf", "woff2")),
    AssetKind.DOCUMENT: QualityGate("document", 1, 20_000_000, ("md", "json", "yaml", "yml", "txt")),
    AssetKind.UNKNOWN: QualityGate("unknown", 0, 100_000_000, (), checksum_required=False),
}

PIPELINES: Dict[AssetKind, Tuple[str, ...]] = {
    AssetKind.TEXTURE: ("ingest", "validate", "mipmap", "compress", "thumbnail", "publish"),
    AssetKind.AUDIO: ("ingest", "validate", "normalize", "waveform", "publish"),
    AssetKind.VIDEO: ("ingest", "validate", "transcode", "thumbnail", "waveform", "publish"),
    AssetKind.MESH: ("ingest", "validate", "lod", "thumbnail", "publish"),
    AssetKind.SHADER: ("ingest", "validate", "compile", "publish"),
    AssetKind.FONT: ("ingest", "validate", "subset", "publish"),
    AssetKind.DOCUMENT: ("ingest", "validate", "publish"),
    AssetKind.UNKNOWN: ("ingest", "publish"),
}


def decide_kind_pipeline(kind: AssetKind) -> Tuple[str, ...]:
    return PIPELINES[kind]


def infer_kind(ext: str) -> AssetKind:
    e = ext.lower().lstrip(".")
    for kind, gate in GATES.items():
        if e in gate.required_exts:
            return kind
    return AssetKind.UNKNOWN


def quality_score_0(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 0 * 0.0001))


def stage_weight_0(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 0 * 0.001


def quality_score_1(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 1 * 0.0001))


def stage_weight_1(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 1 * 0.001


def quality_score_2(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 2 * 0.0001))


def stage_weight_2(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 2 * 0.001


def quality_score_3(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 3 * 0.0001))


def stage_weight_3(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 3 * 0.001


def quality_score_4(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 4 * 0.0001))


def stage_weight_4(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 4 * 0.001


def quality_score_5(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 5 * 0.0001))


def stage_weight_5(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 5 * 0.001


def quality_score_6(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 6 * 0.0001))


def stage_weight_6(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 6 * 0.001


def quality_score_7(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 7 * 0.0001))


def stage_weight_7(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 7 * 0.001


def quality_score_8(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 8 * 0.0001))


def stage_weight_8(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 8 * 0.001


def quality_score_9(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 9 * 0.0001))


def stage_weight_9(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 9 * 0.001


def quality_score_10(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 10 * 0.0001))


def stage_weight_10(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 10 * 0.001


def quality_score_11(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 11 * 0.0001))


def stage_weight_11(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 11 * 0.001


def quality_score_12(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 12 * 0.0001))


def stage_weight_12(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 12 * 0.001


def quality_score_13(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 13 * 0.0001))


def stage_weight_13(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 13 * 0.001


def quality_score_14(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 14 * 0.0001))


def stage_weight_14(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 14 * 0.001


def quality_score_15(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 15 * 0.0001))


def stage_weight_15(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 15 * 0.001


def quality_score_16(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 16 * 0.0001))


def stage_weight_16(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 16 * 0.001


def quality_score_17(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 17 * 0.0001))


def stage_weight_17(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 17 * 0.001


def quality_score_18(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 18 * 0.0001))


def stage_weight_18(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 18 * 0.001


def quality_score_19(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 19 * 0.0001))


def stage_weight_19(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 19 * 0.001


def quality_score_20(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 20 * 0.0001))


def stage_weight_20(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 20 * 0.001


def quality_score_21(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 21 * 0.0001))


def stage_weight_21(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 21 * 0.001


def quality_score_22(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 22 * 0.0001))


def stage_weight_22(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 22 * 0.001


def quality_score_23(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 23 * 0.0001))


def stage_weight_23(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 23 * 0.001


def quality_score_24(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 24 * 0.0001))


def stage_weight_24(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 24 * 0.001


def quality_score_25(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 25 * 0.0001))


def stage_weight_25(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 25 * 0.001


def quality_score_26(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 26 * 0.0001))


def stage_weight_26(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 26 * 0.001


def quality_score_27(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 27 * 0.0001))


def stage_weight_27(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 27 * 0.001


def quality_score_28(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 28 * 0.0001))


def stage_weight_28(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 28 * 0.001


def quality_score_29(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 29 * 0.0001))


def stage_weight_29(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 29 * 0.001


def quality_score_30(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 30 * 0.0001))


def stage_weight_30(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 30 * 0.001


def quality_score_31(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 31 * 0.0001))


def stage_weight_31(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 31 * 0.001


def quality_score_32(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 32 * 0.0001))


def stage_weight_32(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 32 * 0.001


def quality_score_33(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 33 * 0.0001))


def stage_weight_33(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 33 * 0.001


def quality_score_34(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 34 * 0.0001))


def stage_weight_34(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 34 * 0.001


def quality_score_35(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 35 * 0.0001))


def stage_weight_35(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 35 * 0.001


def quality_score_36(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 36 * 0.0001))


def stage_weight_36(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 36 * 0.001


def quality_score_37(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 37 * 0.0001))


def stage_weight_37(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 37 * 0.001


def quality_score_38(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 38 * 0.0001))


def stage_weight_38(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 38 * 0.001


def quality_score_39(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 39 * 0.0001))


def stage_weight_39(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 39 * 0.001


def quality_score_40(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 40 * 0.0001))


def stage_weight_40(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 40 * 0.001


def quality_score_41(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 41 * 0.0001))


def stage_weight_41(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 41 * 0.001


def quality_score_42(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 42 * 0.0001))


def stage_weight_42(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 42 * 0.001


def quality_score_43(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 43 * 0.0001))


def stage_weight_43(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 43 * 0.001


def quality_score_44(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 44 * 0.0001))


def stage_weight_44(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 44 * 0.001


def quality_score_45(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 45 * 0.0001))


def stage_weight_45(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 45 * 0.001


def quality_score_46(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 46 * 0.0001))


def stage_weight_46(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 46 * 0.001


def quality_score_47(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 47 * 0.0001))


def stage_weight_47(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 47 * 0.001


def quality_score_48(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 48 * 0.0001))


def stage_weight_48(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 48 * 0.001


def quality_score_49(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 49 * 0.0001))


def stage_weight_49(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 49 * 0.001


def quality_score_50(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 50 * 0.0001))


def stage_weight_50(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 50 * 0.001


def quality_score_51(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 51 * 0.0001))


def stage_weight_51(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 51 * 0.001


def quality_score_52(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 52 * 0.0001))


def stage_weight_52(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 52 * 0.001


def quality_score_53(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 53 * 0.0001))


def stage_weight_53(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 53 * 0.001


def quality_score_54(size: int, kind: AssetKind) -> float:
    gate = GATES[kind]
    if size <= 0:
        return 0.0
    span = max(1, gate.max_bytes - gate.min_bytes)
    mid = (gate.min_bytes + gate.max_bytes) / 2
    dist = abs(size - mid) / span
    return max(0.0, min(1.0, 1.0 - dist + 54 * 0.0001))


def stage_weight_54(stage: str) -> float:
    base = {"ingest": 1.0, "validate": 1.2, "publish": 1.5}.get(stage, 1.0)
    return base + 54 * 0.001
