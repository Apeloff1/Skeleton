"""Operator approval for fictional survey sightings (GF-P0-118).

Sightings move draft -> approved -> consumed. Approval records the operator
who took the action. A navigation fix accepts only sightings that are
approved and not yet consumed, and only against an approved fictional
baseline. Coordinates are game-world metres. This module does not read
device location and does not accept an Earth datum.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from skeleton.frontier_nav.gps import PositionFix

FICTIONAL_DATUM = "planet_local_enu_not_earth_wgs84"
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
_ACTOR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .@_+\-]{1,63}$")


class SurveyAuthorityError(ValueError):
    """Raised when a sighting or baseline violates the approval contract."""


def _identity(value: object, name: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise SurveyAuthorityError(f"{name} is required")
    return value


def _actor(value: object) -> str:
    if type(value) is not str or _ACTOR.fullmatch(value.strip()) is None:
        raise SurveyAuthorityError("actor identity required")
    if value.strip().lower() == "anonymous":
        raise SurveyAuthorityError("actor identity required")
    return value.strip()


def _finite(value: object, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        raise SurveyAuthorityError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise SurveyAuthorityError(f"{name} is out of range")
    return number


@dataclass
class ControlStation:
    control_id: str
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        _identity(self.control_id, "control_id")
        self.x = _finite(self.x, "x", -1_000_000, 1_000_000)
        self.y = _finite(self.y, "y", -1_000_000, 1_000_000)
        self.z = _finite(self.z, "z", -1_000_000, 1_000_000)


@dataclass
class BaselineRecord:
    baseline_id: str
    datum: str
    epoch: str
    instrument: str
    surveyor: str
    notes: str
    stations: dict[str, ControlStation]
    status: str = "draft"
    approved_by: str | None = None

    def __post_init__(self) -> None:
        _identity(self.baseline_id, "baseline_id")
        if self.datum != FICTIONAL_DATUM:
            raise SurveyAuthorityError("baseline datum must be the fictional planet frame")
        if type(self.epoch) is not str or not self.epoch.strip() or len(self.epoch) > 64:
            raise SurveyAuthorityError("fictional epoch label is required")
        if type(self.instrument) is not str or not self.instrument.strip() or len(self.instrument) > 80:
            raise SurveyAuthorityError("instrument is required")
        if type(self.surveyor) is not str or not self.surveyor.strip() or len(self.surveyor) > 80:
            raise SurveyAuthorityError("surveyor is required")
        if type(self.notes) is not str or len(self.notes) > 500:
            raise SurveyAuthorityError("notes are too long")
        if self.status not in ("draft", "approved"):
            raise SurveyAuthorityError("baseline status is invalid")
        if not self.stations or len(self.stations) > 64:
            raise SurveyAuthorityError("baseline needs 1..64 fictional stations")
        if any(key != station.control_id for key, station in self.stations.items()):
            raise SurveyAuthorityError("station ids must match")


@dataclass
class SightingRecord:
    sighting_id: str
    baseline_id: str
    control_id: str
    bearing_deg: float
    distance_m: float
    uncertainty_m: float
    state: str = "draft"
    approved_by: str | None = None

    def __post_init__(self) -> None:
        _identity(self.sighting_id, "sighting_id")
        _identity(self.baseline_id, "baseline_id")
        _identity(self.control_id, "control_id")
        self.bearing_deg = _finite(self.bearing_deg, "bearing_deg", 0, 360)
        if self.bearing_deg == 360:
            raise SurveyAuthorityError("bearing_deg is out of range")
        self.distance_m = _finite(self.distance_m, "distance_m", 0.01, 100_000)
        self.uncertainty_m = _finite(self.uncertainty_m, "uncertainty_m", 0, 1000)
        if self.state not in ("draft", "approved", "consumed"):
            raise SurveyAuthorityError("sighting state is invalid")


def _bearing_point(station: ControlStation, bearing_deg: float, distance_m: float) -> tuple[float, float, float]:
    """0 degrees is fictional north (+Y). 90 degrees is fictional east (+X)."""
    radians = math.radians(bearing_deg)
    return (
        station.x + distance_m * math.sin(radians),
        station.y + distance_m * math.cos(radians),
        station.z,
    )


@dataclass
class SurveyBook:
    baselines: dict[str, BaselineRecord] = field(default_factory=dict)
    sightings: dict[str, SightingRecord] = field(default_factory=dict)

    def put_baseline(self, baseline: BaselineRecord) -> BaselineRecord:
        current = self.baselines.get(baseline.baseline_id)
        if current is not None and current.status != "draft":
            raise SurveyAuthorityError("approved baseline metadata is frozen")
        if any(item.baseline_id == baseline.baseline_id and item.state == "consumed"
               for item in self.sightings.values()):
            raise SurveyAuthorityError("baseline already entered a navigation fix")
        stored = BaselineRecord(
            baseline.baseline_id, baseline.datum, baseline.epoch.strip(),
            baseline.instrument.strip(), baseline.surveyor.strip(), baseline.notes.strip(),
            {key: ControlStation(station.control_id, station.x, station.y, station.z)
             for key, station in baseline.stations.items()},
            status="draft", approved_by=None,
        )
        self.baselines[stored.baseline_id] = stored
        for sighting in list(self.sightings.values()):
            if sighting.baseline_id == stored.baseline_id and sighting.state == "approved":
                sighting.state = "draft"
                sighting.approved_by = None
        return stored

    def approve_baseline(self, baseline_id: str, actor: str) -> BaselineRecord:
        who = _actor(actor)
        baseline = self.baselines.get(baseline_id)
        if baseline is None:
            raise SurveyAuthorityError("unknown baseline")
        if baseline.status == "approved":
            raise SurveyAuthorityError("baseline is already approved")
        baseline.status = "approved"
        baseline.approved_by = who
        return baseline

    def put_sighting(self, sighting: SightingRecord) -> SightingRecord:
        baseline = self.baselines.get(sighting.baseline_id)
        if baseline is None:
            raise SurveyAuthorityError("unknown baseline")
        if sighting.control_id not in baseline.stations:
            raise SurveyAuthorityError("sighting control is not on the baseline")
        current = self.sightings.get(sighting.sighting_id)
        if current is not None and current.state != "draft":
            raise SurveyAuthorityError("only a draft sighting can be edited")
        stored = SightingRecord(
            sighting.sighting_id, sighting.baseline_id, sighting.control_id,
            sighting.bearing_deg, sighting.distance_m, sighting.uncertainty_m,
            state="draft", approved_by=None,
        )
        self.sightings[stored.sighting_id] = stored
        return stored

    def approve_sighting(self, sighting_id: str, actor: str) -> SightingRecord:
        who = _actor(actor)
        sighting = self.sightings.get(sighting_id)
        if sighting is None:
            raise SurveyAuthorityError("unknown sighting")
        if sighting.state == "consumed":
            raise SurveyAuthorityError("consumed sighting cannot be approved")
        if sighting.state == "approved":
            raise SurveyAuthorityError("sighting is already approved")
        baseline = self.baselines.get(sighting.baseline_id)
        if baseline is None or baseline.status != "approved":
            raise SurveyAuthorityError("approve the baseline metadata first")
        sighting.state = "approved"
        sighting.approved_by = who
        return sighting

    def solve(self, sighting_ids: tuple[str, ...] | list[str], *, entity_id: str = "avatar") -> PositionFix:
        if not 1 <= len(sighting_ids) <= 32 or len(set(sighting_ids)) != len(sighting_ids):
            raise SurveyAuthorityError("choose 1..32 distinct sightings")
        chosen: list[SightingRecord] = []
        for sighting_id in sighting_ids:
            sighting = self.sightings.get(sighting_id)
            if sighting is None:
                raise SurveyAuthorityError("unknown sighting")
            if sighting.state == "consumed":
                raise SurveyAuthorityError("consumed sighting cannot enter a navigation fix")
            if sighting.state != "approved":
                raise SurveyAuthorityError("unapproved sighting cannot enter a navigation fix")
            chosen.append(sighting)
        baseline_ids = {item.baseline_id for item in chosen}
        if len(baseline_ids) != 1:
            raise SurveyAuthorityError("a fix must use one fictional baseline")
        baseline = self.baselines[chosen[0].baseline_id]
        if baseline.status != "approved":
            raise SurveyAuthorityError("unapproved baseline cannot enter a navigation fix")
        points: list[tuple[float, float, float, float]] = []
        for sighting in chosen:
            station = baseline.stations.get(sighting.control_id)
            if station is None:
                raise SurveyAuthorityError("sighting control is not on the baseline")
            x, y, z = _bearing_point(station, sighting.bearing_deg, sighting.distance_m)
            weight = 1.0 / max(sighting.uncertainty_m, 0.05) ** 2
            points.append((x, y, z, weight))
        weight_sum = sum(item[3] for item in points)
        mean = tuple(sum(item[axis] * item[3] for item in points) / weight_sum for axis in range(3))
        for sighting, point in zip(chosen, points):
            residual = math.dist(mean, point[:3])
            if residual > max(sighting.uncertainty_m, 0.05) + 0.05:
                raise SurveyAuthorityError("approved sightings do not agree on one fictional position")
        fix = PositionFix(
            entity_id,
            round(mean[0], 6),
            round(mean[1], 6),
            round(mean[2], 6),
            region=baseline.baseline_id,
        )
        fix.validate()
        for sighting in chosen:
            sighting.state = "consumed"
        return fix
