"""Deterministic simulated navigation instruments for game worlds.

ENU axes are East=x, North=y, Up=z. Angles are degrees unless documented.
Instruments consume explicitly supplied environmental truth and instrument
calibration. A sextant measures a *supplied* celestial direction; it does not
magically solve geographical position or invent ephemerides. Bubble sextants
use an artificial vertical with acceleration/tilt error. No GPS/service IO.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math

from .game_frontier_production import Vec3
from .game_frontier_ecosystem import AirConditions, sample_atmosphere


class InstrumentError(ValueError):
    pass


def bounded(value: float, label: str, lo: float, hi: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not lo <= value <= hi:
        raise InstrumentError(f"{label} outside finite limits")
    return float(value)


def size(v: Vec3) -> float:
    return math.sqrt(v.dot(v))


def _unit(v: Vec3) -> Vec3:
    n = size(v)
    if n < 1e-12:
        raise InstrumentError("zero instrument direction")
    return v.scaled(1/n)


def wrap360(deg: float) -> float:
    return deg % 360


@dataclass(frozen=True)
class NavigationEnvironment:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    geomagnetic_declination_deg: float = 0.
    magnetic_dip_deg: float = 60.
    magnetic_anomaly_deg: float = 0.
    sea_level_pressure_pa: float = 101325.
    air_temperature_c: float = 15.
    vertical_acceleration_mps2: float = 0.
    horizon_obscured: bool = False

    def __post_init__(self) -> None:
        bounded(self.latitude_deg, "latitude", -90, 90)
        bounded(self.longitude_deg, "longitude", -180, 180)
        bounded(self.altitude_m, "altitude", -500, 11000)
        bounded(self.geomagnetic_declination_deg, "declination", -180, 180)
        bounded(self.magnetic_dip_deg, "magnetic dip", -90, 90)
        bounded(self.magnetic_anomaly_deg, "magnetic anomaly", -180, 180)
        bounded(self.sea_level_pressure_pa, "sea level pressure", 30000, 120000)
        bounded(self.air_temperature_c, "air temperature", -80, 70)
        bounded(self.vertical_acceleration_mps2, "vertical acceleration", -9.8, 100)


@dataclass(frozen=True)
class Gyroscope:
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    bias_dps: Vec3 = Vec3(0, 0, 0)
    drift_dps: Vec3 = Vec3(0, 0, 0)

    def __post_init__(self) -> None:
        for label in ("yaw_deg", "pitch_deg", "roll_deg"):
            bounded(getattr(self, label), label, -3600, 3600)


@dataclass(frozen=True)
class GyroReading:
    yaw_deg: float
    pitch_deg: float
    roll_deg: float
    horizon_tilt_deg: float
    elapsed_s: float
    frame: str = "enu_east_north_up_reference"


def advance_gyroscope(gyro: Gyroscope, angular_rate_dps: Vec3, *,
                      delta_s: float,
                      correction_deg: Vec3 = Vec3(0, 0, 0)) -> GyroReading:
    """Yaw from Z angular rate, pitch from X, roll from Y; integrates bias.

    This Euler reference is not a quaternion strapdown INS; near gimbal-lock
    its orientation is approximate. Calibration correction is explicit.
    """
    dt = bounded(delta_s, "gyro dt", 0, 3600)
    yaw = wrap360(gyro.yaw_deg +
                  (angular_rate_dps.z+gyro.bias_dps.z+gyro.drift_dps.z)*dt
                  + correction_deg.z)
    pitch = max(-90, min(90, gyro.pitch_deg +
                  (angular_rate_dps.x+gyro.bias_dps.x+gyro.drift_dps.x)*dt
                  + correction_deg.x))
    roll = ((gyro.roll_deg +
             (angular_rate_dps.y+gyro.bias_dps.y+gyro.drift_dps.y)*dt
             + correction_deg.y + 180) % 360)-180
    tilt = math.degrees(math.acos(
        max(-1, min(1, math.cos(math.radians(pitch))*math.cos(math.radians(roll))))))
    return GyroReading(yaw,pitch,roll,tilt,dt)


@dataclass(frozen=True)
class CompassReading:
    true_heading_deg: float
    magnetic_heading_deg: float
    declination_deg: float
    dip_deg: float
    disturbed: bool
    confidence: float


def sample_compass(true_heading_deg: float,
                   env: NavigationEnvironment, *,
                   interference_deg: float = 0.) -> CompassReading:
    true = wrap360(bounded(true_heading_deg,"heading",-36000,36000))
    interference = bounded(interference_deg,"interference",-180,180)
    magnetic = wrap360(true-env.geomagnetic_declination_deg
                       -env.magnetic_anomaly_deg+interference)
    disturbed = abs(env.magnetic_anomaly_deg)+abs(interference) > 5
    confidence = max(0.,1-(abs(env.magnetic_anomaly_deg)
                            +abs(interference))/180)
    return CompassReading(true,magnetic,env.geomagnetic_declination_deg,
                          env.magnetic_dip_deg,disturbed,confidence)


@dataclass(frozen=True)
class SextantReading:
    apparent_altitude_deg: float
    corrected_altitude_deg: float
    azimuth_deg: float
    index_error_deg: float
    dip_correction_deg: float
    refraction_correction_deg: float
    synthetic_horizon: bool
    authority: str = "simulated_celestial_sighting_not_position_fix"


def _observe_celestial(target_direction_enu: Vec3) -> tuple[float,float]:
    sight = _unit(target_direction_enu)
    altitude = math.degrees(math.asin(max(-1,min(1,sight.z))))
    azimuth = wrap360(math.degrees(math.atan2(sight.x,sight.y)))
    return altitude,azimuth


def _refraction(altitude_deg: float, pressure_pa: float, temperature_c: float) -> float:
    if altitude_deg < -1 or altitude_deg > 89.9:
        return 0.
    h=max(-.99,altitude_deg)
    # Bennett formula in arcminutes, modestly pressure/temp corrected.
    arcmin = (1.02 / math.tan(math.radians(h+10.3/(h+5.11))))
    return arcmin/60 * (pressure_pa/101000) * (283/(273.15+temperature_c))


def sight_sextant(
    target_direction_enu: Vec3, env: NavigationEnvironment, *,
    eye_height_m: float = 2.,
    index_error_deg: float = 0.,
    refraction_correction: bool = True,
) -> SextantReading:
    eye=bounded(eye_height_m,"eye height",0,10000)
    index=bounded(index_error_deg,"index error",-5,5)
    if env.horizon_obscured:
        raise InstrumentError("natural-horizon sextant cannot observe obscured horizon")
    altitude, azimuth = _observe_celestial(target_direction_enu)
    # Dip of visible sea horizon for observer above spherical Earth.
    radius=6371000.
    dip=math.degrees(math.acos(radius/(radius+eye))) if eye else 0.
    air=sample_atmosphere(AirConditions(
        altitude_m=env.altitude_m,temperature_c=env.air_temperature_c))
    pressure=env.sea_level_pressure_pa*air.pressure_pa/101325
    correction=_refraction(altitude,pressure,env.air_temperature_c) if refraction_correction else 0.
    apparent=altitude+index+dip+correction
    return SextantReading(apparent,apparent-index-dip-correction,azimuth,
                          index,dip,correction,False)


def sight_bubble_sextant(
    target_direction_enu: Vec3, env: NavigationEnvironment, *,
    gyro_pitch_deg: float = 0.,
    gyro_roll_deg: float = 0.,
    bubble_alignment_deg: float = 0.,
    index_error_deg: float = 0.,
) -> SextantReading:
    """Artificial-horizon celestial altitude with gyro/bubble alignment bias.

    Does NOT use true sea horizon and remains operable under obscured horizon,
    subject to bubble acceleration and attitude errors.
    """
    altitude, azimuth = _observe_celestial(target_direction_enu)
    pitch=bounded(gyro_pitch_deg,"gyro pitch",-90,90)
    roll=bounded(gyro_roll_deg,"gyro roll",-180,180)
    alignment=bounded(bubble_alignment_deg,"bubble offset",-10,10)
    index=bounded(index_error_deg,"index error",-5,5)
    dynamic_error=math.degrees(math.atan2(
        env.vertical_acceleration_mps2,9.80665))*.08
    # Tilt projected onto apparent azimuth: horizontal-plane bubble error.
    error=(pitch*math.cos(math.radians(azimuth))+
           roll*math.sin(math.radians(azimuth))+
           alignment+dynamic_error)
    apparent=altitude+index+error
    return SextantReading(apparent,apparent-index-error,azimuth,
                          index,0.,0.,True)


@dataclass(frozen=True)
class AltimeterReading:
    altitude_m: float
    altitude_ft: float
    source: str
    source_observation: float
    calibration: str
    authority: str = "simulated_altitude_not_sensor_attestation"


def barometric_altimeter(pressure_pa: float, *,
                         sea_level_pressure_pa: float = 101325.,
                         temperature_c: float = 15.) -> AltimeterReading:
    pressure=bounded(pressure_pa,"observed pressure",1000,120000)
    reference=bounded(sea_level_pressure_pa,"sea pressure",30000,120000)
    temperature=bounded(temperature_c,"temperature",-80,70)
    # Hypsometric equation (isothermal layer approximation) uses local
    # temperature. This differs from ISA standard atmosphere at altitude.
    altitude=287.05*(temperature+273.15)/9.80665*math.log(reference/pressure)
    return AltimeterReading(altitude,altitude*3.280839895,
                            "hypsometric_barometric",pressure,"sea_level_pressure_and_air_temperature")


def trigonometric_altimeter(
    horizontal_baseline_m: float, elevation_angle_deg: float, *,
    observer_altitude_m: float = 0.,
    instrument_height_m: float = 0.,
    curvature_correction: bool = False,
    refraction_fraction: float = .13,
) -> AltimeterReading:
    """Target altitude from horizontal baseline, not slant range.

    Curvature/refraction optional at long baselines; a geometric straight-
    line reference, not a surveyed geodetic altitude fix.
    """
    distance=bounded(horizontal_baseline_m,"baseline",0,100000)
    elev=bounded(elevation_angle_deg,"elevation angle",-89.5,89.5)
    origin=bounded(observer_altitude_m,"observer altitude",-10000,11000)
    eye=bounded(instrument_height_m,"instrument height",0,100)
    fraction=bounded(refraction_fraction,"refraction fraction",0,.5)
    altitude=origin+eye+distance*math.tan(math.radians(elev))
    if curvature_correction:
        altitude += distance**2/(2*6371000.)*(1-fraction)
    return AltimeterReading(altitude,altitude*3.280839895,
                            "trigonometric_baseline_elevation",
                            elev,"horizontal_baseline_elevation_observer_height")


def instrument_manifest(readings: tuple[object, ...]) -> dict:
    """Canonical typed receipts for replay and game UI instrument panels."""
    from dataclasses import asdict, is_dataclass
    if len(readings) > 32 or any(not is_dataclass(r) or isinstance(r,type) for r in readings):
        raise InstrumentError("bounded typed readings required")
    result=[{"type":type(r).__name__,"fields":asdict(r)} for r in readings]
    encoded=json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False)
    return {"schema":"skeleton.game.navigation_instruments.v1",
            "readings":result,
            "digest":sha256(encoded.encode()).hexdigest(),
            "authority":"simulation_only_no_location_fix"}
