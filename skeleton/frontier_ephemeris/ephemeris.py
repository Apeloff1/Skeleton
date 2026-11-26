"""Mean-element sun and moon, and an Earth-rotation stand-in.

``game_time_s = 0`` is the arithmetic simulation instant J2000.0
(JD 2451545.0). The day argument used by the orbital elements is
``game_time_s / 86400 + 1.5``, which places day 0 at arithmetic
1999 Dec 31 00:00. Nothing in this module reads a wall clock.

The sun and moon follow a documented Kepler mean-element series with the
principal lunar perturbations (evection, variation, and the yearly
equation among them). Local sidereal angle is that series' solar mean
longitude plus the simulation clock's turn angle plus the caller-supplied
longitude. The result is a unit vector in fictional local East, North, Up.

Topocentric place shifts the geocentric vector by the observer's position
on the fictional ellipsoid. That shift is simulated parallax, not a
satellite-navigation solution.
"""

from __future__ import annotations

import math

from skeleton.frontier_body.instrument_journal import SIMULATED_LABEL

from .datum import (
    ASTRONOMICAL_UNIT_M,
    AUTHORITY,
    DATUM,
    EPHEMERIS,
    FICTIONAL_EQUATORIAL_RADIUS_M,
    EphemerisError,
    SimulationSite,
    observer_equatorial_radii,
    require_game_time,
    require_simulated,
)


def _wrap360(degrees: float) -> float:
    return degrees % 360.0


def _unit(east: float, north: float, up: float) -> tuple[float, float, float]:
    length = math.sqrt(east * east + north * north + up * up)
    if length < 1e-12:
        raise EphemerisError("mean-element direction vanished")
    return (east / length, north / length, up / length)


def simulation_day_number(game_time_s: float) -> float:
    """Days after arithmetic 1999 Dec 31 00:00 on the simulation clock."""

    return require_game_time(game_time_s) / 86400.0 + 1.5


def _clock_turn_deg(game_time_s: float) -> float:
    """Simulation-clock angle from midnight, degrees.

    Arithmetic J2000.0 is noon, so game time 0 corresponds to 180 degrees.
    This is the fractional turn of the game clock, not an operating-system time.
    """

    day = require_game_time(game_time_s) / 86400.0
    return (180.0 + day * 360.0) % 360.0


def _sun_mean_elements(day_number: float) -> tuple[float, float, float]:
    perihelion = 282.9404 + 4.70935e-5 * day_number
    eccentricity = 0.016709 - 1.151e-9 * day_number
    anomaly = 356.0470 + 0.9856002585 * day_number
    if not 0.0 <= eccentricity < 0.2:
        raise EphemerisError("solar eccentricity left the mean-element window")
    return perihelion, eccentricity, anomaly


def simulated_earth_rotation_deg(game_time_s: float) -> float:
    """Mean sidereal angle of the fictional prime meridian, degrees.

    Greenwich-equivalent stand-in: solar mean longitude plus 180 degrees
    plus the simulation clock's turn angle. Longitude is applied later by
    the caller. The angle advances only when ``game_time_s`` advances.
    """

    day_number = simulation_day_number(game_time_s)
    perihelion, _eccentricity, anomaly = _sun_mean_elements(day_number)
    mean_longitude = anomaly + perihelion
    return _wrap360(mean_longitude + 180.0 + _clock_turn_deg(game_time_s))


def _kepler(mean_anomaly_rad: float, eccentricity: float) -> float:
    eccentric = mean_anomaly_rad
    for _ in range(15):
        slope = 1.0 - eccentricity * math.cos(eccentric)
        if slope == 0.0:
            raise EphemerisError("Kepler iteration lost its slope")
        delta = (eccentric - eccentricity * math.sin(eccentric) - mean_anomaly_rad) / slope
        eccentric -= delta
        if abs(delta) < 1e-14:
            break
    return eccentric


