"""Deterministic image observations for camera-grounded local training.

This module turns a sanitized image asset plus an exact camera pose into a
bounded, content-addressed visual observation.  It intentionally uses simple
deterministic pixel statistics instead of pretending the local recurrent model
has a learned vision encoder.  The resulting signal is nevertheless derived
from real decoded pixels and is stable enough to bind camera views, image
content, and training receipts end to end.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import hashlib
import json
import math
from typing import Iterable

from skeleton.ai.runtime.multimodal.intake import (
    Modality,
    MultimodalAsset,
)
from .multiview import CameraView


_MAX_PIXELS = 16_777_216
_GRID = 4
_HIST_BINS = 8


class VisualLearningError(RuntimeError):
    """An image cannot be converted into bounded deterministic training signal."""


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise VisualLearningError(
            "visual observation is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _sha(value: str, name: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise VisualLearningError(f"{name} must be lowercase sha256")
    return text


def _q(value: float) -> float:
    if not math.isfinite(value):
        raise VisualLearningError("visual feature must be finite")
    return round(float(value), 6)


@dataclass(frozen=True, slots=True)
class VisualTrainingObservation:
    """Pixel-derived observation bound to one exact camera view."""

    camera_view_ref: str
    asset_id: str
    asset_digest: str
    width: int
    height: int
    mean_rgb: tuple[float, float, float]
    std_rgb: tuple[float, float, float]
    luminance_histogram: tuple[float, ...]
    spatial_rgb: tuple[float, ...]
    edge_density: float
    feature_digest: str

    def __post_init__(self) -> None:
        if not self.camera_view_ref.startswith("camera-view-sha256:"):
            raise VisualLearningError(
                "camera_view_ref must use camera-view-sha256 identity"
            )
        _sha(self.camera_view_ref.split(":", 1)[1], "camera view digest")
        asset_id = str(self.asset_id).strip()
        if not asset_id:
            raise VisualLearningError("asset_id must be non-empty")
        object.__setattr__(self, "asset_id", asset_id)
        object.__setattr__(
            self,
            "asset_digest",
            _sha(self.asset_digest, "asset_digest"),
        )
        if (
            isinstance(self.width, bool)
            or isinstance(self.height, bool)
            or not isinstance(self.width, int)
            or not isinstance(self.height, int)
            or self.width < 1
            or self.height < 1
            or self.width * self.height > _MAX_PIXELS
        ):
            raise VisualLearningError("image dimensions exceed visual bounds")
        if len(self.mean_rgb) != 3 or len(self.std_rgb) != 3:
            raise VisualLearningError("RGB feature tuples must have length 3")
        if len(self.luminance_histogram) != _HIST_BINS:
            raise VisualLearningError("luminance histogram has invalid size")
        if len(self.spatial_rgb) != _GRID * _GRID * 3:
            raise VisualLearningError("spatial RGB feature has invalid size")
        for value in (
            *self.mean_rgb,
            *self.std_rgb,
            *self.luminance_histogram,
            *self.spatial_rgb,
            self.edge_density,
        ):
            if not math.isfinite(float(value)):
                raise VisualLearningError("visual feature must be finite")
        expected = _digest(self.feature_payload())
        actual = _sha(self.feature_digest, "feature_digest")
        if expected != actual:
            raise VisualLearningError(
                "feature_digest does not match visual observation"
            )
        object.__setattr__(self, "feature_digest", actual)

    def feature_payload(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.visual_training_observation.v1",
            "camera_view_ref": self.camera_view_ref,
            "asset_id": self.asset_id,
            "asset_digest": self.asset_digest,
            "width": self.width,
            "height": self.height,
            "mean_rgb": list(self.mean_rgb),
            "std_rgb": list(self.std_rgb),
            "luminance_histogram": list(self.luminance_histogram),
            "spatial_rgb": list(self.spatial_rgb),
            "edge_density": self.edge_density,
        }

    @property
    def reference(self) -> str:
        return "visual-observation-sha256:" + self.feature_digest

    def training_text(self) -> str:
        mean = ",".join(f"{value:.6f}" for value in self.mean_rgb)
        std = ",".join(f"{value:.6f}" for value in self.std_rgb)
        hist = ",".join(
            f"{value:.6f}" for value in self.luminance_histogram
        )
        spatial = ",".join(f"{value:.6f}" for value in self.spatial_rgb)
        return (
            "<|visual_observation|>\n"
            + self.reference
            + "\n<|asset_sha256|>\n"
            + self.asset_digest
            + "\n<|image_size|>\n"
            + f"{self.width}x{self.height}"
            + "\n<|mean_rgb|>\n"
            + mean
            + "\n<|std_rgb|>\n"
            + std
            + "\n<|luminance_histogram|>\n"
            + hist
            + "\n<|spatial_rgb_4x4|>\n"
            + spatial
            + "\n<|edge_density|>\n"
            + f"{self.edge_density:.6f}"
        )


def _histogram(values: Iterable[int]) -> tuple[float, ...]:
    counts = [0] * _HIST_BINS
    total = 0
    for value in values:
        index = min(_HIST_BINS - 1, int(value) * _HIST_BINS // 256)
        counts[index] += 1
        total += 1
    if total == 0:
        raise VisualLearningError("image contains no pixels")
    return tuple(_q(count / total) for count in counts)


def extract_visual_training_observation(
    *,
    asset: MultimodalAsset,
    payload: bytes,
    camera_view: CameraView,
) -> VisualTrainingObservation:
    """Decode bounded pixels and bind deterministic features to camera identity."""

    if not isinstance(asset, MultimodalAsset):
        raise TypeError("asset must be MultimodalAsset")
    if asset.modality is not Modality.IMAGE:
        raise VisualLearningError("visual training requires an image asset")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if hashlib.sha256(payload).hexdigest() != asset.content_digest:
        raise VisualLearningError("image bytes differ from sanitized asset digest")
    if not isinstance(camera_view, CameraView):
        raise TypeError("camera_view must be CameraView")

    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - CI installs Pillow.
        raise VisualLearningError("Pillow is required for visual training") from exc

    try:
        with Image.open(BytesIO(payload)) as opened:
            source_width, source_height = opened.size
            if (
                source_width < 1
                or source_height < 1
                or source_width * source_height > _MAX_PIXELS
            ):
                raise VisualLearningError(
                    "decoded image dimensions exceed visual bounds"
                )
            opened.verify()
        with Image.open(BytesIO(payload)) as opened:
            source_width, source_height = opened.size
            if (
                source_width < 1
                or source_height < 1
                or source_width * source_height > _MAX_PIXELS
            ):
                raise VisualLearningError(
                    "decoded image dimensions exceed visual bounds"
                )
            image = ImageOps.exif_transpose(opened)
            width, height = image.size
            if (
                width < 1
                or height < 1
                or width * height > _MAX_PIXELS
            ):
                raise VisualLearningError(
                    "decoded image dimensions exceed visual bounds"
                )
            metadata = dict(asset.sanitized_metadata)
            declared_width = metadata.get("width")
            declared_height = metadata.get("height")
            if declared_width is not None and declared_width != width:
                raise VisualLearningError(
                    "decoded width differs from sanitized metadata"
                )
            if declared_height is not None and declared_height != height:
                raise VisualLearningError(
                    "decoded height differs from sanitized metadata"
                )
            image = image.convert("RGB")
            # Bound compute while retaining the full image field of view.
            image.thumbnail((512, 512))
            width_small, height_small = image.size
            pixels = list(image.getdata())
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
    ) as exc:
        raise VisualLearningError("image payload cannot be decoded safely") from exc

    count = len(pixels)
    if count == 0:
        raise VisualLearningError("decoded image contains no pixels")

    means = [
        sum(pixel[channel] for pixel in pixels) / (255.0 * count)
        for channel in range(3)
    ]
    stds = []
    for channel in range(3):
        mean_raw = means[channel] * 255.0
        variance = (
            sum(
                (pixel[channel] - mean_raw) ** 2
                for pixel in pixels
            )
            / count
        )
        stds.append(math.sqrt(variance) / 255.0)

    luminance = tuple(
        int(round(0.2126 * red + 0.7152 * green + 0.0722 * blue))
        for red, green, blue in pixels
    )
    histogram = _histogram(luminance)

    spatial: list[float] = []
    for gy in range(_GRID):
        y0 = gy * height_small // _GRID
        y1 = max(y0 + 1, (gy + 1) * height_small // _GRID)
        for gx in range(_GRID):
            x0 = gx * width_small // _GRID
            x1 = max(x0 + 1, (gx + 1) * width_small // _GRID)
            cell = [
                image.getpixel((x, y))
                for y in range(y0, min(y1, height_small))
                for x in range(x0, min(x1, width_small))
            ]
            if not cell:
                cell = [image.getpixel((min(x0, width_small - 1), min(y0, height_small - 1)))]
            for channel in range(3):
                spatial.append(
                    _q(
                        sum(pixel[channel] for pixel in cell)
                        / (255.0 * len(cell))
                    )
                )

    gray = image.convert("L")
    edge_hits = 0
    comparisons = 0
    threshold = 24
    for y in range(height_small):
        for x in range(width_small):
            value = gray.getpixel((x, y))
            if x + 1 < width_small:
                comparisons += 1
                if abs(value - gray.getpixel((x + 1, y))) >= threshold:
                    edge_hits += 1
            if y + 1 < height_small:
                comparisons += 1
                if abs(value - gray.getpixel((x, y + 1))) >= threshold:
                    edge_hits += 1
    edge_density = _q(edge_hits / max(1, comparisons))

    payload_obj = {
        "schema_version": "skeleton.visual_training_observation.v1",
        "camera_view_ref": camera_view.reference,
        "asset_id": asset.asset_id,
        "asset_digest": asset.content_digest,
        "width": width,
        "height": height,
        "mean_rgb": [_q(value) for value in means],
        "std_rgb": [_q(value) for value in stds],
        "luminance_histogram": list(histogram),
        "spatial_rgb": list(spatial),
        "edge_density": edge_density,
    }
    return VisualTrainingObservation(
        camera_view_ref=camera_view.reference,
        asset_id=asset.asset_id,
        asset_digest=asset.content_digest,
        width=width,
        height=height,
        mean_rgb=tuple(payload_obj["mean_rgb"]),
        std_rgb=tuple(payload_obj["std_rgb"]),
        luminance_histogram=histogram,
        spatial_rgb=tuple(spatial),
        edge_density=edge_density,
        feature_digest=_digest(payload_obj),
    )


__all__ = [
    "VisualLearningError",
    "VisualTrainingObservation",
    "extract_visual_training_observation",
]
