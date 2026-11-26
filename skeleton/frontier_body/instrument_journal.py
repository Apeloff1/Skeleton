"""Content-addressed instrument calibration journal on game time.

Gyro bias and drift, compass declination, sextant index error, and the
barometer's sea-level reference are stored as calibration epochs. Derived
readings are produced by the existing simulated instruments. The solar and
lunar directions are a documented mean-element ephemeris evaluated at the
supplied game time. They are not a device fix.

Every reading is labeled ``simulated``. The journal never reads the wall
clock, an operating-system sensor, or a geolocation service. Replay
re-integrates the stored inputs and must reproduce the stored readings.
Changing calibration numbers while keeping the active epoch id is rejected.
A new epoch id opens the next span.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re

from skeleton.jeeves.game_frontier_instruments import (
    Gyroscope,
    InstrumentError,
    NavigationEnvironment,
    advance_gyroscope,
    barometric_altimeter,
    sample_compass,
    sight_sextant,
)
from skeleton.jeeves.game_frontier_production import FrontierProductionError, Vec3


SIMULATED_LABEL = "simulated"
_SCHEMA = "skeleton.frontier_body.instrument_journal.v1"
_EPOCH_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")
_AUTHORITY = "simulated_navigation_not_geolocation"
_EPHEMERIS = "simulated_mean_element_ephemeris_not_gnss"


class InstrumentJournalError(ValueError):
    """Rejected calibration, game-time step, digest, or replay."""


def _real(value: float, label: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float) or isinstance(value, bool) or not math.isfinite(value):
        raise InstrumentJournalError(f"{label} must be finite")
    if not lo <= float(value) <= hi:
        raise InstrumentJournalError(f"{label} must lie in [{lo}, {hi}]")
    return float(value)


def _canon(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(payload: object) -> str:
    return sha256(_canon(payload).encode("utf-8")).hexdigest()


def _vec3(components: tuple[float, float, float], label: str, limit: float) -> tuple[float, float, float]:
    if type(components) is not tuple or len(components) != 3:
        raise InstrumentJournalError(f"{label} must be three components")
    return tuple(_real(component, label, -limit, limit) for component in components)


@dataclass(frozen=True)
class CalibrationEpoch:
    epoch_id: str
    gyro_bias_dps: tuple[float, float, float]
    gyro_drift_dps: tuple[float, float, float]
    compass_declination_deg: float
    sextant_index_error_deg: float
    barometer_reference_pa: float

    def __post_init__(self) -> None:
        if type(self.epoch_id) is not str or _EPOCH_ID.fullmatch(self.epoch_id) is None:
            raise InstrumentJournalError("calibration epoch id must be a short token")
        object.__setattr__(self, "gyro_bias_dps", _vec3(self.gyro_bias_dps, "gyro bias", 1000))
        object.__setattr__(self, "gyro_drift_dps", _vec3(self.gyro_drift_dps, "gyro drift", 1000))
        object.__setattr__(
            self,
            "compass_declination_deg",
            _real(self.compass_declination_deg, "declination", -180, 180),
        )
        object.__setattr__(
            self,
            "sextant_index_error_deg",
            _real(self.sextant_index_error_deg, "sextant index error", -5, 5),
        )
        object.__setattr__(
            self,
            "barometer_reference_pa",
            _real(self.barometer_reference_pa, "barometer reference", 30000, 120000),
        )

    def payload(self) -> dict:
        return {
            "epoch_id": self.epoch_id,
            "gyro_bias_dps": list(self.gyro_bias_dps),
            "gyro_drift_dps": list(self.gyro_drift_dps),
            "compass_declination_deg": self.compass_declination_deg,
            "sextant_index_error_deg": self.sextant_index_error_deg,
            "barometer_reference_pa": self.barometer_reference_pa,
        }

    def content_digest(self) -> str:
        return _digest(self.payload())


@dataclass(frozen=True)
class SimulatedReading:
    game_time_s: float
    label: str
    simulated: bool
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    horizon_tilt_deg: float
    true_heading_deg: float
    magnetic_heading_deg: float
    declination_deg: float
    sextant_apparent_altitude_deg: float
    sextant_corrected_altitude_deg: float
    sextant_index_error_deg: float
    barometric_altitude_m: float
    barometer_reference_pa: float
    solar_direction_enu: tuple[float, float, float]
    lunar_direction_enu: tuple[float, float, float]
    authority: str = _AUTHORITY
    ephemeris: str = _EPHEMERIS

    def __post_init__(self) -> None:
        if self.label != SIMULATED_LABEL or self.simulated is not True:
            raise InstrumentJournalError("every instrument reading must be labeled simulated")
        if self.authority != _AUTHORITY or self.ephemeris != _EPHEMERIS:
            raise InstrumentJournalError("instrument readings stay simulated navigation")

    def payload(self) -> dict:
        return {
            "game_time_s": self.game_time_s,
            "label": self.label,
            "simulated": True,
            "yaw_deg": self.yaw_deg,
            "pitch_deg": self.pitch_deg,
            "roll_deg": self.roll_deg,
            "horizon_tilt_deg": self.horizon_tilt_deg,
            "true_heading_deg": self.true_heading_deg,
            "magnetic_heading_deg": self.magnetic_heading_deg,
            "declination_deg": self.declination_deg,
            "sextant_apparent_altitude_deg": self.sextant_apparent_altitude_deg,
            "sextant_corrected_altitude_deg": self.sextant_corrected_altitude_deg,
            "sextant_index_error_deg": self.sextant_index_error_deg,
            "barometric_altitude_m": self.barometric_altitude_m,
            "barometer_reference_pa": self.barometer_reference_pa,
            "solar_direction_enu": list(self.solar_direction_enu),
            "lunar_direction_enu": list(self.lunar_direction_enu),
            "authority": self.authority,
            "ephemeris": self.ephemeris,
        }


@dataclass(frozen=True)
class InstrumentEntry:
    game_time_s: float
    angular_rate_dps: tuple[float, float, float]
    true_heading_deg: float
    observed_pressure_pa: float
    air_temperature_c: float
    calibration_epoch_id: str
    calibration_digest: str
    reading: SimulatedReading
    prior_digest: str
    digest: str


@dataclass(frozen=True)
class InstrumentJournal:
    calibration: CalibrationEpoch
    epochs: tuple[CalibrationEpoch, ...]
    origin_game_time_s: float
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    initial_yaw_deg: float
    initial_pitch_deg: float
    initial_roll_deg: float
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    entries: tuple[InstrumentEntry, ...]
    header_digest: str


def _wrap_unit(east: float, north: float, up: float) -> Vec3:
    vector = Vec3(east, north, up)
    length = math.sqrt(vector.dot(vector))
    if length < 1e-12:
        raise InstrumentJournalError("mean-element direction vanished")
    return vector.scaled(1.0 / length)


def _equatorial_to_enu(latitude_deg: float, hour_angle: float, declination: float) -> Vec3:
    lat = math.radians(latitude_deg)
    east = -math.cos(declination) * math.sin(hour_angle)
    north = math.sin(declination) * math.cos(lat) - math.cos(declination) * math.cos(hour_angle) * math.sin(lat)
    up = math.sin(lat) * math.sin(declination) + math.cos(lat) * math.cos(declination) * math.cos(hour_angle)
    return _wrap_unit(east, north, up)


def _mean_elements(game_time_s: float, longitude_deg: float, ecliptic_longitude: float) -> tuple[float, float, float]:
    """Rotate a mean ecliptic longitude into ENU at the game-time sidereal angle.

    ``game_time_s`` is seconds after the journal's arithmetic J2000.0 origin.
    The obliquity and sidereal rate are the standard low-precision mean
    elements. This is a simulated sighting direction, not a GNSS solution.
    """

    day = game_time_s / 86400.0
    obliquity = math.radians(23.439 - 0.0000004 * day)
    right_ascension = math.atan2(
        math.cos(obliquity) * math.sin(ecliptic_longitude),
        math.cos(ecliptic_longitude),
    )
    declination = math.asin(max(-1.0, min(1.0, math.sin(obliquity) * math.sin(ecliptic_longitude))))
    sidereal = math.radians((280.46061837 + 360.98564736629 * day + longitude_deg) % 360.0)
    return right_ascension, declination, sidereal - right_ascension


def simulated_solar_direction(latitude_deg: float, longitude_deg: float, game_time_s: float) -> Vec3:
    day = game_time_s / 86400.0
    mean_longitude = math.radians((280.460 + 0.9856474 * day) % 360.0)
    mean_anomaly = math.radians((357.528 + 0.9856003 * day) % 360.0)
    ecliptic = mean_longitude + math.radians(1.915 * math.sin(mean_anomaly) + 0.020 * math.sin(2.0 * mean_anomaly))
    _right_ascension, declination, hour_angle = _mean_elements(game_time_s, longitude_deg, ecliptic)
    return _equatorial_to_enu(latitude_deg, hour_angle, declination)


def simulated_lunar_direction(latitude_deg: float, longitude_deg: float, game_time_s: float) -> Vec3:
    day = game_time_s / 86400.0
    ecliptic = math.radians((218.3164477 + 13.17639648 * day) % 360.0)
    _right_ascension, declination, hour_angle = _mean_elements(game_time_s, longitude_deg, ecliptic)
    return _equatorial_to_enu(latitude_deg, hour_angle, declination)


def _header_payload(journal: InstrumentJournal) -> dict:
    return {
        "schema": _SCHEMA,
        "origin_game_time_s": journal.origin_game_time_s,
        "latitude_deg": journal.latitude_deg,
        "longitude_deg": journal.longitude_deg,
        "altitude_m": journal.altitude_m,
        "initial_yaw_deg": journal.initial_yaw_deg,
        "initial_pitch_deg": journal.initial_pitch_deg,
        "initial_roll_deg": journal.initial_roll_deg,
        "calibration": journal.epochs[0].payload(),
    }


def open_instrument_journal(
    *,
    calibration: CalibrationEpoch,
    origin_game_time_s: float,
    latitude_deg: float,
    longitude_deg: float,
    altitude_m: float,
    yaw_deg: float = 0.0,
    pitch_deg: float = 0.0,
    roll_deg: float = 0.0,
) -> InstrumentJournal:
    if not isinstance(calibration, CalibrationEpoch):
        raise InstrumentJournalError("journal requires a calibration epoch")
    origin = _real(origin_game_time_s, "origin game time", 0, 1e12)
    try:
        NavigationEnvironment(latitude_deg, longitude_deg, altitude_m)
        Gyroscope(yaw_deg, pitch_deg, roll_deg)
    except (InstrumentError, FrontierProductionError) as exc:
        raise InstrumentJournalError(str(exc)) from exc
    journal = InstrumentJournal(
        calibration,
        (calibration,),
        origin,
        float(latitude_deg),
        float(longitude_deg),
        float(altitude_m),
        float(yaw_deg),
        float(pitch_deg),
        float(roll_deg),
        float(yaw_deg),
        float(pitch_deg),
        float(roll_deg),
        (),
        "",
    )
    return _with_header(journal)


def _with_header(journal: InstrumentJournal) -> InstrumentJournal:
    return InstrumentJournal(
        journal.calibration,
        journal.epochs,
        journal.origin_game_time_s,
        journal.latitude_deg,
        journal.longitude_deg,
        journal.altitude_m,
        journal.initial_yaw_deg,
        journal.initial_pitch_deg,
        journal.initial_roll_deg,
        journal.yaw_deg,
        journal.pitch_deg,
        journal.roll_deg,
        journal.entries,
        _digest(_header_payload(journal)),
    )


def _select_epoch(journal: InstrumentJournal, calibration: CalibrationEpoch | None) -> tuple[CalibrationEpoch, tuple[CalibrationEpoch, ...]]:
    chosen = journal.calibration if calibration is None else calibration
    if not isinstance(chosen, CalibrationEpoch):
        raise InstrumentJournalError("calibration must be an epoch")
    known = {epoch.epoch_id: epoch for epoch in journal.epochs}
    if chosen.epoch_id in known:
        if known[chosen.epoch_id].content_digest() != chosen.content_digest():
            raise InstrumentJournalError("changing calibration mid-stream requires a new epoch")
        if chosen.epoch_id != journal.calibration.epoch_id:
            raise InstrumentJournalError("changing calibration mid-stream requires a new epoch")
        return known[chosen.epoch_id], journal.epochs
    return chosen, journal.epochs + (chosen,)


def _entry_payload(entry: InstrumentEntry) -> dict:
    return {
        "game_time_s": entry.game_time_s,
        "angular_rate_dps": list(entry.angular_rate_dps),
        "true_heading_deg": entry.true_heading_deg,
        "observed_pressure_pa": entry.observed_pressure_pa,
        "air_temperature_c": entry.air_temperature_c,
        "calibration_epoch_id": entry.calibration_epoch_id,
        "calibration_digest": entry.calibration_digest,
        "reading": entry.reading.payload(),
        "prior_digest": entry.prior_digest,
    }


def append_reading(
    journal: InstrumentJournal,
    *,
    game_time_s: float,
    angular_rate_dps: tuple[float, float, float],
    true_heading_deg: float,
    observed_pressure_pa: float,
    air_temperature_c: float,
    calibration: CalibrationEpoch | None = None,
) -> InstrumentJournal:
    """Integrate one simulated fix at ``game_time_s`` and chain its digest."""

    if not isinstance(journal, InstrumentJournal) or not journal.header_digest:
        raise InstrumentJournalError("append requires an open instrument journal")
    when = _real(game_time_s, "game_time_s", 0, 1e12)
    previous_time = journal.entries[-1].game_time_s if journal.entries else journal.origin_game_time_s
    if journal.entries and when <= previous_time:
        raise InstrumentJournalError("readings advance on game time")
    if when < journal.origin_game_time_s:
        raise InstrumentJournalError("reading precedes the journal origin")
    rate = _vec3(angular_rate_dps, "angular rate", 10000)
    heading = _real(true_heading_deg, "true heading", -36000, 36000)
    pressure = _real(observed_pressure_pa, "observed pressure", 1000, 120000)
    temperature = _real(air_temperature_c, "air temperature", -80, 70)
    active, epochs = _select_epoch(journal, calibration)
    delta_s = when - previous_time
    if delta_s > 3600:
        raise InstrumentJournalError("game-time step exceeds the instrument integration limit")
    try:
        environment = NavigationEnvironment(
            journal.latitude_deg,
            journal.longitude_deg,
            journal.altitude_m,
            geomagnetic_declination_deg=active.compass_declination_deg,
            sea_level_pressure_pa=active.barometer_reference_pa,
            air_temperature_c=temperature,
        )
        gyro = advance_gyroscope(
            Gyroscope(
                journal.yaw_deg,
                journal.pitch_deg,
                journal.roll_deg,
                bias_dps=Vec3(*active.gyro_bias_dps),
                drift_dps=Vec3(*active.gyro_drift_dps),
            ),
            Vec3(*rate),
            delta_s=delta_s,
        )
        compass = sample_compass(heading, environment)
        solar = simulated_solar_direction(journal.latitude_deg, journal.longitude_deg, when)
        lunar = simulated_lunar_direction(journal.latitude_deg, journal.longitude_deg, when)
        sextant = sight_sextant(
            solar,
            environment,
            eye_height_m=2.0,
            index_error_deg=active.sextant_index_error_deg,
        )
        barometer = barometric_altimeter(
            pressure,
            sea_level_pressure_pa=active.barometer_reference_pa,
            temperature_c=temperature,
        )
    except (InstrumentError, FrontierProductionError) as exc:
        raise InstrumentJournalError(str(exc)) from exc
    reading = SimulatedReading(
        when,
        SIMULATED_LABEL,
        True,
        gyro.yaw_deg,
        gyro.pitch_deg,
        gyro.roll_deg,
        gyro.horizon_tilt_deg,
        compass.true_heading_deg,
        compass.magnetic_heading_deg,
        compass.declination_deg,
        sextant.apparent_altitude_deg,
        sextant.corrected_altitude_deg,
        sextant.index_error_deg,
        barometer.altitude_m,
        active.barometer_reference_pa,
        (solar.x, solar.y, solar.z),
        (lunar.x, lunar.y, lunar.z),
    )
    prior = journal.entries[-1].digest if journal.entries else journal.header_digest
    entry = InstrumentEntry(
        when,
        rate,
        heading,
        pressure,
        temperature,
        active.epoch_id,
        active.content_digest(),
        reading,
        prior,
        "",
    )
    entry = InstrumentEntry(
        entry.game_time_s,
        entry.angular_rate_dps,
        entry.true_heading_deg,
        entry.observed_pressure_pa,
        entry.air_temperature_c,
        entry.calibration_epoch_id,
        entry.calibration_digest,
        entry.reading,
        entry.prior_digest,
        _digest(_entry_payload(entry)),
    )
    return InstrumentJournal(
        active,
        epochs,
        journal.origin_game_time_s,
        journal.latitude_deg,
        journal.longitude_deg,
        journal.altitude_m,
        journal.initial_yaw_deg,
        journal.initial_pitch_deg,
        journal.initial_roll_deg,
        gyro.yaw_deg,
        gyro.pitch_deg,
        gyro.roll_deg,
        journal.entries + (entry,),
        journal.header_digest,
    )


def replay_instrument_journal(journal: InstrumentJournal) -> tuple[SimulatedReading, ...]:
    """Recompute every reading from stored inputs, game time, and epochs."""

    if not isinstance(journal, InstrumentJournal) or not journal.epochs:
        raise InstrumentJournalError("replay requires an instrument journal")
    rebuilt = open_instrument_journal(
        calibration=journal.epochs[0],
        origin_game_time_s=journal.origin_game_time_s,
        latitude_deg=journal.latitude_deg,
        longitude_deg=journal.longitude_deg,
        altitude_m=journal.altitude_m,
        yaw_deg=journal.initial_yaw_deg,
        pitch_deg=journal.initial_pitch_deg,
        roll_deg=journal.initial_roll_deg,
    )
    if rebuilt.header_digest != journal.header_digest:
        raise InstrumentJournalError("replay header does not match the journal")
    epochs = {epoch.epoch_id: epoch for epoch in journal.epochs}
    for entry in journal.entries:
        if entry.calibration_epoch_id not in epochs:
            raise InstrumentJournalError("replay is missing a calibration epoch")
        if epochs[entry.calibration_epoch_id].content_digest() != entry.calibration_digest:
            raise InstrumentJournalError("replay calibration digest mismatch")
        rebuilt = append_reading(
            rebuilt,
            game_time_s=entry.game_time_s,
            angular_rate_dps=entry.angular_rate_dps,
            true_heading_deg=entry.true_heading_deg,
            observed_pressure_pa=entry.observed_pressure_pa,
            air_temperature_c=entry.air_temperature_c,
            calibration=epochs[entry.calibration_epoch_id],
        )
    if tuple(item.digest for item in rebuilt.entries) != tuple(item.digest for item in journal.entries):
        raise InstrumentJournalError("replay diverged from the stored journal")
    readings = tuple(item.reading for item in rebuilt.entries)
    if readings != tuple(item.reading for item in journal.entries):
        raise InstrumentJournalError("replay readings diverged")
    return readings


def dump_instrument_journal(journal: InstrumentJournal) -> str:
    if not isinstance(journal, InstrumentJournal):
        raise InstrumentJournalError("instrument dump requires a journal")
    if _digest(_header_payload(journal)) != journal.header_digest:
        raise InstrumentJournalError("instrument journal header digest mismatch")
    entries = []
    for entry in journal.entries:
        payload = _entry_payload(entry)
        if _digest(payload) != entry.digest:
            raise InstrumentJournalError("instrument entry digest mismatch")
        payload["digest"] = entry.digest
        entries.append(payload)
    body = {
        "schema": _SCHEMA,
        "header_digest": journal.header_digest,
        "origin_game_time_s": journal.origin_game_time_s,
        "latitude_deg": journal.latitude_deg,
        "longitude_deg": journal.longitude_deg,
        "altitude_m": journal.altitude_m,
        "initial_yaw_deg": journal.initial_yaw_deg,
        "initial_pitch_deg": journal.initial_pitch_deg,
        "initial_roll_deg": journal.initial_roll_deg,
        "epochs": [epoch.payload() for epoch in journal.epochs],
        "entries": entries,
    }
    return _canon(body)


def _reading_from_payload(payload: object) -> SimulatedReading:
    if not isinstance(payload, dict):
        raise InstrumentJournalError("stored reading is not an object")
    try:
        return SimulatedReading(
            payload["game_time_s"],
            payload["label"],
            payload["simulated"],
            payload["yaw_deg"],
            payload["pitch_deg"],
            payload["roll_deg"],
            payload["horizon_tilt_deg"],
            payload["true_heading_deg"],
            payload["magnetic_heading_deg"],
            payload["declination_deg"],
            payload["sextant_apparent_altitude_deg"],
            payload["sextant_corrected_altitude_deg"],
            payload["sextant_index_error_deg"],
            payload["barometric_altitude_m"],
            payload["barometer_reference_pa"],
            tuple(payload["solar_direction_enu"]),
            tuple(payload["lunar_direction_enu"]),
            payload["authority"],
            payload["ephemeris"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InstrumentJournalError("stored reading is incomplete") from exc


def _epoch_from_payload(payload: dict) -> CalibrationEpoch:
    try:
        return CalibrationEpoch(
            payload["epoch_id"],
            tuple(payload["gyro_bias_dps"]),
            tuple(payload["gyro_drift_dps"]),
            payload["compass_declination_deg"],
            payload["sextant_index_error_deg"],
            payload["barometer_reference_pa"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InstrumentJournalError("calibration epoch payload is incomplete") from exc


def load_instrument_journal(payload: str) -> InstrumentJournal:
    if type(payload) is not str or not payload:
        raise InstrumentJournalError("instrument journal payload must be text")
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise InstrumentJournalError("instrument journal payload is not JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema") != _SCHEMA:
        raise InstrumentJournalError("instrument journal schema mismatch")
    try:
        epochs = tuple(_epoch_from_payload(item) for item in raw["epochs"])
        journal = open_instrument_journal(
            calibration=epochs[0],
            origin_game_time_s=raw["origin_game_time_s"],
            latitude_deg=raw["latitude_deg"],
            longitude_deg=raw["longitude_deg"],
            altitude_m=raw["altitude_m"],
            yaw_deg=raw["initial_yaw_deg"],
            pitch_deg=raw["initial_pitch_deg"],
            roll_deg=raw["initial_roll_deg"],
        )
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise InstrumentJournalError("instrument journal header is incomplete") from exc
    if journal.header_digest != raw.get("header_digest"):
        raise InstrumentJournalError("instrument journal header digest mismatch")
    known = {epoch.epoch_id: epoch for epoch in epochs}
    for item in raw["entries"]:
        if not isinstance(item, dict):
            raise InstrumentJournalError("instrument entry is not an object")
        try:
            epoch = known[item["calibration_epoch_id"]]
            if epoch.content_digest() != item["calibration_digest"]:
                raise InstrumentJournalError("stored calibration digest mismatch")
            stored = _reading_from_payload(item["reading"])
            claimed = InstrumentEntry(
                item["game_time_s"],
                tuple(item["angular_rate_dps"]),
                item["true_heading_deg"],
                item["observed_pressure_pa"],
                item["air_temperature_c"],
                item["calibration_epoch_id"],
                item["calibration_digest"],
                stored,
                item["prior_digest"],
                "",
            )
            if _digest(_entry_payload(claimed)) != item.get("digest"):
                raise InstrumentJournalError("instrument journal digest mismatch")
            journal = append_reading(
                journal,
                game_time_s=item["game_time_s"],
                angular_rate_dps=tuple(item["angular_rate_dps"]),
                true_heading_deg=item["true_heading_deg"],
                observed_pressure_pa=item["observed_pressure_pa"],
                air_temperature_c=item["air_temperature_c"],
                calibration=epoch,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InstrumentJournalError("instrument entry is incomplete") from exc
        if journal.entries[-1].digest != item.get("digest"):
            raise InstrumentJournalError("instrument journal digest mismatch")
    if len(journal.epochs) != len(epochs):
        raise InstrumentJournalError("instrument journal epoch chain mismatch")
    return journal