def _obliquity_rad(day_number: float) -> float:
    return math.radians(23.4393 - 3.563e-7 * day_number)


def _ecliptic_to_equatorial(
    x_ecl: float, y_ecl: float, z_ecl: float, day_number: float,
) -> tuple[float, float, float]:
    obliquity = _obliquity_rad(day_number)
    cosine = math.cos(obliquity)
    sine = math.sin(obliquity)
    return (
        x_ecl,
        y_ecl * cosine - z_ecl * sine,
        y_ecl * sine + z_ecl * cosine,
    )


def _orbit_ecliptic(
    distance: float,
    node: float,
    inclination: float,
    periapsis: float,
    true_anomaly: float,
) -> tuple[float, float, float]:
    argument = true_anomaly + periapsis
    cosine_node = math.cos(node)
    sine_node = math.sin(node)
    cosine_argument = math.cos(argument)
    sine_argument = math.sin(argument)
    cosine_inclination = math.cos(inclination)
    return (
        distance * (cosine_node * cosine_argument - sine_node * sine_argument * cosine_inclination),
        distance * (sine_node * cosine_argument + cosine_node * sine_argument * cosine_inclination),
        distance * (sine_argument * math.sin(inclination)),
    )


def _solve_orbit(
    node_deg: float,
    inclination_deg: float,
    periapsis_deg: float,
    semi_major: float,
    eccentricity: float,
    anomaly_deg: float,
) -> tuple[float, float, float]:
    mean = math.radians(anomaly_deg % 360.0)
    eccentric = _kepler(mean, eccentricity)
    xv = semi_major * (math.cos(eccentric) - eccentricity)
    yv = semi_major * math.sqrt(1.0 - eccentricity * eccentricity) * math.sin(eccentric)
    true_anomaly = math.atan2(yv, xv)
    distance = math.hypot(xv, yv)
    return _orbit_ecliptic(
        distance,
        math.radians(node_deg % 360.0),
        math.radians(inclination_deg),
        math.radians(periapsis_deg % 360.0),
        true_anomaly,
    )


def _sun_equatorial(day_number: float) -> tuple[float, float, float]:
    perihelion, eccentricity, anomaly = _sun_mean_elements(day_number)
    radii = ASTRONOMICAL_UNIT_M / FICTIONAL_EQUATORIAL_RADIUS_M
    x_ecl, y_ecl, z_ecl = _solve_orbit(0.0, 0.0, perihelion, radii, eccentricity, anomaly)
    return _ecliptic_to_equatorial(x_ecl, y_ecl, z_ecl, day_number)


