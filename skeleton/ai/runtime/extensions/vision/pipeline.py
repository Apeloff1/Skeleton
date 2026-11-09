"""Resource-bounded, provenance-preserving vision contracts for VOL-154."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
_FORMATS = frozenset({"png", "jpeg", "webp"})
_MAX_DIMENSION = 1_000_000
_MAX_PIXELS = 1_000_000_000
_MAX_ENCODED_BYTES = 2_000_000_000


class VisionError(ValueError):
    pass


def _id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise VisionError(f"{field} must be stable identifier")
    return value


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise VisionError(f"{field} must be lowercase sha256")
    return value


def _positive_int(value: object, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise VisionError(f"{field} outside safety bound")
    return value


@dataclass(frozen=True, slots=True)
class ImageAsset:
    asset_id: str
    source_digest: str
    format: str
    width: int
    height: int
    encoded_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _id(self.asset_id, "asset_id"))
        object.__setattr__(self, "source_digest", _sha(self.source_digest, "source_digest"))
        if not isinstance(self.format, str) or self.format.lower() not in _FORMATS:
            raise VisionError("unsupported image format")
        object.__setattr__(self, "format", self.format.lower())
        _positive_int(self.width, "width", _MAX_DIMENSION)
        _positive_int(self.height, "height", _MAX_DIMENSION)
        _positive_int(self.encoded_bytes, "encoded_bytes", _MAX_ENCODED_BYTES)


@dataclass(frozen=True, slots=True)
class ImageLimits:
    max_width: int
    max_height: int
    max_pixels: int
    max_encoded_bytes: int

    def __post_init__(self) -> None:
        _positive_int(self.max_width, "max_width", _MAX_DIMENSION)
        _positive_int(self.max_height, "max_height", _MAX_DIMENSION)
        _positive_int(self.max_pixels, "max_pixels", _MAX_PIXELS)
        _positive_int(self.max_encoded_bytes, "max_encoded_bytes", _MAX_ENCODED_BYTES)

    def admit(self, asset: object) -> bool:
        if not isinstance(asset, ImageAsset):
            raise VisionError("typed image asset required")
        if (
            asset.width > self.max_width
            or asset.height > self.max_height
            or asset.width * asset.height > self.max_pixels
            or asset.encoded_bytes > self.max_encoded_bytes
        ):
            raise VisionError("image exceeds decode limits")
        return True


@dataclass(frozen=True, slots=True)
class ImageRegion:
    asset_id: str
    x: int
    y: int
    width: int
    height: int
    transform_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _id(self.asset_id, "asset_id"))
        if isinstance(self.x, bool) or not isinstance(self.x, int) or self.x < 0:
            raise VisionError("invalid region origin")
        if isinstance(self.y, bool) or not isinstance(self.y, int) or self.y < 0:
            raise VisionError("invalid region origin")
        _positive_int(self.width, "region width", _MAX_DIMENSION)
        _positive_int(self.height, "region height", _MAX_DIMENSION)
        object.__setattr__(
            self, "transform_digest", _sha(self.transform_digest, "transform_digest")
        )

    def validate(self, asset: object) -> bool:
        if not isinstance(asset, ImageAsset):
            raise VisionError("typed image asset required")
        if (
            self.asset_id != asset.asset_id
            or self.x > asset.width - self.width
            or self.y > asset.height - self.height
        ):
            raise VisionError("region outside source image")
        return True


@dataclass(frozen=True, slots=True)
class VisionResult:
    region: ImageRegion
    source_digest: str
    model_digest: str
    confidence: float
    payload_digest: str
    result_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.region, ImageRegion):
            raise VisionError("typed region required")
        object.__setattr__(self, "source_digest", _sha(self.source_digest, "source_digest"))
        object.__setattr__(self, "model_digest", _sha(self.model_digest, "model_digest"))
        object.__setattr__(self, "payload_digest", _sha(self.payload_digest, "payload_digest"))
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise VisionError("invalid confidence")
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise VisionError("invalid confidence")
        expected = hashlib.sha256(
            json.dumps(
                {
                    "asset_id": self.region.asset_id,
                    "source_digest": self.source_digest,
                    "region": (
                        self.region.x,
                        self.region.y,
                        self.region.width,
                        self.region.height,
                        self.region.transform_digest,
                    ),
                    "model_digest": self.model_digest,
                    "confidence": float(self.confidence),
                    "payload_digest": self.payload_digest,
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        supplied = _sha(self.result_digest, "result_digest")
        if supplied != expected:
            raise VisionError("result digest does not bind exact provenance")

    @classmethod
    def create(
        cls,
        region: ImageRegion,
        asset: ImageAsset,
        model_digest: str,
        confidence: float,
        payload_digest: str,
    ) -> "VisionResult":
        if not isinstance(region, ImageRegion) or not isinstance(asset, ImageAsset):
            raise VisionError("typed region and asset required")
        region.validate(asset)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise VisionError("invalid confidence")
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise VisionError("invalid confidence")
        normalized_confidence = float(confidence)
        body = {
            "asset_id": region.asset_id,
            "source_digest": asset.source_digest,
            "region": (region.x, region.y, region.width, region.height, region.transform_digest),
            "model_digest": _sha(model_digest, "model_digest"),
            "confidence": normalized_confidence,
            "payload_digest": _sha(payload_digest, "payload_digest"),
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        return cls(region, asset.source_digest, model_digest, normalized_confidence, payload_digest, digest)


__all__ = ["ImageAsset", "ImageLimits", "ImageRegion", "VisionError", "VisionResult"]
