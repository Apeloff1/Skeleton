"""Side-by-side calibration bench for simulated navigation instruments.

The caller submits gyro bias, compass declination, sextant index, bubble
bias, and a barometer reference as a named epoch. ``compare_instruments``
returns the uncorrected indication and the corrected indication together.
Both are labeled simulated.

Uncorrected means the indication before the stored adjustment is removed:
gyro integration keeps the bias, the compass shows magnetic heading, the
sextant and bubble altitudes keep index, dip or bubble bias, and refraction,
and the barometer still uses the factory sea-level constant. Corrected
removes the gyro bias and the sextant or bubble adjustments, restores true
heading from the stored declination, and evaluates the hypsometric altitude
at the submitted barometer reference.

An out-of-range number, or a numeric change that reuses an epoch id, raises
and leaves the caller's bench object as it was.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from skeleton.frontier_body.instrument_journal import SIMULATED_LABEL

from .datum import (
    AUTHORITY,
    DATUM,
    EPHEMERIS,
    FACTORY_BAROMETER_PA,
    CalibrationEpoch,
    EphemerisError,
    SimulationSite,
    _real,
    _vec3,
    install_epoch,
    require_game_time,
    require_simulated,
)
from .sight import reduce_sight


def _wrap360(degrees: float) -> float:
    return degrees % 360.0


def _wrap180(degrees: float) -> float:
    return ((degrees + 180.0) % 360.0) - 180.0


def _integrate(
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float,
    angular_rate_dps: tuple[float, float, float],
    bias_dps: tuple[float, float, float],
    delta_s: float,
) -> tuple[float, float, float]:
    """Pitch from X, roll from Y, yaw from Z, matching the game gyro axes."""

    yaw = _wrap360(yaw_deg + (angular_rate_dps[2] + bias_dps[2]) * delta_s)
    pitch = max(-90.0, min(90.0, pitch_deg + (angular_rate_dps[0] + bias_dps[0]) * delta_s))
    roll = _wrap180(roll_deg + (angular_rate_dps[1] + bias_dps[1]) * delta_s)
    return yaw, pitch, roll


def _hypsometric(pressure_pa: float, reference_pa: float, temperature_c: float) -> float:
    """Isothermal hypsometric altitude. Simulated, not a survey monument."""

    return 287.05 * (temperature_c + 273.15) / 9.80665 * math.log(reference_pa / pressure_pa)


@dataclass(frozen=True)
class InstrumentSample:
    gyro_yaw_deg: float
    gyro_pitch_deg: float
    gyro_roll_deg: float
    compass_heading_deg: float
    sextant_altitude_deg: float
    bubble_altitude_deg: float
    barometric_altitude_m: float
    label: str = SIMULATED_LABEL
    simulated: bool = True
    authority: str = AUTHORITY
    datum: str = DATUM
    ephemeris: str = EPHEMERIS

    def __post_init__(self) -> None:
        require_simulated(
            self.label, self.simulated, authority=self.authority, datum=self.datum, ephemeris=self.ephemeris,
        )


@dataclass(frozen=True)
class BenchComparison:
    game_time_s: float
    epoch_id: str
    uncorrected: InstrumentSample
    corrected: InstrumentSample
    label: str = SIMULATED_LABEL
    simulated: bool = True
    authority: str = AUTHORITY
    datum: str = DATUM
    ephemeris: str = EPHEMERIS

    def __post_init__(self) -> None:
        require_simulated(
            self.label, self.simulated, authority=self.authority, datum=self.datum, ephemeris=self.ephemeris,
        )
        if not isinstance(self.uncorrected, InstrumentSample) or not isinstance(self.corrected, InstrumentSample):
            raise EphemerisError("bench comparison needs two simulated samples")
        if self.uncorrected.label != SIMULATED_LABEL or self.corrected.label != SIMULATED_LABEL:
            raise EphemerisError("both bench columns must be labeled simulated")


@dataclass(frozen=True)
class CalibrationBench:
    active: CalibrationEpoch
    epochs: tuple[CalibrationEpoch, ...]


def open_calibration_bench(epoch: CalibrationEpoch) -> CalibrationBench:
    if not isinstance(epoch, CalibrationEpoch):
        raise EphemerisError("bench requires a calibration epoch")
    return CalibrationBench(epoch, (epoch,))


def submit_calibration(
    bench: CalibrationBench,
    *,
    epoch_id: str,
    gyro_bias_dps: tuple[float, float, float],
    compass_declination_deg: float,
    sextant_index_error_deg: float,
    bubble_bias_deg: float,
    barometer_reference_pa: float,
) -> CalibrationBench:
    """Store a new epoch, or reject an out-of-range or same-id change.

    Failure raises before a new bench is returned, so the caller's stored
    epoch is unchanged.
    """

    if not isinstance(bench, CalibrationBench) or not bench.epochs:
        raise EphemerisError("submit requires an open calibration bench")
    candidate = CalibrationEpoch(
        epoch_id,
        gyro_bias_dps,
        compass_declination_deg,
        sextant_index_error_deg,
        bubble_bias_deg,
        barometer_reference_pa,
    )
    active, epochs = install_epoch(bench.active, bench.epochs, candidate)
    if active is bench.active and epochs is bench.epochs:
        return bench
    return CalibrationBench(active, epochs)


def compare_instruments(
    bench: CalibrationBench,
    *,
    site: SimulationSite,
    game_time_s: float,
    true_heading_deg: float,
    angular_rate_dps: tuple[float, float, float],
    yaw_deg: float,
    pitch_deg: float,
    roll_deg: float,
    delta_s: float,
    observed_pressure_pa: float,
    air_temperature_c: float,
    body: str = "sun",
) -> BenchComparison:
    """Return uncorrected and corrected simulated readings side by side."""

    if not isinstance(bench, CalibrationBench) or not isinstance(bench.active, CalibrationEpoch):
        raise EphemerisError("comparison requires an open calibration bench")
    if not isinstance(site, SimulationSite):
        raise EphemerisError("comparison requires a simulation site")
    when = require_game_time(game_time_s)
    heading = _real(true_heading_deg, "true heading", -36000.0, 36000.0)
    rate = _vec3(angular_rate_dps, "angular rate", 10_000.0)
    yaw = _real(yaw_deg, "yaw", -3600.0, 3600.0)
    pitch = _real(pitch_deg, "pitch", -90.0, 90.0)
    roll = _real(roll_deg, "roll", -180.0, 180.0)
    step = _real(delta_s, "gyro dt", 0.0, 3600.0)
    pressure = _real(observed_pressure_pa, "observed pressure", 1000.0, 120_000.0)
    temperature = _real(air_temperature_c, "air temperature", -80.0, 70.0)
    active = bench.active
    natural = reduce_sight(
        site,
        active,
        game_time_s=when,
        body=body,
        kind="natural_horizon",
        pressure_pa=pressure,
        temperature_c=temperature,
    )
    bubble = reduce_sight(
        site,
        active,
        game_time_s=when,
        body=body,
        kind="bubble",
        pressure_pa=pressure,
        temperature_c=temperature,
    )
    raw_yaw, raw_pitch, raw_roll = _integrate(yaw, pitch, roll, rate, active.gyro_bias_dps, step)
    clean_yaw, clean_pitch, clean_roll = _integrate(yaw, pitch, roll, rate, (0.0, 0.0, 0.0), step)
    magnetic = _wrap360(heading - active.compass_declination_deg)
    restored = _wrap360(magnetic + active.compass_declination_deg)
    uncorrected = InstrumentSample(
        raw_yaw,
        raw_pitch,
        raw_roll,
        magnetic,
        natural.apparent_altitude_deg,
        bubble.apparent_altitude_deg,
        _hypsometric(pressure, FACTORY_BAROMETER_PA, temperature),
    )
    corrected = InstrumentSample(
        clean_yaw,
        clean_pitch,
        clean_roll,
        restored,
        natural.corrected_altitude_deg,
        bubble.corrected_altitude_deg,
        _hypsometric(pressure, active.barometer_reference_pa, temperature),
    )
    return BenchComparison(when, active.epoch_id, uncorrected, corrected)
