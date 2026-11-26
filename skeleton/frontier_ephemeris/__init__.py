"""Simulated game-time sun, moon, sight reduction, and calibration bench.

The package does not read the wall clock, an operating-system sensor, or a
geolocation service. Latitude and longitude are simulation parameters, and
the local frame is fictional East, North, Up.
"""

from skeleton.frontier_body.instrument_journal import SIMULATED_LABEL

from .bench import (
    BenchComparison,
    CalibrationBench,
    InstrumentSample,
    compare_instruments,
    open_calibration_bench,
    submit_calibration,
)
from .datum import (
    ASTRONOMICAL_UNIT_M,
    AUTHORITY,
    BAROMETER_REFERENCE_MAX_PA,
    BAROMETER_REFERENCE_MIN_PA,
    BUBBLE_BIAS_LIMIT_DEG,
    DATUM,
    DECLINATION_LIMIT_DEG,
    EPHEMERIS,
    FACTORY_BAROMETER_PA,
    FICTIONAL_EQUATORIAL_RADIUS_M,
    FICTIONAL_FLATTENING,
    GYRO_BIAS_LIMIT_DPS,
    HORIZON_REFRACTION_FACTOR,
    SEXTANT_INDEX_LIMIT_DEG,
    SUN_SERIES_AGREEMENT_ARC_MIN,
    SUN_SERIES_WINDOW_DAYS,
    CalibrationEpoch,
    EphemerisError,
    SimulationSite,
    fictional_geocentric_latitude_deg,
)
from .ephemeris import (
    BodyDirection,
    lunar_direction,
    simulated_earth_rotation_deg,
    simulation_day_number,
    solar_direction,
)
from .sight import (
    SightJournal,
    SightReduction,
    append_sight,
    bennett_refraction_deg,
    dump_sight_journal,
    horizon_dip_deg,
    load_sight_journal,
    open_sight_journal,
    reduce_sight,
    replay_sight_journal,
)

__all__ = (
    "ASTRONOMICAL_UNIT_M",
    "AUTHORITY",
    "BAROMETER_REFERENCE_MAX_PA",
    "BAROMETER_REFERENCE_MIN_PA",
    "BUBBLE_BIAS_LIMIT_DEG",
    "DATUM",
    "DECLINATION_LIMIT_DEG",
    "EPHEMERIS",
    "FACTORY_BAROMETER_PA",
    "FICTIONAL_EQUATORIAL_RADIUS_M",
    "FICTIONAL_FLATTENING",
    "GYRO_BIAS_LIMIT_DPS",
    "HORIZON_REFRACTION_FACTOR",
    "SEXTANT_INDEX_LIMIT_DEG",
    "SIMULATED_LABEL",
    "SUN_SERIES_AGREEMENT_ARC_MIN",
    "SUN_SERIES_WINDOW_DAYS",
    "BenchComparison",
    "BodyDirection",
    "CalibrationBench",
    "CalibrationEpoch",
    "EphemerisError",
    "InstrumentSample",
    "SightJournal",
    "SightReduction",
    "SimulationSite",
    "append_sight",
    "bennett_refraction_deg",
    "compare_instruments",
    "dump_sight_journal",
    "fictional_geocentric_latitude_deg",
    "horizon_dip_deg",
    "load_sight_journal",
    "lunar_direction",
    "open_calibration_bench",
    "open_sight_journal",
    "reduce_sight",
    "replay_sight_journal",
    "simulated_earth_rotation_deg",
    "simulation_day_number",
    "solar_direction",
    "submit_calibration",
)
