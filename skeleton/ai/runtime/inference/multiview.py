"""Bounded 360-degree camera-view planning for multimodal learning.

This module produces *view identities and augmentation instructions*.  It never
pretends to synthesize pixels.  A vision renderer/extractor can materialize the
views later while preserving the exact training identity generated here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Sequence


_MAX_VIEWS = 4_096


class CameraViewError(RuntimeError):
    """A camera augmentation plan is invalid or exceeds hard bounds."""


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
        raise CameraViewError(
            "camera view identity is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _finite(
    value: object,
    field: str,
    minimum: float,
    maximum: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CameraViewError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise CameraViewError(
            f"{field} must be in [{minimum}, {maximum}]"
        )
    if result == 0.0:
        result = 0.0
    return result


@dataclass(frozen=True, slots=True)
class CameraView:
    """One spherical camera pose + optical augmentation."""

    azimuth_deg: float
    elevation_deg: float
    roll_deg: float
    fov_deg: float
    distance_scale: float = 1.0
    exposure_ev: float = 0.0

    def __post_init__(self) -> None:
        azimuth = _finite(
            self.azimuth_deg,
            "azimuth_deg",
            -360.0,
            360.0,
        ) % 360.0
        elevation = _finite(
            self.elevation_deg,
            "elevation_deg",
            -90.0,
            90.0,
        )
        roll = _finite(
            self.roll_deg,
            "roll_deg",
            -360.0,
            360.0,
        ) % 360.0
        fov = _finite(self.fov_deg, "fov_deg", 1.0, 179.0)
        distance = _finite(
            self.distance_scale,
            "distance_scale",
            0.05,
            100.0,
        )
        exposure = _finite(
            self.exposure_ev,
            "exposure_ev",
            -8.0,
            8.0,
        )
        # At the poles, azimuth is geometrically degenerate.  Canonicalize it
        # so equivalent top/bottom views do not silently multiply.
        if abs(elevation) == 90.0:
            azimuth = 0.0
        object.__setattr__(self, "azimuth_deg", azimuth)
        object.__setattr__(self, "elevation_deg", elevation)
        object.__setattr__(self, "roll_deg", roll)
        object.__setattr__(self, "fov_deg", fov)
        object.__setattr__(self, "distance_scale", distance)
        object.__setattr__(self, "exposure_ev", exposure)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "azimuth_deg": self.azimuth_deg,
                "elevation_deg": self.elevation_deg,
                "roll_deg": self.roll_deg,
                "fov_deg": self.fov_deg,
                "distance_scale": self.distance_scale,
                "exposure_ev": self.exposure_ev,
            }
        )

    @property
    def reference(self) -> str:
        return "camera-view-sha256:" + self.digest

    @property
    def semantic_angle(self) -> str:
        if self.elevation_deg == 90.0:
            return "top"
        if self.elevation_deg == -90.0:
            return "bottom"
        directions = (
            "front",
            "front-right",
            "right",
            "back-right",
            "back",
            "back-left",
            "left",
            "front-left",
        )
        index = int(
            round(self.azimuth_deg / 45.0)
        ) % len(directions)
        vertical = (
            "high"
            if self.elevation_deg > 15.0
            else "low"
            if self.elevation_deg < -15.0
            else "level"
        )
        return vertical + ":" + directions[index]

    def as_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "azimuth_deg": self.azimuth_deg,
            "elevation_deg": self.elevation_deg,
            "roll_deg": self.roll_deg,
            "fov_deg": self.fov_deg,
            "distance_scale": self.distance_scale,
            "exposure_ev": self.exposure_ev,
            "semantic_angle": self.semantic_angle,
        }


@dataclass(frozen=True, slots=True)
class CameraCoveragePolicy:
    """Regular spherical lattice with bounded optical variants."""

    azimuth_step_deg: int = 45
    elevation_step_deg: int = 30
    roll_step_deg: int = 90
    fov_degrees: tuple[float, ...] = (35.0, 55.0, 85.0)
    distance_scales: tuple[float, ...] = (1.0,)
    exposure_evs: tuple[float, ...] = (0.0,)
    include_poles: bool = True
    max_views: int = 2_048

    def __post_init__(self) -> None:
        for name, value, maximum in (
            ("azimuth_step_deg", self.azimuth_step_deg, 180),
            ("elevation_step_deg", self.elevation_step_deg, 90),
            ("roll_step_deg", self.roll_step_deg, 180),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
                or value > maximum
            ):
                raise CameraViewError(
                    f"{name} must be in [1, {maximum}]"
                )
        if 360 % self.azimuth_step_deg:
            raise CameraViewError(
                "azimuth_step_deg must divide 360 exactly"
            )
        if 180 % self.elevation_step_deg:
            raise CameraViewError(
                "elevation_step_deg must divide 180 exactly"
            )
        if 360 % self.roll_step_deg:
            raise CameraViewError(
                "roll_step_deg must divide 360 exactly"
            )
        if (
            isinstance(self.max_views, bool)
            or not isinstance(self.max_views, int)
            or not 1 <= self.max_views <= _MAX_VIEWS
        ):
            raise CameraViewError(
                f"max_views must be in [1, {_MAX_VIEWS}]"
            )
        fovs = tuple(
            _finite(value, "fov_degrees", 1.0, 179.0)
            for value in self.fov_degrees
        )
        distances = tuple(
            _finite(value, "distance_scales", 0.05, 100.0)
            for value in self.distance_scales
        )
        exposures = tuple(
            _finite(value, "exposure_evs", -8.0, 8.0)
            for value in self.exposure_evs
        )
        if not fovs or not distances or not exposures:
            raise CameraViewError(
                "camera optical variant lists must be non-empty"
            )
        if len(fovs) != len(set(fovs)):
            raise CameraViewError("fov_degrees must be unique")
        if len(distances) != len(set(distances)):
            raise CameraViewError("distance_scales must be unique")
        if len(exposures) != len(set(exposures)):
            raise CameraViewError("exposure_evs must be unique")
        object.__setattr__(self, "fov_degrees", tuple(sorted(fovs)))
        object.__setattr__(
            self,
            "distance_scales",
            tuple(sorted(distances)),
        )
        object.__setattr__(
            self,
            "exposure_evs",
            tuple(sorted(exposures)),
        )

    @property
    def digest(self) -> str:
        return _digest(
            {
                "azimuth_step_deg": self.azimuth_step_deg,
                "elevation_step_deg": self.elevation_step_deg,
                "roll_step_deg": self.roll_step_deg,
                "fov_degrees": list(self.fov_degrees),
                "distance_scales": list(self.distance_scales),
                "exposure_evs": list(self.exposure_evs),
                "include_poles": self.include_poles,
                "max_views": self.max_views,
            }
        )


@dataclass(frozen=True, slots=True)
class CameraCoveragePlan:
    policy_digest: str
    views: tuple[CameraView, ...]
    coverage_digest: str

    def __post_init__(self) -> None:
        if not self.views:
            raise CameraViewError(
                "camera coverage plan requires views"
            )
        if len(self.views) > _MAX_VIEWS:
            raise CameraViewError(
                "camera coverage exceeds hard view bound"
            )
        refs = [item.reference for item in self.views]
        if len(refs) != len(set(refs)):
            raise CameraViewError(
                "camera coverage contains duplicate views"
            )

    @property
    def references(self) -> tuple[str, ...]:
        return tuple(item.reference for item in self.views)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "skeleton.camera_coverage.v1",
            "policy_digest": self.policy_digest,
            "coverage_digest": self.coverage_digest,
            "view_count": len(self.views),
            "view_refs": list(self.references),
        }


def build_camera_coverage(
    policy: CameraCoveragePolicy | None = None,
) -> CameraCoveragePlan:
    """Generate deterministic bounded spherical/optical training coverage."""

    actual = policy or CameraCoveragePolicy()
    views: dict[str, CameraView] = {}

    elevations = list(
        range(
            -90,
            91,
            actual.elevation_step_deg,
        )
    )
    if not actual.include_poles:
        elevations = [
            value
            for value in elevations
            if abs(value) != 90
        ]

    azimuths = tuple(
        range(0, 360, actual.azimuth_step_deg)
    )
    rolls = tuple(
        range(0, 360, actual.roll_step_deg)
    )
    for elevation in elevations:
        pose_azimuths: Sequence[int] = (
            (0,)
            if abs(elevation) == 90
            else azimuths
        )
        for azimuth in pose_azimuths:
            for roll in rolls:
                for fov in actual.fov_degrees:
                    for distance in actual.distance_scales:
                        for exposure in actual.exposure_evs:
                            view = CameraView(
                                azimuth_deg=azimuth,
                                elevation_deg=elevation,
                                roll_deg=roll,
                                fov_deg=fov,
                                distance_scale=distance,
                                exposure_ev=exposure,
                            )
                            views[view.reference] = view
                            if len(views) > actual.max_views:
                                raise CameraViewError(
                                    "camera coverage exceeds policy max_views; "
                                    "increase sampling step or max_views"
                                )

    ordered = tuple(
        sorted(
            views.values(),
            key=lambda item: (
                item.elevation_deg,
                item.azimuth_deg,
                item.roll_deg,
                item.fov_deg,
                item.distance_scale,
                item.exposure_ev,
            ),
        )
    )
    payload = {
        "policy_digest": actual.digest,
        "view_refs": [item.reference for item in ordered],
    }
    return CameraCoveragePlan(
        policy_digest=actual.digest,
        views=ordered,
        coverage_digest=_digest(payload),
    )


def stratified_camera_subset(
    plan: CameraCoveragePlan,
    *,
    limit: int,
) -> tuple[CameraView, ...]:
    """Choose a deterministic spread across the full coverage lattice."""

    if not isinstance(plan, CameraCoveragePlan):
        raise TypeError("plan must be CameraCoveragePlan")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= len(plan.views)
    ):
        raise CameraViewError(
            "limit must be within camera view inventory"
        )
    if limit == len(plan.views):
        return plan.views
    if limit == 1:
        return (plan.views[len(plan.views) // 2],)

    indices: list[int] = []
    for position in range(limit):
        index = round(
            position * (len(plan.views) - 1) / (limit - 1)
        )
        if index not in indices:
            indices.append(index)
    # Rounding can collide for small inventories; fill deterministically.
    for index in range(len(plan.views)):
        if len(indices) >= limit:
            break
        if index not in indices:
            indices.append(index)
    indices.sort()
    return tuple(plan.views[index] for index in indices[:limit])


__all__ = [
    "CameraCoveragePlan",
    "CameraCoveragePolicy",
    "CameraView",
    "CameraViewError",
    "build_camera_coverage",
    "stratified_camera_subset",
]