def _moon_equatorial(day_number: float) -> tuple[float, float, float]:
    node = 125.1228 - 0.0529538083 * day_number
    periapsis = 318.0634 + 0.1643573223 * day_number
    anomaly = 115.3654 + 13.0649929509 * day_number
    x_ecl, y_ecl, z_ecl = _solve_orbit(node, 5.1454, periapsis, 60.2666, 0.054900, anomaly)
    longitude = math.atan2(y_ecl, x_ecl)
    latitude = math.atan2(z_ecl, math.hypot(x_ecl, y_ecl))
    distance = math.sqrt(x_ecl * x_ecl + y_ecl * y_ecl + z_ecl * z_ecl)
    sun_perihelion, _eccentricity, sun_anomaly = _sun_mean_elements(day_number)
    sun_anomaly_rad = math.radians(sun_anomaly % 360.0)
    moon_anomaly_rad = math.radians(anomaly % 360.0)
    elongation = math.radians((anomaly + periapsis + node - (sun_anomaly + sun_perihelion)) % 360.0)
    latitude_argument = math.radians((anomaly + periapsis) % 360.0)
    # Principal lunar perturbations, degrees. Terms below about 0.01 degree
    # are omitted. Distance terms are in equatorial radii of the series.
    longitude += math.radians(
        -1.274 * math.sin(moon_anomaly_rad - 2.0 * elongation)
        + 0.658 * math.sin(2.0 * elongation)
        - 0.186 * math.sin(sun_anomaly_rad)
        - 0.059 * math.sin(2.0 * moon_anomaly_rad - 2.0 * elongation)
        - 0.057 * math.sin(moon_anomaly_rad - 2.0 * elongation + sun_anomaly_rad)
        + 0.053 * math.sin(moon_anomaly_rad + 2.0 * elongation)
        + 0.046 * math.sin(2.0 * elongation - sun_anomaly_rad)
        + 0.041 * math.sin(moon_anomaly_rad - sun_anomaly_rad)
        - 0.035 * math.sin(elongation)
        - 0.031 * math.sin(moon_anomaly_rad + sun_anomaly_rad)
        - 0.015 * math.sin(2.0 * latitude_argument - 2.0 * elongation)
        + 0.011 * math.sin(moon_anomaly_rad - 4.0 * elongation)
    )
    latitude += math.radians(
        -0.173 * math.sin(latitude_argument - 2.0 * elongation)
        - 0.055 * math.sin(moon_anomaly_rad - latitude_argument - 2.0 * elongation)
        - 0.046 * math.sin(moon_anomaly_rad + latitude_argument - 2.0 * elongation)
        + 0.033 * math.sin(latitude_argument + 2.0 * elongation)
        + 0.017 * math.sin(2.0 * moon_anomaly_rad + latitude_argument)
    )
    distance += (
        -0.58 * math.cos(moon_anomaly_rad - 2.0 * elongation)
        - 0.46 * math.cos(2.0 * elongation)
    )
    if distance <= 1.0:
        raise EphemerisError("lunar distance collapsed inside the ellipsoid")
    x_ecl = distance * math.cos(longitude) * math.cos(latitude)
    y_ecl = distance * math.sin(longitude) * math.cos(latitude)
    z_ecl = distance * math.sin(latitude)
    return _ecliptic_to_equatorial(x_ecl, y_ecl, z_ecl, day_number)


def _topocentric(
    equatorial: tuple[float, float, float],
    site: SimulationSite,
    game_time_s: float,
) -> tuple[float, float, float]:
    axial, polar = observer_equatorial_radii(site.latitude_deg, site.observer_height_m)
    sidereal = math.radians(
        _wrap360(simulated_earth_rotation_deg(game_time_s) + site.longitude_deg)
    )
    return (
        equatorial[0] - axial * math.cos(sidereal),
        equatorial[1] - axial * math.sin(sidereal),
        equatorial[2] - polar,
    )


def _direction_from_equatorial(
    body: str,
    equatorial: tuple[float, float, float],
    site: SimulationSite,
    game_time_s: float,
) -> BodyDirection:
    topocentric = _topocentric(equatorial, site, game_time_s)
    distance = math.sqrt(topocentric[0] ** 2 + topocentric[1] ** 2 + topocentric[2] ** 2)
    if distance < 1e-9:
        raise EphemerisError("topocentric body distance vanished")
    right_ascension = math.atan2(topocentric[1], topocentric[0])
    declination = math.asin(max(-1.0, min(1.0, topocentric[2] / distance)))
    rotation = simulated_earth_rotation_deg(game_time_s)
    local_sidereal = math.radians(_wrap360(rotation + site.longitude_deg))
    hour_angle = local_sidereal - right_ascension
    latitude = math.radians(site.latitude_deg)
    cosine_dec = math.cos(declination)
    sine_dec = math.sin(declination)
    east = -cosine_dec * math.sin(hour_angle)
    north = sine_dec * math.cos(latitude) - cosine_dec * math.cos(hour_angle) * math.sin(latitude)
    up = math.sin(latitude) * sine_dec + math.cos(latitude) * cosine_dec * math.cos(hour_angle)
    direction = _unit(east, north, up)
    altitude = math.degrees(math.asin(max(-1.0, min(1.0, direction[2]))))
    azimuth = _wrap360(math.degrees(math.atan2(direction[0], direction[1])))
    return BodyDirection(
        body,
        game_time_s,
        SIMULATED_LABEL,
        True,
        math.degrees(right_ascension) % 360.0,
        math.degrees(declination),
        math.degrees(hour_angle) % 360.0,
        rotation,
        altitude,
        azimuth,
        direction,
        distance,
        AUTHORITY,
        DATUM,
        EPHEMERIS,
    )


