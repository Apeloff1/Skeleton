"""Measured handcrafted media signals over existing verified source authority.

The descriptors encode color/spatial pixels and PCM spectral/temporal signals.
They are neither semantic embeddings nor transcription or recognition results.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import wave
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import pairwise
from types import MappingProxyType
from typing import TYPE_CHECKING

import numpy as np

from skeleton.ai.runtime.multimodal.intake import VerifiedMultimodalAsset
from skeleton.ai.runtime.retrieval.fusion import ScoredResult

from .multimodal import (
    LearningModality,
    MultimodalCorpus,
    MultimodalFoundationError,
    _digest,
    _json,
    _sha,
    _text,
)
from .temporal import _bounded_refs, _clone_corpus, _integer, _publish_corpus, _seconds

if TYPE_CHECKING:
    from skeleton.ai.runtime.training.data import (
        DatasetRegistry,
        MaterializedDatasetReceipt,
        SourceAuthorityBinding,
    )

_SCHEMA = "skeleton.ai.multimodal_content_retrieval.v1"
_IMAGE_ALGORITHM = "RGBA-black-alpha:spatial4x4:hist8x3:luma-gradient:integer-v1"
_AUDIO_ALGORITHM = f"PCM-mono:temporal8:fft2048x8:physical-bands16:q16-v1:numpy@{np.__version__}"
_CEILINGS = {
    "max_records": 256,
    "max_source_bytes": 524288,
    "max_total_source_bytes": 33554432,
    "max_image_pixels": 1048576,
    "max_audio_sample_frames": 262144,
    "max_audio_seconds": 60,
}
_BANDS = (
    0,
    125,
    250,
    500,
    1000,
    1500,
    2000,
    3000,
    4000,
    6000,
    8000,
    10000,
    12000,
    16000,
    24000,
    48000,
    96000,
)


def _q(value: float) -> int:
    if not math.isfinite(value):
        raise MultimodalFoundationError("measured signal is not finite")
    return round(min(1.0, max(0.0, value)) * 65535)


def _ratio(numerator: int, denominator: int) -> int:
    return 0 if not denominator else (int(numerator) * 65535 + denominator // 2) // denominator


def _window(value: tuple[float, float] | None) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, tuple) or len(value) != 2:
        raise MultimodalFoundationError("time span requires an explicit start/end tuple")
    start, end = (_seconds("time_seconds", component) for component in value)
    if end < start:
        raise MultimodalFoundationError("time span is reversed")
    return start, end


def _record_data(record) -> dict[str, object]:
    projection = record.text_projection
    return {
        "record_id": record.record_id,
        "modality": record.modality.value,
        "asset_digest": record.asset_digest,
        "media_type": record.media_type,
        "source_refs": list(record.source_refs),
        "rights_refs": list(record.rights_refs),
        "lineage_refs": list(record.lineage_refs),
        "simulated": record.simulated,
        "embedded_instruction_detected": record.embedded_instruction_detected,
        "metadata": dict(record.metadata),
        "text_projection": (
            None
            if projection is None
            else {
                "text_digest": projection.text_digest,
                "extractor_ref": projection.extractor_ref,
                "language": projection.language,
                "instruction_trusted": projection.instruction_trusted,
            }
        ),
    }


@dataclass(frozen=True, slots=True)
class ContentFeatureReceipt:
    feature_id: str
    record_id: str
    record_digest: str
    asset_digest: str
    validation_digest: str
    decoded_digest: str
    modality: LearningModality
    algorithm_ref: str
    values: tuple[int, ...]
    measurements: Mapping[str, object]
    source_refs: tuple[str, ...]
    rights_refs: tuple[str, ...]
    lineage_refs: tuple[str, ...]
    simulated: bool
    original_source_binding: SourceAuthorityBinding | None = None
    time_span: tuple[float, float] | None = None
    instruction_trusted: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_id", _text("feature_id", self.feature_id, maximum=512))
        object.__setattr__(self, "record_id", _text("record_id", self.record_id, maximum=512))
        for name in ("record_digest", "asset_digest", "validation_digest", "decoded_digest"):
            object.__setattr__(self, name, _sha(name, getattr(self, name)))
        expected = {
            LearningModality.IMAGE: (_IMAGE_ALGORITHM, 90),
            LearningModality.AUDIO: (_AUDIO_ALGORITHM, 52),
        }
        if not isinstance(self.modality, LearningModality) or self.modality not in expected:
            raise MultimodalFoundationError("content features require image or PCM audio")
        algorithm, dimensions = expected[self.modality]
        if (
            self.algorithm_ref != algorithm
            or not isinstance(self.values, tuple)
            or len(self.values) != dimensions
            or any(
                isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 65535
                for value in self.values
            )
        ):
            raise MultimodalFoundationError("content feature algorithm/vector identity invalid")
        if not isinstance(self.measurements, Mapping) or len(self.measurements) > 16:
            raise MultimodalFoundationError("signal measurements must be bounded")
        measured = dict(self.measurements)
        if any(
            not isinstance(key, str) or isinstance(value, bool) or not isinstance(value, (int, float))
            for key, value in measured.items()
        ):
            raise MultimodalFoundationError("signal measurements must be numeric")
        _json(measured)
        object.__setattr__(self, "measurements", MappingProxyType(measured))
        object.__setattr__(self, "source_refs", _bounded_refs("source_ref", self.source_refs))
        object.__setattr__(self, "rights_refs", _bounded_refs("rights_ref", self.rights_refs))
        if not isinstance(self.lineage_refs, tuple) or len(self.lineage_refs) > 128:
            raise MultimodalFoundationError("signal lineage references must be bounded")
        object.__setattr__(
            self, "lineage_refs", tuple(_text("lineage_ref", value) for value in self.lineage_refs)
        )
        if not isinstance(self.simulated, bool) or self.instruction_trusted is not False:
            raise MultimodalFoundationError("content signals remain explicitly untrusted evidence")
        object.__setattr__(self, "time_span", _window(self.time_span))
        if self.original_source_binding is not None:
            from skeleton.ai.runtime.training.data import SourceAuthorityBinding

            if not isinstance(self.original_source_binding, SourceAuthorityBinding):
                raise MultimodalFoundationError("content signal original authority binding is invalid")
            binding = SourceAuthorityBinding(**self.original_source_binding.as_dict())
            if binding.content_digest != self.asset_digest or binding.purpose != "media_retrieval":
                raise MultimodalFoundationError(
                    "content signal original authority binding does not match source"
                )

    def as_dict(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "record_id": self.record_id,
            "record_digest": self.record_digest,
            "asset_digest": self.asset_digest,
            "validation_digest": self.validation_digest,
            "decoded_digest": self.decoded_digest,
            "modality": self.modality.value,
            "algorithm_ref": self.algorithm_ref,
            "values": list(self.values),
            "measurements": dict(self.measurements),
            "source_refs": list(self.source_refs),
            "rights_refs": list(self.rights_refs),
            "lineage_refs": list(self.lineage_refs),
            "simulated": self.simulated,
            "original_source_binding": (
                None if self.original_source_binding is None else self.original_source_binding.as_dict()
            ),
            "time_span": None if self.time_span is None else list(self.time_span),
            "instruction_trusted": self.instruction_trusted,
        }

    @property
    def digest(self) -> str:
        return _digest(self.as_dict())


@dataclass(frozen=True, slots=True)
class ContentSimilarityHit:
    query_feature_digest: str
    feature: ContentFeatureReceipt
    score: float
    distance: float
    instruction_trusted: bool = False

    def __post_init__(self) -> None:
        _sha("query_feature_digest", self.query_feature_digest)
        if self.instruction_trusted is not False or not isinstance(self.feature, ContentFeatureReceipt):
            raise MultimodalFoundationError("signal hit must retain untrusted typed evidence")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 1
            for value in (self.score, self.distance)
        ) or not math.isclose(self.score + self.distance, 1, abs_tol=1e-15):
            raise MultimodalFoundationError("signal similarity score is invalid")

    def as_scored_result(self) -> ScoredResult:
        return ScoredResult(
            self.feature.record_id,
            f"Verified {self.feature.modality.value} source {self.feature.asset_digest}",
            self.score,
            plane=f"media:{self.feature.modality.value}_signal",
            provenance=self.feature.digest,
            metadata={
                "content_feature": self.feature.as_dict(),
                "query_feature_digest": self.query_feature_digest,
                "distance": self.distance,
                "instruction_trusted": False,
            },
        )


def _image_values(
    payload: bytes, asset: VerifiedMultimodalAsset
) -> tuple[tuple[int, ...], dict[str, object]]:
    from PIL import Image

    with Image.open(io.BytesIO(payload)) as image, image.convert("RGBA") as rgba:
        decoded = rgba.tobytes()
        width, height = rgba.size
    if hashlib.sha256(decoded).hexdigest() != asset.validation.decoded_digest or (width, height) != (
        asset.validation.width,
        asset.validation.height,
    ):
        raise MultimodalFoundationError("signal decoder image output changed")
    pixels = np.frombuffer(decoded, dtype=np.uint8).reshape(height, width, 4)
    alpha = pixels[:, :, 3:4].astype(np.uint16)
    colors = (pixels[:, :, :3].astype(np.uint16) * alpha + 127) // 255
    channels = np.concatenate((colors, alpha), axis=2)
    values = []
    for y in range(4):
        y0, y1 = y * height // 4, max(y * height // 4 + 1, (y + 1) * height // 4)
        for x in range(4):
            x0, x1 = x * width // 4, max(x * width // 4 + 1, (x + 1) * width // 4)
            block = channels[y0:y1, x0:x1]
            values.extend(
                _ratio(int(value), block.shape[0] * block.shape[1] * 255) for value in block.sum(axis=(0, 1))
            )
    for channel in range(3):
        bins = np.bincount((colors[:, :, channel] // 32).ravel().astype(np.int64), minlength=8)
        values.extend(_ratio(int(value), width * height) for value in bins)
    luma = ((54 * colors[:, :, 0] + 183 * colors[:, :, 1] + 19 * colors[:, :, 2]) // 256).astype(np.int32)
    for axis in (1, 0):
        differences = np.abs(np.diff(luma, axis=axis))
        values.append(_ratio(int(differences.sum()), differences.size * 255))
    return tuple(values), {
        "source_bytes": len(payload),
        "width": width,
        "height": height,
        "channels": 4,
        "vector_dimensions": 90,
    }


def _audio_values(
    payload: bytes, asset: VerifiedMultimodalAsset
) -> tuple[tuple[int, ...], dict[str, object]]:
    with wave.open(io.BytesIO(payload), "rb") as audio:
        channels, rate, width, count = (
            audio.getnchannels(),
            audio.getframerate(),
            audio.getsampwidth(),
            audio.getnframes(),
        )
        decoded = audio.readframes(count + 1)
    validation = asset.validation
    if hashlib.sha256(decoded).hexdigest() != validation.decoded_digest or (channels, rate, width, count) != (
        validation.channels,
        validation.sample_rate_hz,
        validation.sample_width_bytes,
        validation.sample_count,
    ):
        raise MultimodalFoundationError("signal decoder PCM output changed")
    if width == 1:
        samples = (np.frombuffer(decoded, np.uint8).astype(np.float64) - 128) / 128
    elif width == 3:
        raw = np.frombuffer(decoded, np.uint8).reshape(-1, 3).astype(np.int32)
        signed = raw[:, 0] | (raw[:, 1] << 8) | (raw[:, 2] << 16)
        samples = ((signed ^ 8388608) - 8388608).astype(np.float64) / 8388608
    else:
        samples = np.frombuffer(decoded, dtype="<i2" if width == 2 else "<i4").astype(np.float64) / (
            2 ** (8 * width - 1)
        )
    mono = samples.reshape(count, channels).mean(axis=1)
    values = []
    for cell in range(8):
        start, end = cell * count // 8, max(cell * count // 8 + 1, (cell + 1) * count // 8)
        block = mono[start:end]
        crossings = np.count_nonzero(np.diff(np.signbit(block))) / max(1, len(block) - 1)
        values.extend(
            (
                _q(float(np.sqrt(np.mean(block * block)))),
                _q(float(np.mean(np.abs(block)))),
                _q(float(np.mean(block) + 1) / 2),
                _q(float(crossings)),
            )
        )
    n = min(2048, count)
    starts = sorted({index * (count - n) // 7 for index in range(8)})
    power = np.zeros(n // 2 + 1, dtype=np.float64)
    taper = np.hanning(n)
    for start in starts:
        block = mono[start : start + n]
        spectrum = np.fft.rfft((block - block.mean()) * taper)
        power += np.abs(spectrum) ** 2
    frequencies = np.fft.rfftfreq(n, 1 / rate)
    total = float(power.sum())
    for index, (low, high) in enumerate(pairwise(_BANDS)):
        mask = (frequencies >= low) & (frequencies <= high if index == 15 else frequencies < high)
        values.append(_q(0 if total == 0 else math.sqrt(float(power[mask].sum()) / total)))
    centroid = 0 if total == 0 else float(np.sum(frequencies * power) / total)
    bandwidth = 0 if total == 0 else float(np.sqrt(np.sum((frequencies - centroid) ** 2 * power) / total))
    flatness = 0 if total == 0 else float(np.exp(np.log(np.maximum(power, 1e-30)).mean()) / power.mean())
    values.extend(
        (_q(centroid / 96000), _q(bandwidth / 96000), _q(flatness), _q(float(np.max(np.abs(mono)))))
    )
    return tuple(values), {
        "source_bytes": len(payload),
        "sample_rate_hz": rate,
        "sample_count": count,
        "channels": channels,
        "sample_width_bytes": width,
        "duration_seconds": count / rate,
        "vector_dimensions": 52,
        "fft_window_samples": n,
        "fft_windows": len(starts),
    }


class ContentSignalIndex:
    """Bounded exact signal evidence and existing governed snapshot authority."""

    def __init__(
        self,
        corpus: MultimodalCorpus,
        *,
        index_id: str = "media-signals",
        rights_policy: Mapping[str, Sequence[str]],
        registry: DatasetRegistry | None = None,
        dataset_id: str | None = None,
        limits: Mapping[str, int] | None = None,
        acquired_at: datetime | None = None,
    ) -> None:
        if not isinstance(corpus, MultimodalCorpus):
            raise MultimodalFoundationError("content signals require the canonical corpus")
        self.corpus = corpus
        self._index_id = _text("index_id", index_id, maximum=128)
        if not isinstance(rights_policy, Mapping) or not 1 <= len(rights_policy) <= 128:
            raise MultimodalFoundationError("content retrieval requires explicit bounded source rights")
        self._rights_policy = {
            _text("rights_ref", ref): _bounded_refs("permitted_use", uses)
            for ref, uses in rights_policy.items()
        }
        if limits is not None and (not isinstance(limits, Mapping) or set(limits) - set(_CEILINGS)):
            raise MultimodalFoundationError("content signal resource limits are unknown")
        self._limits = {
            name: _integer(name, (limits or {}).get(name, ceiling), ceiling)
            for name, ceiling in _CEILINGS.items()
        }
        self._registry = registry
        self._dataset_id = _text("dataset_id", dataset_id or "media-signal-index:" + self._index_id)
        if registry is not None:
            from skeleton.ai.runtime.training.data import DatasetRegistry

            if (
                not isinstance(registry, DatasetRegistry)
                or registry.latest_materialized_version(self._dataset_id) != 0
            ):
                raise MultimodalFoundationError("existing canonical signal index must be restored")
        elif dataset_id is not None:
            raise MultimodalFoundationError("dataset identity requires a governed registry")
        when = acquired_at or datetime.now(UTC)
        if not isinstance(when, datetime) or when.tzinfo is None or when.utcoffset() is None:
            raise MultimodalFoundationError("signal acquisition time must be timezone aware")
        self._acquired_at = when.astimezone(UTC)
        self._features: dict[str, ContentFeatureReceipt] = {}
        self._record_features: dict[str, str] = {}
        self._pins: dict[str, str] = {}
        self._copies: dict[str, SourceAuthorityBinding] = {}
        self._checkpoint_refs: dict[str, tuple[int, str]] = {}
        self._version = 0
        self._checkpoint: MaterializedDatasetReceipt | None = None
        self._checkpoint_digest: str | None = None
        self._integrity = _digest(self._state())

    @property
    def features(self) -> tuple[ContentFeatureReceipt, ...]:
        return tuple(self._features[key] for key in sorted(self._features))

    @property
    def latest_checkpoint(self) -> MaterializedDatasetReceipt | None:
        return self._checkpoint

    def _content(self) -> dict[str, object]:
        return {
            "index_id": self._index_id,
            "dataset_id": self._dataset_id,
            "limits": dict(self._limits),
            "rights_policy": {key: list(value) for key, value in self._rights_policy.items()},
            "acquired_at": self._acquired_at.isoformat(),
            "features": [feature.as_dict() for feature in self.features],
        }

    def _state(self) -> dict[str, object]:
        return {
            "content": self._content(),
            "record_features": dict(self._record_features),
            "pins": dict(self._pins),
            "copies": {key: value.as_dict() for key, value in self._copies.items()},
            "checkpoint_refs": dict(self._checkpoint_refs),
            "version": self._version,
        }

    def _verify_state(self) -> None:
        if self._integrity != _digest(self._state()) or any(
            self._pins.get(feature.feature_id) != feature.digest for feature in self.features
        ):
            raise MultimodalFoundationError("issued content signal index evidence drift")
        if self._registry is not None:
            if self._registry.latest_materialized_version(self._dataset_id) != self._version:
                raise MultimodalFoundationError("stale content signal snapshot version")
            if self._checkpoint is not None and self._checkpoint.digest != self._checkpoint_digest:
                raise MultimodalFoundationError("issued content signal checkpoint identity drift")

    def _allowed(self, receipt: ContentFeatureReceipt) -> bool:
        return all("media_retrieval" in self._rights_policy.get(ref, ()) for ref in receipt.rights_refs)

    def _preflight(self, record_id: str) -> None:
        record = self.corpus._records.get(record_id)
        if record is None:
            raise MultimodalFoundationError("content signal source record is missing")
        asset = self.corpus.intake._assets.get(record_id)
        payload = self.corpus.store._objects.get(record.asset_digest)
        if not isinstance(asset, VerifiedMultimodalAsset) or record.modality not in {
            LearningModality.IMAGE,
            LearningModality.AUDIO,
        }:
            raise MultimodalFoundationError("content features require verified image/PCM source bytes")
        if not isinstance(payload, bytes) or len(payload) > self._limits["max_source_bytes"]:
            raise MultimodalFoundationError("content source byte limit exceeded")
        if len(record.source_refs) > 128 or len(record.rights_refs) > 128 or len(record.lineage_refs) > 128:
            raise MultimodalFoundationError("content source provenance reference bound exceeded")
        projection = self.corpus._text.get(record_id)
        if projection is not None and (
            not isinstance(projection, str) or len(projection.encode("utf-8")) > 16384
        ):
            raise MultimodalFoundationError("preserved projection byte limit exceeded")
        validation = asset.validation
        if record.modality is LearningModality.IMAGE:
            if (
                validation.width is None
                or validation.height is None
                or validation.width * validation.height > self._limits["max_image_pixels"]
            ):
                raise MultimodalFoundationError("content image pixel limit exceeded")
        elif (
            validation.sample_count is None
            or validation.sample_count > self._limits["max_audio_sample_frames"]
            or validation.duration_seconds > self._limits["max_audio_seconds"]
        ):
            raise MultimodalFoundationError("content PCM sample/duration limit exceeded")

    def _derive(
        self,
        record_id: str,
        feature_id: str,
        time_span: tuple[float, float] | None,
        binding: SourceAuthorityBinding | None,
    ) -> ContentFeatureReceipt:
        self._preflight(record_id)
        record = self.corpus.get(record_id)
        asset = self.corpus.intake._assets[record_id]
        assert isinstance(asset, VerifiedMultimodalAsset)
        payload = self.corpus.store.get(record.asset_digest)
        try:
            values, measured = (
                _image_values(payload, asset)
                if record.modality is LearningModality.IMAGE
                else _audio_values(payload, asset)
            )
        except (OSError, ValueError, EOFError, wave.Error) as exc:
            raise MultimodalFoundationError("actual content signal decoding failed") from exc
        if time_span is not None and (
            record.modality is LearningModality.IMAGE
            and time_span[0] != time_span[1]
            or record.modality is LearningModality.AUDIO
            and not math.isclose(
                time_span[1] - time_span[0], asset.validation.duration_seconds, rel_tol=0, abs_tol=1e-9
            )
        ):
            raise MultimodalFoundationError("content time span disagrees with measured source")
        return ContentFeatureReceipt(
            feature_id,
            record_id,
            record.digest,
            record.asset_digest,
            asset.validation.digest,
            asset.validation.decoded_digest,
            record.modality,
            _IMAGE_ALGORITHM if record.modality is LearningModality.IMAGE else _AUDIO_ALGORITHM,
            values,
            measured,
            record.source_refs,
            record.rights_refs,
            record.lineage_refs,
            record.simulated,
            binding,
            time_span,
        )

    def _bind_original(self, receipt: ContentFeatureReceipt) -> SourceAuthorityBinding | None:
        if self._registry is None:
            return None
        from skeleton.ai.runtime.training.data import IngestEnvelope

        prior = self._registry.source_envelope(receipt.asset_digest)
        if prior is None:
            envelope = IngestEnvelope.from_bytes(
                source_id="media-signal-source:" + receipt.record_digest,
                payload=self.corpus.store.get(receipt.asset_digest),
                parser_version="media-signal-source@1",
                classification="internal",
                rights=("media_retrieval",),
                trusted=True,
                acquired_at=self._acquired_at,
            )
            self._registry.register_ingest(envelope)
        elif (
            prior.source_id != "media-signal-source:" + receipt.record_digest
            or prior.parser_version != "media-signal-source@1"
            or prior.rights != ("media_retrieval",)
            or prior.classification != "internal"
        ):
            raise PermissionError("registered original source cannot acquire content retrieval privileges")
        return self._registry.source_binding(receipt.asset_digest, purpose="media_retrieval")

    def add(
        self, record_id: str, *, feature_id: str | None = None, time_span: tuple[float, float] | None = None
    ) -> ContentFeatureReceipt:
        rid = _text("record_id", record_id, maximum=512)
        fid = _text(
            "feature_id", feature_id or "signal:" + hashlib.sha256(rid.encode()).hexdigest(), maximum=512
        )
        offsets = _window(time_span)
        with self.corpus._lock:
            self._verify_state()
            prior = self._features.get(fid)
            if (
                prior is not None
                and prior.record_id != rid
                or rid in self._record_features
                and self._record_features[rid] != fid
            ):
                raise MultimodalFoundationError("content feature identity conflict")
            if prior is None and len(self._features) >= self._limits["max_records"]:
                raise MultimodalFoundationError("content feature record bound exceeded")
            self._preflight(rid)
            raw_record = self.corpus._records[rid]
            total = sum(
                int(feature.measurements["source_bytes"])
                for feature in self.features
                if feature.record_id != rid
            )
            if (
                total + len(self.corpus.store._objects[raw_record.asset_digest])
                > self._limits["max_total_source_bytes"]
            ):
                raise MultimodalFoundationError("content aggregate source byte limit exceeded")
            candidate = self._derive(rid, fid, offsets, None)
            if not self._allowed(candidate):
                raise MultimodalFoundationError("every source right must permit media retrieval")
            if any(
                feature.record_id != rid and feature.asset_digest == candidate.asset_digest
                for feature in self.features
            ):
                raise MultimodalFoundationError("duplicate original asset in content signal index")
            candidate = replace(candidate, original_source_binding=self._bind_original(candidate))
            guard = (
                nullcontext()
                if self._registry is None
                else self._registry.source_authority((candidate.original_source_binding,))
            )
            original_state = (
                dict(self._features),
                dict(self._pins),
                dict(self._record_features),
                self._integrity,
            )
            try:
                with guard:
                    self._verify_state()
                    if prior is not None:
                        if candidate != prior:
                            raise MultimodalFoundationError("issued content feature identity conflict")
                        return prior
                    self._features[fid] = candidate
                    self._pins[fid] = candidate.digest
                    self._record_features[rid] = fid
                    self._integrity = _digest(self._state())
                    return candidate
            except BaseException:
                self._features, self._pins, self._record_features, self._integrity = original_state
                raise

    def _verify_feature(self, feature: ContentFeatureReceipt) -> None:
        if self._pins.get(feature.feature_id) != feature.digest or replace(feature) != feature:
            raise MultimodalFoundationError("issued content feature receipt drift")
        if (
            self._derive(
                feature.record_id, feature.feature_id, feature.time_span, feature.original_source_binding
            )
            != feature
        ):
            raise MultimodalFoundationError("measured content feature/source identity drift")
        copied = self._copies.get(feature.feature_id)
        if copied is not None:
            source = self._registry.materialized_source(copied.content_digest, purpose="media_retrieval")
            if (
                source.evidence.get("content_feature_digest") != feature.digest
                or source.evidence.get("original_source_binding") != feature.original_source_binding.as_dict()
            ):
                raise MultimodalFoundationError("copied content feature provenance drift")

    def search(
        self,
        query_record_id: str,
        *,
        record_ids: Sequence[str],
        allowed_rights_refs: Sequence[str],
        include_simulated: bool = False,
        window_seconds: tuple[float, float] | None = None,
        exclude_record_ids: Sequence[str] = (),
        limit: int = 10,
    ) -> tuple[ContentSimilarityHit, ...]:
        rid = _text("query_record_id", query_record_id, maximum=512)
        if (
            isinstance(record_ids, (str, bytes))
            or not isinstance(record_ids, Sequence)
            or not 1 <= len(record_ids) <= self._limits["max_records"]
        ):
            raise MultimodalFoundationError("signal candidates require bounded ordered record IDs")
        selected = tuple(_text("record_id", value, maximum=512) for value in record_ids)
        if len(set(selected)) != len(selected):
            raise MultimodalFoundationError("duplicate content signal candidate record")
        if (
            isinstance(exclude_record_ids, (str, bytes))
            or not isinstance(exclude_record_ids, Sequence)
            or len(exclude_record_ids) > 256
        ):
            raise MultimodalFoundationError("source exclusions require bounded ordered IDs")
        excluded = {_text("excluded_record_id", value, maximum=512) for value in exclude_record_ids}
        allowed = set(_bounded_refs("allowed_rights_ref", allowed_rights_refs))
        if not isinstance(include_simulated, bool):
            raise MultimodalFoundationError("include_simulated must be boolean")
        count = _integer("limit", limit, 256)
        window = _window(window_seconds)
        if window is not None and window[0] == window[1]:
            raise MultimodalFoundationError("signal query window is empty")
        with self.corpus._lock:
            self._verify_state()
            try:
                query = self._features[self._record_features[rid]]
                candidates = [self._features[self._record_features[item]] for item in selected]
            except KeyError as exc:
                raise MultimodalFoundationError("content signal record is not indexed") from exc
            if (
                not self._allowed(query)
                or not set(query.rights_refs).issubset(allowed)
                or query.simulated
                and not include_simulated
            ):
                raise MultimodalFoundationError(
                    "query source is outside declared retrieval rights/simulation scope"
                )
            eligible = []
            for feature in candidates:
                if (
                    feature.record_id == rid
                    or feature.asset_digest == query.asset_digest
                    or feature.record_id in excluded
                    or feature.modality is not query.modality
                    or feature.simulated != query.simulated
                    or not set(feature.rights_refs).issubset(allowed)
                    or not self._allowed(feature)
                ):
                    continue
                if window is not None:
                    span = feature.time_span
                    if span is None or not (
                        window[0] <= span[0] < window[1]
                        if feature.modality is LearningModality.IMAGE
                        else span[0] < window[1] and span[1] > window[0]
                    ):
                        continue
                eligible.append(feature)
            selected_features = (query, *eligible)
            for feature in selected_features:
                self._preflight(feature.record_id)
            if (
                sum(len(self.corpus.store._objects[feature.asset_digest]) for feature in selected_features)
                > self._limits["max_total_source_bytes"]
            ):
                raise MultimodalFoundationError("signal verification source byte budget exceeded")
            bindings = []
            if self._registry is not None:
                bindings.extend(feature.original_source_binding for feature in selected_features)
                bindings.extend(
                    self._copies[feature.feature_id]
                    for feature in selected_features
                    if feature.feature_id in self._copies
                )
            guard = (
                nullcontext()
                if not bindings
                else self._registry.source_authority(tuple(dict.fromkeys(bindings)))
            )
            with guard:
                self._verify_state()
                self._verify_feature(query)
                hits = []
                for feature in eligible:
                    self._verify_feature(feature)
                    distance = sum(
                        abs(left - right) for left, right in zip(query.values, feature.values, strict=True)
                    ) / (len(query.values) * 65535)
                    hits.append(ContentSimilarityHit(query.digest, feature, 1 - distance, distance))
                return tuple(sorted(hits, key=lambda hit: (-hit.score, hit.feature.record_id))[:count])

    def _copy_document(self, feature: ContentFeatureReceipt) -> dict[str, object]:
        record = self.corpus.get(feature.record_id)
        asset = self.corpus.intake._assets[feature.record_id]
        return {
            "schema_version": _SCHEMA,
            "kind": "media",
            "feature": feature.as_dict(),
            "record": _record_data(record),
            "validation": asset.validation.as_dict(),
            "projection_text": self.corpus._text.get(feature.record_id),
            "payload_base64": base64.b64encode(self.corpus.store.get(feature.asset_digest)).decode("ascii"),
        }

    def _source(
        self,
        document: dict[str, object],
        rights: tuple[str, ...],
        lineage: tuple[str, ...],
        evidence: dict[str, object],
    ):
        from skeleton.ai.runtime.training.data import (
            IngestEnvelope,
            MaterializedTrainingSource,
        )

        text = _json(document)
        if len(text.encode("utf-8")) > 1048576:
            raise MultimodalFoundationError("signal snapshot document exceeds byte ceiling")
        payload = _json([text]).encode("utf-8")
        envelope = IngestEnvelope.from_bytes(
            source_id="media-signal-copy:" + hashlib.sha256(payload).hexdigest(),
            payload=payload,
            parser_version="media-signal-index@1",
            classification="internal",
            rights=("media_retrieval",),
            trusted=True,
            acquired_at=self._acquired_at,
        )
        return MaterializedTrainingSource(envelope, payload, "json_documents", rights, lineage, evidence)

    def checkpoint(self, *, checkpoint_id: str) -> MaterializedDatasetReceipt:
        from skeleton.ai.runtime.training.data import SourceAuthorityBinding

        if self._registry is None:
            raise MultimodalFoundationError("signal checkpoints require the canonical governed registry")
        cid = _text("checkpoint_id", checkpoint_id, maximum=128)
        with self.corpus._lock:
            self._verify_state()
            if not self.features:
                raise MultimodalFoundationError("cannot persist an empty content signal index")
            content_digest = _digest(self._content())
            prior = self._checkpoint_refs.get(cid)
            if prior is not None:
                if prior[1] != content_digest:
                    raise MultimodalFoundationError("signal checkpoint identity conflict")
                bindings = tuple(
                    dict.fromkeys(
                        (
                            *(feature.original_source_binding for feature in self.features),
                            *self._copies.values(),
                        )
                    )
                )
                with self._registry.source_authority(bindings):
                    self._verify_state()
                    receipt = self._registry.materialized_ingestion(cid)
                    if (
                        receipt is None
                        or receipt.manifest.dataset_id != self._dataset_id
                        or receipt.manifest.version != str(prior[0])
                    ):
                        raise MultimodalFoundationError("issued signal checkpoint replay identity drift")
                    return receipt
            if len(self._checkpoint_refs) >= 128:
                raise MultimodalFoundationError("signal checkpoint count bound exceeded")
            originals = tuple(feature.original_source_binding for feature in self.features)
            with self._registry.source_authority(originals):
                for feature in self.features:
                    self._verify_feature(feature)
                refs = {**self._checkpoint_refs, cid: (self._version + 1, content_digest)}
                metadata = {
                    "schema_version": _SCHEMA,
                    "kind": "index",
                    "index_id": self._index_id,
                    "dataset_id": self._dataset_id,
                    "limits": dict(self._limits),
                    "rights_policy": {key: list(value) for key, value in self._rights_policy.items()},
                    "acquired_at": self._acquired_at.isoformat(),
                    "version": self._version + 1,
                    "checkpoint_id": cid,
                    "checkpoint_refs": {key: list(value) for key, value in refs.items()},
                    "content_digest": content_digest,
                    "features": [
                        {"feature_id": feature.feature_id, "digest": feature.digest}
                        for feature in self.features
                    ],
                }
                rights = tuple(dict.fromkeys(ref for feature in self.features for ref in feature.rights_refs))
                sources = [
                    self._source(
                        metadata,
                        rights,
                        tuple(feature.digest for feature in self.features),
                        {"content_index_id": self._index_id, "content_digest": content_digest},
                    )
                ]
                sources.extend(
                    self._source(
                        self._copy_document(feature),
                        feature.rights_refs,
                        tuple(
                            dict.fromkeys(
                                (
                                    *feature.lineage_refs,
                                    feature.record_digest,
                                    feature.asset_digest,
                                    feature.validation_digest,
                                    feature.digest,
                                )
                            )
                        ),
                        {
                            "content_feature_digest": feature.digest,
                            "original_source_binding": feature.original_source_binding.as_dict(),
                        },
                    )
                    for feature in self.features
                )
                copy_bindings = {}
                for feature, source in zip(self.features, sources[1:], strict=True):
                    digest = source.envelope.content_digest
                    if self._registry.source_envelope(digest) is None:
                        binding = SourceAuthorityBinding(
                            digest, _digest(source.envelope.as_dict()), 0, "media_retrieval"
                        )
                    else:
                        binding = self._registry.source_binding(digest, purpose="media_retrieval")
                    if binding.envelope_digest != _digest(source.envelope.as_dict()):
                        raise MultimodalFoundationError("signal copied-source envelope identity conflict")
                    copy_bindings[feature.feature_id] = binding
            receipt = self._registry.ingest_materialized(
                ingestion_id=cid,
                dataset_id=self._dataset_id,
                expected_version=self._version,
                sources={"signals": tuple(sources)},
                classification="internal",
                permitted_uses=("media_retrieval",),
                retention_class="bounded-media-retrieval",
                original_source_bindings=originals,
            )
            self._version += 1
            self._checkpoint_refs[cid] = self._version, content_digest
            self._checkpoint, self._checkpoint_digest = receipt, receipt.digest
            self._copies = copy_bindings
            self._integrity = _digest(self._state())
            return receipt

    @classmethod
    def restore(
        cls, corpus: MultimodalCorpus, registry: DatasetRegistry, dataset_digest: str
    ) -> ContentSignalIndex:
        try:
            return cls._restore(corpus, registry, dataset_digest)
        except (ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
            raise MultimodalFoundationError("content signal recovery evidence invalid") from exc

    @classmethod
    def _restore(
        cls, corpus: MultimodalCorpus, registry: DatasetRegistry, dataset_digest: str
    ) -> ContentSignalIndex:
        from skeleton.ai.runtime.training.data import SourceAuthorityBinding

        digest = _sha("dataset_digest", dataset_digest)
        manifest = registry.dataset(digest)
        if manifest.permitted_uses != ("media_retrieval",) or tuple(
            split.name for split in manifest.splits
        ) != ("signals",):
            raise MultimodalFoundationError("dataset is not an isolated content signal snapshot")
        sources = registry.materialized_sources(digest)
        if not 2 <= len(sources) <= 257:
            raise MultimodalFoundationError("signal snapshot source coverage exceeds bounds")
        documents = []
        for source in sources:
            if (
                source.envelope.rights != ("media_retrieval",)
                or source.envelope.parser_version != "media-signal-index@1"
            ):
                raise MultimodalFoundationError("signal snapshot source purpose/parser mismatch")
            docs = source.documents()
            if len(docs) != 1 or len(docs[0].encode("utf-8")) > 1048576:
                raise MultimodalFoundationError("signal snapshot document bound exceeded")
            document = json.loads(docs[0])
            if (
                not isinstance(document, dict)
                or _json(document) != docs[0]
                or document.get("schema_version") != _SCHEMA
            ):
                raise MultimodalFoundationError("signal snapshot document identity invalid")
            documents.append(document)
        metadata = documents[0]
        version = _integer("version", metadata.get("version"), 128)
        if (
            metadata.get("kind") != "index"
            or metadata.get("dataset_id") != manifest.dataset_id
            or manifest.version != str(version)
            or registry.latest_materialized_version(manifest.dataset_id) != version
        ):
            raise MultimodalFoundationError("stale or invalid signal snapshot version")
        reconstructed = []
        for document in documents[1:]:
            if document.get("kind") != "media":
                raise MultimodalFoundationError("signal snapshot media document missing")
            value = document["feature"]
            binding = SourceAuthorityBinding(**value["original_source_binding"])
            feature = ContentFeatureReceipt(
                **{
                    **value,
                    "modality": LearningModality(value["modality"]),
                    "values": tuple(value["values"]),
                    "source_refs": tuple(value["source_refs"]),
                    "rights_refs": tuple(value["rights_refs"]),
                    "lineage_refs": tuple(value["lineage_refs"]),
                    "original_source_binding": binding,
                    "time_span": None if value["time_span"] is None else tuple(value["time_span"]),
                }
            )
            reconstructed.append(feature)
        if metadata["features"] != [
            {"feature_id": feature.feature_id, "digest": feature.digest} for feature in reconstructed
        ]:
            raise MultimodalFoundationError("signal snapshot feature receipt identity drift")
        originals = tuple(feature.original_source_binding for feature in reconstructed)
        copies = tuple(
            registry.source_binding(source.envelope.content_digest, purpose="media_retrieval")
            for source in sources
        )
        with corpus._lock:
            original_corpus = _clone_corpus(corpus)
            staged = _clone_corpus(corpus)
            recovered = cls(
                staged,
                index_id=metadata["index_id"],
                rights_policy=metadata["rights_policy"],
                limits=metadata["limits"],
                acquired_at=datetime.fromisoformat(metadata["acquired_at"]),
            )
            recovered._dataset_id = metadata["dataset_id"]
            try:
                with registry.source_authority((*originals, *copies)):
                    for feature, document, source in zip(
                        reconstructed, documents[1:], sources[1:], strict=True
                    ):
                        encoded = document["payload_base64"]
                        if not isinstance(encoded, str) or len(encoded) > 4 * math.ceil(
                            recovered._limits["max_source_bytes"] / 3
                        ):
                            raise MultimodalFoundationError("signal snapshot original byte bound exceeded")
                        payload = base64.b64decode(encoded, validate=True)
                        record = document["record"]
                        projection = record["text_projection"]
                        issued = staged.ingest(
                            record_id=record["record_id"],
                            modality=LearningModality(record["modality"]),
                            media_type=record["media_type"],
                            payload=payload,
                            source_refs=record["source_refs"],
                            rights_refs=record["rights_refs"],
                            lineage_refs=record["lineage_refs"],
                            metadata=record["metadata"],
                            extracted_text=document["projection_text"],
                            extractor_ref=None if projection is None else projection["extractor_ref"],
                            language="und" if projection is None else projection["language"],
                            simulated=record["simulated"],
                            verified=True,
                        )
                        if (
                            _record_data(issued) != record
                            or issued.digest != feature.record_digest
                            or staged.intake._assets[issued.record_id].validation.as_dict()
                            != document["validation"]
                        ):
                            raise MultimodalFoundationError(
                                "signal snapshot original record/decoder identity drift"
                            )
                        candidate = recovered._derive(
                            feature.record_id,
                            feature.feature_id,
                            feature.time_span,
                            feature.original_source_binding,
                        )
                        if (
                            candidate != feature
                            or not recovered._allowed(feature)
                            or feature.feature_id in recovered._features
                            or feature.record_id in recovered._record_features
                            or any(prior.asset_digest == feature.asset_digest for prior in recovered.features)
                        ):
                            raise MultimodalFoundationError(
                                "signal snapshot recomputed feature/provenance identity drift"
                            )
                        if (
                            source.as_dict()
                            != recovered._source(
                                recovered._copy_document(feature),
                                feature.rights_refs,
                                tuple(
                                    dict.fromkeys(
                                        (
                                            *feature.lineage_refs,
                                            feature.record_digest,
                                            feature.asset_digest,
                                            feature.validation_digest,
                                            feature.digest,
                                        )
                                    )
                                ),
                                {
                                    "content_feature_digest": feature.digest,
                                    "original_source_binding": feature.original_source_binding.as_dict(),
                                },
                            ).as_dict()
                        ):
                            raise MultimodalFoundationError(
                                "signal snapshot copy source/rights identity drift"
                            )
                        recovered._features[feature.feature_id], recovered._pins[feature.feature_id] = (
                            feature,
                            feature.digest,
                        )
                        recovered._record_features[feature.record_id] = feature.feature_id
                    if (
                        len(recovered.features) > recovered._limits["max_records"]
                        or sum(int(feature.measurements["source_bytes"]) for feature in recovered.features)
                        > recovered._limits["max_total_source_bytes"]
                        or _digest(recovered._content()) != metadata["content_digest"]
                    ):
                        raise MultimodalFoundationError("signal snapshot content identity/bounds drift")
                    refs = metadata["checkpoint_refs"]
                    if not isinstance(refs, dict) or len(refs) != version or len(refs) > 128:
                        raise MultimodalFoundationError("signal checkpoint replay coverage invalid")
                    parsed = {
                        key: (_integer("checkpoint_version", value[0], 128), _sha("content_digest", value[1]))
                        for key, value in refs.items()
                        if isinstance(value, list) and len(value) == 2
                    }
                    if (
                        len(parsed) != len(refs)
                        or sorted(value[0] for value in parsed.values()) != list(range(1, version + 1))
                        or parsed.get(metadata["checkpoint_id"]) != (version, metadata["content_digest"])
                    ):
                        raise MultimodalFoundationError("signal checkpoint receipt versions invalid")
                    recovered._version, recovered._checkpoint_refs = version, parsed
                    recovered._registry = registry
                    recovered._copies = {
                        feature.feature_id: binding
                        for feature, binding in zip(recovered.features, copies[1:], strict=True)
                    }
                    recovered._checkpoint = registry.materialized_ingestion(metadata["checkpoint_id"])
                    if recovered._checkpoint is None or recovered._checkpoint.dataset_digest != digest:
                        raise MultimodalFoundationError("signal issued native checkpoint identity mismatch")
                    recovered._checkpoint_digest = recovered._checkpoint.digest
                    recovered._integrity = _digest(recovered._state())
                    recovered._verify_state()
                    _publish_corpus(staged, corpus)
            except BaseException:
                _publish_corpus(original_corpus, corpus)
                raise
            recovered.corpus = corpus
            return recovered
