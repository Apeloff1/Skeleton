"""Deterministic pixel-derived features for local multimodal learning.

This layer intentionally sits after multimodal intake/decoding.  The intake
contract authenticates the compressed/source asset.  A decoder supplies
canonical row-major uint8 pixels and declares the exact source asset digest it
decoded.  This module verifies that source binding, dimensions, and metadata,
then extracts fixed-point spatial/color/edge features with no network calls and
no instruction authority.

The result can be bound to a camera view and fed to the text-native local
trainer as discrete feature tokens.  Raw pixels are never interpreted as
instructions and are not stored in the feature receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Sequence

from skeleton.ai.runtime.multimodal.intake import (
    Modality,
    MultimodalAsset,
)


_CAMERA_VIEW_REF = re.compile(r"^camera-view-sha256:[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_PIXELS = 64 * 1024 * 1024
_FEATURE_SCALE = 1_000_000


class VisualFeatureError(RuntimeError):
    """Decoded image evidence cannot safely enter the visual feature plane."""


def _json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise VisualFeatureError(
            "visual feature identity is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise VisualFeatureError(f"{name} must be sha256 text")
    result = value.strip().lower()
    if _SHA256.fullmatch(result) is None:
        raise VisualFeatureError(f"{name} must be lowercase sha256")
    return result


def _integer(value: object, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise VisualFeatureError(f"{name} must be an integer")
    if not minimum <= value <= maximum:
        raise VisualFeatureError(
            f"{name} must be in [{minimum}, {maximum}]"
        )
    return value


def _fixed_ratio(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        return 0
    return int((numerator * _FEATURE_SCALE + denominator // 2) // denominator)


@dataclass(frozen=True, slots=True)
class VisualFeatureObservation:
    """Content-addressed pixel statistics from one authenticated image decode."""

    asset_id: str
    asset_content_digest: str
    decoder_id: str
    decoder_source_digest: str
    decoded_pixel_digest: str
    width: int
    height: int
    channels: int
    feature_names: tuple[str, ...]
    feature_values: tuple[int, ...]
    instruction_trusted: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not self.asset_id.strip():
            raise VisualFeatureError("asset_id must be non-empty")
        if not isinstance(self.decoder_id, str) or not self.decoder_id.strip():
            raise VisualFeatureError("decoder_id must be non-empty")
        object.__setattr__(
            self,
            "asset_content_digest",
            _sha(self.asset_content_digest, "asset_content_digest"),
        )
        object.__setattr__(
            self,
            "decoder_source_digest",
            _sha(self.decoder_source_digest, "decoder_source_digest"),
        )
        object.__setattr__(
            self,
            "decoded_pixel_digest",
            _sha(self.decoded_pixel_digest, "decoded_pixel_digest"),
        )
        if self.asset_content_digest != self.decoder_source_digest:
            raise VisualFeatureError(
                "decoder source digest does not match sanitized image asset"
            )
        _integer(self.width, "width", 1, 65_535)
        _integer(self.height, "height", 1, 65_535)
        _integer(self.channels, "channels", 1, 4)
        if self.channels not in {1, 3, 4}:
            raise VisualFeatureError("channels must be grayscale, RGB, or RGBA")
        if self.width * self.height > _MAX_PIXELS:
            raise VisualFeatureError("decoded image exceeds pixel bound")
        if not self.feature_names or len(self.feature_names) != len(
            self.feature_values
        ):
            raise VisualFeatureError(
                "feature names and values must be non-empty and aligned"
            )
        if len(self.feature_names) > 128:
            raise VisualFeatureError("visual feature count exceeds hard bound")
        if len(set(self.feature_names)) != len(self.feature_names):
            raise VisualFeatureError("visual feature names must be unique")
        for name in self.feature_names:
            if (
                not isinstance(name, str)
                or not name
                or len(name) > 64
                or any(ch.isspace() for ch in name)
            ):
                raise VisualFeatureError(
                    "visual feature names must be compact normalized text"
                )
        for value in self.feature_values:
            _integer(
                value,
                "visual feature value",
                0,
                _FEATURE_SCALE,
            )
        if self.instruction_trusted is not False:
            raise VisualFeatureError(
                "pixel-derived visual features never receive instruction authority"
            )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.visual_features.v1",
                "asset_id": self.asset_id,
                "asset_content_digest": self.asset_content_digest,
                "decoder_id": self.decoder_id,
                "decoder_source_digest": self.decoder_source_digest,
                "decoded_pixel_digest": self.decoded_pixel_digest,
                "width": self.width,
                "height": self.height,
                "channels": self.channels,
                "feature_names": list(self.feature_names),
                "feature_values": list(self.feature_values),
                "instruction_trusted": False,
            }
        )

    @property
    def reference(self) -> str:
        return "visual-feature-sha256:" + self.digest

    def token_text(self) -> str:
        """Stable discrete representation consumable by the local tokenizer."""

        tokens = [
            f"vf:{name}:{value}"
            for name, value in zip(
                self.feature_names,
                self.feature_values,
                strict=True,
            )
        ]
        return (
            "<|visual_feature_observation|>\n"
            + self.reference
            + "\n"
            + " ".join(tokens)
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.visual_features.v1",
            "reference": self.reference,
            "asset_id": self.asset_id,
            "asset_content_digest": self.asset_content_digest,
            "decoder_id": self.decoder_id,
            "decoder_source_digest": self.decoder_source_digest,
            "decoded_pixel_digest": self.decoded_pixel_digest,
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "feature_names": list(self.feature_names),
            "feature_values": list(self.feature_values),
            "instruction_trusted": False,
        }


@dataclass(frozen=True, slots=True)
class CameraBoundVisualFeature:
    """One pixel-derived observation bound to an exact camera pose/coverage."""

    observation: VisualFeatureObservation
    camera_view_ref: str
    camera_coverage_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.observation, VisualFeatureObservation):
            raise TypeError(
                "observation must be VisualFeatureObservation"
            )
        if (
            not isinstance(self.camera_view_ref, str)
            or _CAMERA_VIEW_REF.fullmatch(self.camera_view_ref) is None
        ):
            raise VisualFeatureError(
                "camera_view_ref must be canonical camera-view-sha256 identity"
            )
        object.__setattr__(
            self,
            "camera_coverage_digest",
            _sha(
                self.camera_coverage_digest,
                "camera_coverage_digest",
            ),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "schema_version": "skeleton.camera_visual_feature.v1",
                "visual_feature_ref": self.observation.reference,
                "camera_view_ref": self.camera_view_ref,
                "camera_coverage_digest": self.camera_coverage_digest,
            }
        )

    @property
    def reference(self) -> str:
        return "camera-visual-sha256:" + self.digest

    def token_text(self) -> str:
        return (
            "<|camera_visual_feature|>\n"
            + self.camera_view_ref
            + "\ncoverage:"
            + self.camera_coverage_digest
            + "\n"
            + self.observation.token_text()
        )


def extract_visual_features(
    asset: MultimodalAsset,
    *,
    pixels: bytes,
    width: int,
    height: int,
    channels: int,
    decoder_id: str,
    decoder_source_digest: str,
) -> VisualFeatureObservation:
    """Extract fixed-point spatial/color/edge features from decoded uint8 pixels."""

    if not isinstance(asset, MultimodalAsset):
        raise TypeError("asset must be MultimodalAsset")
    if asset.modality is not Modality.IMAGE:
        raise VisualFeatureError("visual features require an image asset")
    if asset.instruction_trusted is not False:
        raise VisualFeatureError(
            "image asset unexpectedly has instruction authority"
        )
    if not isinstance(pixels, bytes):
        raise VisualFeatureError("pixels must be immutable bytes")
    width_i = _integer(width, "width", 1, 65_535)
    height_i = _integer(height, "height", 1, 65_535)
    channels_i = _integer(channels, "channels", 1, 4)
    if channels_i not in {1, 3, 4}:
        raise VisualFeatureError("channels must be grayscale, RGB, or RGBA")
    pixel_count = width_i * height_i
    if pixel_count > _MAX_PIXELS:
        raise VisualFeatureError("decoded image exceeds pixel bound")
    expected = pixel_count * channels_i
    if len(pixels) != expected:
        raise VisualFeatureError(
            "pixel byte length does not match dimensions/channels"
        )
    source_digest = _sha(
        decoder_source_digest,
        "decoder_source_digest",
    )
    if source_digest != asset.content_digest:
        raise VisualFeatureError(
            "decoder source digest does not match sanitized image asset"
        )
    metadata = dict(asset.sanitized_metadata)
    for key, actual in (("width", width_i), ("height", height_i)):
        declared = metadata.get(key)
        if declared is not None:
            if (
                isinstance(declared, bool)
                or not isinstance(declared, int)
                or declared != actual
            ):
                raise VisualFeatureError(
                    f"decoded {key} differs from sanitized metadata"
                )

    # NumPy is local-inference's only numeric dependency. Keep all reductions
    # integer/fixed-point to make feature receipts stable across platforms.
    try:
        import numpy as np
    except ImportError as exc:
        raise VisualFeatureError(
            "NumPy is required for visual feature extraction"
        ) from exc

    raw = np.frombuffer(pixels, dtype=np.uint8)
    image = raw.reshape((height_i, width_i, channels_i))
    color = image[:, :, : min(channels_i, 3)].astype(np.uint64)
    if channels_i == 1:
        luminance = color[:, :, 0]
    else:
        # Integer BT.601-style luma, scaled by 1000.
        luminance = (
            color[:, :, 0] * 299
            + color[:, :, 1] * 587
            + color[:, :, 2] * 114
        ) // 1000

    names: list[str] = []
    values: list[int] = []

    def add_mean(name: str, array) -> None:
        total = int(array.astype(np.uint64).sum())
        denom = int(array.size) * 255
        names.append(name)
        values.append(_fixed_ratio(total, denom))

    def add_mean_square(name: str, array) -> None:
        square = array.astype(np.uint64)
        total = int((square * square).sum())
        denom = int(array.size) * 255 * 255
        names.append(name)
        values.append(_fixed_ratio(total, denom))

    channel_labels = ("gray",) if channels_i == 1 else ("r", "g", "b")
    for index, label in enumerate(channel_labels):
        channel = color[:, :, index]
        add_mean(f"{label}_mean", channel)
        add_mean_square(f"{label}_mean_square", channel)

    add_mean("luma_mean", luminance)
    add_mean_square("luma_mean_square", luminance)

    # 4x4 spatial luma grid. Empty cells on tiny images deterministically map
    # to zero rather than being silently dropped.
    for gy in range(4):
        y0 = (gy * height_i) // 4
        y1 = ((gy + 1) * height_i) // 4
        for gx in range(4):
            x0 = (gx * width_i) // 4
            x1 = ((gx + 1) * width_i) // 4
            cell = luminance[y0:y1, x0:x1]
            names.append(f"grid_{gy}_{gx}")
            if cell.size:
                values.append(
                    _fixed_ratio(
                        int(cell.astype(np.uint64).sum()),
                        int(cell.size) * 255,
                    )
                )
            else:
                values.append(0)

    # Eight-bin luminance distribution.
    histogram = np.bincount(
        (luminance.reshape(-1) * 8 // 256).astype(np.int64),
        minlength=8,
    )
    for index in range(8):
        names.append(f"luma_hist_{index}")
        values.append(
            _fixed_ratio(int(histogram[index]), pixel_count)
        )

    # Edge-energy summaries from adjacent luma differences.
    if width_i > 1:
        horizontal = np.abs(
            luminance[:, 1:].astype(np.int16)
            - luminance[:, :-1].astype(np.int16)
        ).astype(np.uint64)
        add_mean("edge_horizontal", horizontal)
    else:
        names.append("edge_horizontal")
        values.append(0)
    if height_i > 1:
        vertical = np.abs(
            luminance[1:, :].astype(np.int16)
            - luminance[:-1, :].astype(np.int16)
        ).astype(np.uint64)
        add_mean("edge_vertical", vertical)
    else:
        names.append("edge_vertical")
        values.append(0)

    # Alpha is useful for compositing/segmentation signal but never interpreted
    # as authority.
    if channels_i == 4:
        add_mean("alpha_mean", image[:, :, 3])

    return VisualFeatureObservation(
        asset_id=asset.asset_id,
        asset_content_digest=asset.content_digest,
        decoder_id=decoder_id.strip(),
        decoder_source_digest=source_digest,
        decoded_pixel_digest=hashlib.sha256(pixels).hexdigest(),
        width=width_i,
        height=height_i,
        channels=channels_i,
        feature_names=tuple(names),
        feature_values=tuple(values),
        instruction_trusted=False,
    )


def bind_visual_feature_to_camera(
    observation: VisualFeatureObservation,
    *,
    camera_view_ref: str,
    camera_coverage_digest: str,
) -> CameraBoundVisualFeature:
    """Bind a pixel feature receipt to one exact camera view identity."""

    return CameraBoundVisualFeature(
        observation=observation,
        camera_view_ref=camera_view_ref,
        camera_coverage_digest=camera_coverage_digest,
    )


__all__ = [
    "CameraBoundVisualFeature",
    "VisualFeatureError",
    "VisualFeatureObservation",
    "bind_visual_feature_to_camera",
    "extract_visual_features",
]