class BodyDirection:
    """One simulated topocentric direction. Constructed only by this module."""

    def __init__(
        self,
        body: str,
        game_time_s: float,
        label: str,
        simulated: bool,
        right_ascension_deg: float,
        declination_deg: float,
        hour_angle_deg: float,
        earth_rotation_deg: float,
        altitude_deg: float,
        azimuth_deg: float,
        direction_enu: tuple[float, float, float],
        distance_equatorial_radii: float,
        authority: str,
        datum: str,
        ephemeris: str,
    ) -> None:
        require_simulated(label, simulated, authority=authority, datum=datum, ephemeris=ephemeris)
        if body not in ("sun", "moon"):
            raise EphemerisError("body must be sun or moon")
        if type(direction_enu) is not tuple or len(direction_enu) != 3:
            raise EphemerisError("direction must be an ENU triple")
        norm = math.sqrt(sum(component * component for component in direction_enu))
        if abs(norm - 1.0) > 1e-9:
            raise EphemerisError("ENU direction must be a unit vector")
        self.body = body
        self.game_time_s = float(game_time_s)
        self.label = label
        self.simulated = True
        self.right_ascension_deg = float(right_ascension_deg)
        self.declination_deg = float(declination_deg)
        self.hour_angle_deg = float(hour_angle_deg)
        self.earth_rotation_deg = float(earth_rotation_deg)
        self.altitude_deg = float(altitude_deg)
        self.azimuth_deg = float(azimuth_deg)
        self.direction_enu = tuple(float(component) for component in direction_enu)
        self.distance_equatorial_radii = float(distance_equatorial_radii)
        self.authority = authority
        self.datum = datum
        self.ephemeris = ephemeris

    def __eq__(self, other: object) -> bool:
        return isinstance(other, BodyDirection) and self.payload() == other.payload()

    def __hash__(self) -> int:
        return hash(canon_direction(self))

    def payload(self) -> dict:
        return {
            "body": self.body,
            "game_time_s": self.game_time_s,
            "label": self.label,
            "simulated": True,
            "right_ascension_deg": self.right_ascension_deg,
            "declination_deg": self.declination_deg,
            "hour_angle_deg": self.hour_angle_deg,
            "earth_rotation_deg": self.earth_rotation_deg,
            "altitude_deg": self.altitude_deg,
            "azimuth_deg": self.azimuth_deg,
            "direction_enu": list(self.direction_enu),
            "distance_equatorial_radii": self.distance_equatorial_radii,
            "authority": self.authority,
            "datum": self.datum,
            "ephemeris": self.ephemeris,
        }


def canon_direction(direction: BodyDirection) -> str:
    from .datum import canon

    return canon(direction.payload())


def solar_direction(site: SimulationSite, game_time_s: float) -> BodyDirection:
    """Topocentric sun in fictional local ENU at ``game_time_s``."""

    if not isinstance(site, SimulationSite):
        raise EphemerisError("sun direction requires a simulation site")
    when = require_game_time(game_time_s)
    return _direction_from_equatorial("sun", _sun_equatorial(simulation_day_number(when)), site, when)


def lunar_direction(site: SimulationSite, game_time_s: float) -> BodyDirection:
    """Topocentric moon in fictional local ENU at ``game_time_s``."""

    if not isinstance(site, SimulationSite):
        raise EphemerisError("moon direction requires a simulation site")
    when = require_game_time(game_time_s)
    return _direction_from_equatorial("moon", _moon_equatorial(simulation_day_number(when)), site, when)
