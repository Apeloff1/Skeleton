"""Fictional local datum and stored instrument calibrations.

Latitude, longitude, and observer height are simulation parameters on the
game clock. They are not a device fix, an operating-system sensor, or a
published Earth geodetic datum. The local frame is East, North, Up.

Every public reading built on these types stays labeled ``simulated``.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from hashlib import sha256

from skeleton.frontier_body.instrument_journal import SIMULATED_LABEL

DATUM = "fictional_local_enu"
AUTHORITY = "simulated_navigation_not_geolocation"
EPHEMERIS = "simulated_mean_element_ephemeris_not_gnss"

# Game-world ellipsoid. The equatorial radius is the sphere already used by
# the frontier instruments. Flattening is 1/300. Neither number is taken
# from a GNSS datum, and neither is read from a device.
FICTIONAL_EQUATORIAL_RADIUS_M = 6_371_000.0
FICTIONAL_FLATTENING = 1.0 / 300.0

# One astronomical unit, used only to scale the simulated solar distance
# into equatorial radii of the fictional ellipsoid.
ASTRONOMICAL_UNIT_M = 149_597_870_700.0

# Independent-series agreement. The package sun is a Kepler mean-element
# series. The marathon test compares it with a separate Astronomical Almanac
# ecliptic series over ±50 Julian years about arithmetic J2000.0. Those two
# truncations are each about one arcminute. A dense scan of the window
# stays under 0.4 arcmin, and a separation above this bound fails the test.
SUN_SERIES_WINDOW_DAYS = 50.0 * 365.25
SUN_SERIES_AGREEMENT_ARC_MIN = 1.0

# Nautical dip is about 0.92 of the pure geometric horizon depression
# (1.76 arcmin per square-root meter against about 1.93). The factor is a
# documented refraction stand-in for the horizon, not a sensor reading.
HORIZON_REFRACTION_FACTOR = 0.92

FACTORY_BAROMETER_PA = 101_325.0
GYRO_BIAS_LIMIT_DPS = 15.0
DECLINATION_LIMIT_DEG = 180.0
SEXTANT_INDEX_LIMIT_DEG = 5.0
BUBBLE_BIAS_LIMIT_DEG = 10.0
BAROMETER_REFERENCE_MIN_PA = 30_000.0
BAROMETER_REFERENCE_MAX_PA = 120_000.0
OBSERVER_HEIGHT_LIMIT_M = 10_000.0
GAME_TIME_LIMIT_S = 1.0e12

_EPOCH_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")


class EphemerisError(ValueError):
    """Rejected game time, calibration, sight, or bench adjustment."""


def _real(value: float, label: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(value):
        raise EphemerisError(f"{label} must be finite")
    if not lo <= float(value) <= hi:
        raise EphemerisError(f"{label} must lie in [{lo}, {hi}]")
    return float(value)


def _vec3(components: tuple[float, float, float], label: str, limit: float) -> tuple[float, float, float]:
    if type(components) is not tuple or len(components) != 3:
        raise EphemerisError(f"{label} must be three components")
    return tuple(_real(component, label, -limit, limit) for component in components)


def canon(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(payload: object) -> str:
    return sha256(canon(payload).encode("utf-8")).hexdigest()


def require_game_time(value: float) -> float:
    return _real(value, "game time", -GAME_TIME_LIMIT_S, GAME_TIME_LIMIT_S)


def fictional_geocentric_latitude_deg(geodetic_latitude_deg: float) -> float:
    """Geocentric latitude on the fictional ellipsoid, degrees.

    ``tan(phi') = (1 - f)^2 tan(phi)`` with the stored flattening. The
    argument is a simulation parameter, not a device latitude.
    """

    latitude = _real(geodetic_latitude_deg, "latitude", -90.0, 90.0)
    if abs(latitude) == 90.0:
        return latitude
    factor = (1.0 - FICTIONAL_FLATTENING) ** 2
    return math.degrees(math.atan(factor * math.tan(math.radians(latitude))))


def observer_equatorial_radii(latitude_deg: float, height_m: float) -> tuple[float, float]:
    """Axial distance and polar distance of the observer, in equatorial radii.

    Both components follow the fictional ellipsoid normal at the stored
    geodetic latitude plus the stored observer height.
    """

    latitude = _real(latitude_deg, "latitude", -90.0, 90.0)
    height = _real(height_m, "observer height", 0.0, OBSERVER_HEIGHT_LIMIT_M)
    flattening = FICTIONAL_FLATTENING
    radius = FICTIONAL_EQUATORIAL_RADIUS_M
    eccentricity_sq = flattening * (2.0 - flattening)
    phi = math.radians(latitude)
    sin_phi = math.sin(phi)
    cos_phi = math.cos(phi)
    prime_vertical = radius / math.sqrt(1.0 - eccentricity_sq * sin_phi * sin_phi)
    axial = (prime_vertical + height) * cos_phi / radius
    polar = (prime_vertical * (1.0 - eccentricity_sq) + height) * sin_phi / radius
    return axial, polar


def local_gaussian_radius_m(latitude_deg: float) -> float:
    """Geometric-mean radius of curvature of the fictional ellipsoid."""

    latitude = _real(latitude_deg, "latitude", -90.0, 90.0)
    flattening = FICTIONAL_FLATTENING
    radius = FICTIONAL_EQUATORIAL_RADIUS_M
    eccentricity_sq = flattening * (2.0 - flattening)
    sin_phi = math.sin(math.radians(latitude))
    denominator = 1.0 - eccentricity_sq * sin_phi * sin_phi
    prime_vertical = radius / math.sqrt(denominator)
    meridional = radius * (1.0 - eccentricity_sq) / (denominator * math.sqrt(denominator))
    return math.sqrt(meridional * prime_vertical)


@dataclass(frozen=True)
class SimulationSite:
    """Fictional geodetic latitude, longitude, and eye height.

    These three numbers are simulation parameters supplied by the caller.
    """

    latitude_deg: float
    longitude_deg: float
    observer_height_m: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "latitude_deg", _real(self.latitude_deg, "latitude", -90.0, 90.0))
        object.__setattr__(self, "longitude_deg", _real(self.longitude_deg, "longitude", -180.0, 180.0))
        object.__setattr__(
            self,
            "observer_height_m",
            _real(self.observer_height_m, "observer height", 0.0, OBSERVER_HEIGHT_LIMIT_M),
        )

    def payload(self) -> dict:
        return {
            "latitude_deg": self.latitude_deg,
            "longitude_deg": self.longitude_deg,
            "observer_height_m": self.observer_height_m,
            "datum": DATUM,
        }


@dataclass(frozen=True)
class CalibrationEpoch:
    """Stored bench adjustments. Changing a number requires a new epoch id."""

    epoch_id: str
    gyro_bias_dps: tuple[float, float, float]
    compass_declination_deg: float
    sextant_index_error_deg: float
    bubble_bias_deg: float
    barometer_reference_pa: float

    def __post_init__(self) -> None:
        if type(self.epoch_id) is not str or _EPOCH_ID.fullmatch(self.epoch_id) is None:
            raise EphemerisError("calibration epoch id must be a short token")
        object.__setattr__(
            self,
            "gyro_bias_dps",
            _vec3(self.gyro_bias_dps, "gyro bias", GYRO_BIAS_LIMIT_DPS),
        )
        object.__setattr__(
            self,
            "compass_declination_deg",
            _real(self.compass_declination_deg, "declination", -DECLINATION_LIMIT_DEG, DECLINATION_LIMIT_DEG),
        )
        object.__setattr__(
            self,
            "sextant_index_error_deg",
            _real(
                self.sextant_index_error_deg,
                "sextant index error",
                -SEXTANT_INDEX_LIMIT_DEG,
                SEXTANT_INDEX_LIMIT_DEG,
            ),
        )
        object.__setattr__(
            self,
            "bubble_bias_deg",
            _real(self.bubble_bias_deg, "bubble bias", -BUBBLE_BIAS_LIMIT_DEG, BUBBLE_BIAS_LIMIT_DEG),
        )
        object.__setattr__(
            self,
            "barometer_reference_pa",
            _real(
                self.barometer_reference_pa,
                "barometer reference",
                BAROMETER_REFERENCE_MIN_PA,
                BAROMETER_REFERENCE_MAX_PA,
            ),
        )

    def payload(self) -> dict:
        return {
            "epoch_id": self.epoch_id,
            "gyro_bias_dps": list(self.gyro_bias_dps),
            "compass_declination_deg": self.compass_declination_deg,
            "sextant_index_error_deg": self.sextant_index_error_deg,
            "bubble_bias_deg": self.bubble_bias_deg,
            "barometer_reference_pa": self.barometer_reference_pa,
        }

    def content_digest(self) -> str:
        return digest(self.payload())


def require_simulated(label: str, simulated: bool, *, authority: str, datum: str, ephemeris: str) -> None:
    if label != SIMULATED_LABEL or simulated is not True:
        raise EphemerisError("every reading must be labeled simulated")
    if authority != AUTHORITY or datum != DATUM or ephemeris != EPHEMERIS:
        raise EphemerisError("readings stay on the fictional local datum")


def install_epoch(
    active: CalibrationEpoch,
    epochs: tuple[CalibrationEpoch, ...],
    candidate: CalibrationEpoch,
) -> tuple[CalibrationEpoch, tuple[CalibrationEpoch, ...]]:
    """Adopt ``candidate`` or reject a same-id numeric change.

    The returned objects are new. Callers that catch ``EphemerisError`` keep
    the epoch tuple they already stored.
    """

    if not isinstance(candidate, CalibrationEpoch):
        raise EphemerisError("calibration must be an epoch")
    for existing in epochs:
        if existing.epoch_id == candidate.epoch_id:
            if existing.payload() != candidate.payload():
                raise EphemerisError("changing a calibration number requires a new epoch id")
            return existing, epochs
    return candidate, epochs + (candidate,)
