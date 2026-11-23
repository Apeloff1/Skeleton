"""Game-clock sun and moon sights, and the simulated calibration bench.

The sun check compares the package direction with an independent
Astronomical Almanac ecliptic series. A separation above the documented
arcminute bound fails. Every reading stays labeled simulated.
"""

from __future__ import annotations

import ast
import json
import math
import unittest
from pathlib import Path

from skeleton.frontier_ephemeris import (
    AUTHORITY,
    DATUM,
    EPHEMERIS,
    FACTORY_BAROMETER_PA,
    FICTIONAL_FLATTENING,
    SIMULATED_LABEL,
    SUN_SERIES_AGREEMENT_ARC_MIN,
    SUN_SERIES_WINDOW_DAYS,
    CalibrationEpoch,
    EphemerisError,
    InstrumentSample,
    SimulationSite,
    append_sight,
    bennett_refraction_deg,
    compare_instruments,
    dump_sight_journal,
    fictional_geocentric_latitude_deg,
    horizon_dip_deg,
    load_sight_journal,
    lunar_direction,
    open_calibration_bench,
    open_sight_journal,
    reduce_sight,
    replay_sight_journal,
    simulated_earth_rotation_deg,
    simulation_day_number,
    solar_direction,
    submit_calibration,
)


def _site(**overrides) -> SimulationSite:
    base = {"latitude_deg": 37.5, "longitude_deg": 18.0, "observer_height_m": 2.0}
    base.update(overrides)
    return SimulationSite(**base)


def _epoch(epoch_id="epoch-a", **overrides) -> CalibrationEpoch:
    base = {
        "epoch_id": epoch_id,
        "gyro_bias_dps": (0.1, -0.2, 0.2),
        "compass_declination_deg": 12.0,
        "sextant_index_error_deg": 0.4,
        "bubble_bias_deg": 0.3,
        "barometer_reference_pa": 100_000.0,
    }
    base.update(overrides)
    return CalibrationEpoch(**base)


def _almanac_sun_enu(latitude_deg: float, longitude_deg: float, game_time_s: float) -> tuple[float, float, float]:
    """Independent Astronomical Almanac sun, equinox of date.

    Mean longitude and mean anomaly are linear in days from arithmetic
    J2000.0. The equation of center keeps the two published sine terms.
    Earth rotation is the separate linear sidereal stand-in, not the
    Kepler mean longitude used by the package.
    """

    day = game_time_s / 86400.0
    mean_longitude = math.radians((280.460 + 0.9856474 * day) % 360.0)
    mean_anomaly = math.radians((357.528 + 0.9856003 * day) % 360.0)
    ecliptic = mean_longitude + math.radians(
        1.915 * math.sin(mean_anomaly) + 0.020 * math.sin(2.0 * mean_anomaly)
    )
    obliquity = math.radians(23.439 - 0.0000004 * day)
    right_ascension = math.atan2(math.cos(obliquity) * math.sin(ecliptic), math.cos(ecliptic))
    declination = math.asin(max(-1.0, min(1.0, math.sin(obliquity) * math.sin(ecliptic))))
    rotation = math.radians((280.46061837 + 360.98564736629 * day) % 360.0)
    hour_angle = rotation + math.radians(longitude_deg) - right_ascension
    latitude = math.radians(latitude_deg)
    cosine_dec = math.cos(declination)
    sine_dec = math.sin(declination)
    east = -cosine_dec * math.sin(hour_angle)
    north = sine_dec * math.cos(latitude) - cosine_dec * math.cos(hour_angle) * math.sin(latitude)
    up = math.sin(latitude) * sine_dec + math.cos(latitude) * cosine_dec * math.cos(hour_angle)
    length = math.sqrt(east * east + north * north + up * up)
    return (east / length, north / length, up / length)


def _separation_arcmin(left: tuple[float, float, float], right: tuple[float, float, float]) -> float:
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right))))
    return math.degrees(math.acos(dot)) * 60.0


def _signed_turn(before: float, after: float) -> float:
    delta = (after - before) % 360.0
    if delta > 180.0:
        delta -= 360.0
    return delta


class EphemerisAndBenchTests(unittest.TestCase):
    def test_sun_matches_independent_almanac_series(self):
        self.assertEqual(SUN_SERIES_AGREEMENT_ARC_MIN, 1.0)
        window = SUN_SERIES_WINDOW_DAYS * 86400.0
        times = (
            -window,
            -40.0 * 86400.0,
            0.0,
            3600.0,
            0.5 * 86400.0,
            10.0 * 86400.0,
            100.0 * 86400.0,
            365.25 * 86400.0,
            10.0 * 365.25 * 86400.0,
            window,
        )
        worst = 0.0
        for game_time_s in times:
            self.assertLessEqual(abs(game_time_s) / 86400.0, SUN_SERIES_WINDOW_DAYS)
            for latitude in (-66.0, -23.4, 0.0, 37.5, 71.0):
                for longitude in (-150.0, 0.0, 18.0, 139.0):
                    site = SimulationSite(latitude, longitude, 12.0)
                    package = solar_direction(site, game_time_s)
                    self.assertEqual(package.label, SIMULATED_LABEL)
                    self.assertTrue(package.simulated)
                    self.assertEqual(package.datum, DATUM)
                    self.assertEqual(package.authority, AUTHORITY)
                    self.assertIn("simulated", package.ephemeris)
                    independent = _almanac_sun_enu(latitude, longitude, game_time_s)
                    worst = max(worst, _separation_arcmin(package.direction_enu, independent))
        self.assertLessEqual(worst, SUN_SERIES_AGREEMENT_ARC_MIN)
        self.assertGreater(worst, 0.05)

    def test_earth_rotation_follows_game_time_only(self):
        self.assertEqual(simulation_day_number(0.0), 1.5)
        origin = simulated_earth_rotation_deg(0.0)
        solar_day = simulated_earth_rotation_deg(86400.0)
        sidereal_day = simulated_earth_rotation_deg(86164.0905)
        self.assertAlmostEqual(_signed_turn(origin, solar_day), 0.985647, places=4)
        self.assertAlmostEqual(_signed_turn(origin, sidereal_day), 0.0, places=4)
        self.assertEqual(
            solar_direction(_site(longitude_deg=0.0), 1000.0).earth_rotation_deg,
            solar_direction(_site(longitude_deg=15.0), 1000.0).earth_rotation_deg,
        )
        east = solar_direction(_site(longitude_deg=0.0), 1000.0)
        shifted = solar_direction(_site(longitude_deg=15.0), 1000.0)
        self.assertAlmostEqual(
            _signed_turn(east.hour_angle_deg, shifted.hour_angle_deg),
            15.0,
            places=2,
        )
        self.assertGreater(
            _separation_arcmin(east.direction_enu, shifted.direction_enu),
            10.0 * 60.0,
        )
        polar = solar_direction(SimulationSite(90.0, 0.0, 0.0), 0.0)
        self.assertAlmostEqual(sum(component * component for component in polar.direction_enu), 1.0, places=9)

    def test_moon_and_ellipsoid_are_simulated_geometry(self):
        site = _site()
        sun = solar_direction(site, 86400.0)
        moon = lunar_direction(site, 86400.0)
        self.assertNotEqual(sun.direction_enu, moon.direction_enu)
        self.assertGreater(moon.distance_equatorial_radii, 50.0)
        self.assertLess(moon.distance_equatorial_radii, 70.0)
        self.assertGreater(sun.distance_equatorial_radii, 22_000.0)
        self.assertLess(sun.distance_equatorial_radii, 25_000.0)
        self.assertEqual(moon.label, SIMULATED_LABEL)
        self.assertEqual(moon.datum, "fictional_local_enu")
        low = lunar_direction(_site(observer_height_m=0.0), 86400.0)
        high = lunar_direction(_site(observer_height_m=5_000.0), 86400.0)
        self.assertNotEqual(low.direction_enu, high.direction_enu)
        expected = math.degrees(math.atan((1.0 - FICTIONAL_FLATTENING) ** 2 * math.tan(math.radians(45.0))))
        self.assertAlmostEqual(fictional_geocentric_latitude_deg(45.0), expected, places=9)
        self.assertNotAlmostEqual(fictional_geocentric_latitude_deg(45.0), 45.0, places=3)
        self.assertEqual(horizon_dip_deg(45.0, 0.0), 0.0)
        self.assertGreater(horizon_dip_deg(45.0, 25.0), horizon_dip_deg(45.0, 4.0))
        self.assertNotAlmostEqual(horizon_dip_deg(0.0, 100.0), horizon_dip_deg(80.0, 100.0), places=3)
        with self.assertRaises(EphemerisError):
            SimulationSite(latitude_deg=90.1, longitude_deg=0.0, observer_height_m=0.0)
        with self.assertRaises(EphemerisError):
            solar_direction(_site(), math.nan)

    def test_refraction_and_sight_corrections_replay(self):
        low = bennett_refraction_deg(5.0, 101_325.0, 15.0)
        high = bennett_refraction_deg(70.0, 101_325.0, 15.0)
        self.assertGreater(low, high)
        self.assertGreater(low, 0.0)
        self.assertLess(low, 1.0)
        self.assertAlmostEqual(
            bennett_refraction_deg(20.0, 101_000.0, 15.0) / bennett_refraction_deg(20.0, 50_500.0, 15.0),
            2.0,
            places=6,
        )
        self.assertGreater(
            bennett_refraction_deg(20.0, 101_325.0, -20.0),
            bennett_refraction_deg(20.0, 101_325.0, 30.0),
        )
        plain = _epoch(sextant_index_error_deg=0.0, bubble_bias_deg=0.0)
        indexed = _epoch(sextant_index_error_deg=0.4, bubble_bias_deg=0.0)
        biased = _epoch(sextant_index_error_deg=0.0, bubble_bias_deg=0.3)
        kwargs = {"game_time_s": 8_000.0, "body": "sun", "pressure_pa": 101_000.0, "temperature_c": 15.0}
        natural = reduce_sight(_site(), plain, kind="natural_horizon", **kwargs)
        shifted = reduce_sight(_site(), indexed, kind="natural_horizon", **kwargs)
        bubble = reduce_sight(_site(), biased, kind="bubble", **kwargs)
        natural_with_bias = reduce_sight(_site(), biased, kind="natural_horizon", **kwargs)
        self.assertEqual(natural.label, SIMULATED_LABEL)
        self.assertTrue(natural.simulated)
        self.assertIn("simulated", natural.ephemeris)
        self.assertAlmostEqual(shifted.apparent_altitude_deg - natural.apparent_altitude_deg, 0.4, places=9)
        self.assertAlmostEqual(shifted.corrected_altitude_deg, natural.corrected_altitude_deg, places=9)
        self.assertAlmostEqual(natural.corrected_altitude_deg, natural.geometric_altitude_deg, places=9)
        self.assertAlmostEqual(bubble.corrected_altitude_deg, natural.corrected_altitude_deg, places=9)
        self.assertAlmostEqual(bubble.apparent_altitude_deg - natural.geometric_altitude_deg, 0.3 + bubble.refraction_deg, places=9)
        self.assertEqual(natural_with_bias.apparent_altitude_deg, natural.apparent_altitude_deg)
        self.assertEqual(natural.bubble_bias_deg, 0.0)
        self.assertEqual(bubble.dip_deg, 0.0)
        self.assertGreater(natural.dip_deg, 0.0)
        tall = reduce_sight(_site(observer_height_m=100.0), plain, kind="natural_horizon", **kwargs)
        self.assertGreater(tall.dip_deg, natural.dip_deg)
        again = reduce_sight(_site(), indexed, kind="natural_horizon", **kwargs)
        self.assertEqual(again, shifted)

    def test_same_game_time_and_calibration_replay(self):
        epoch = _epoch()
        journal = open_sight_journal(_site(), epoch, origin_game_time_s=0.0)
        journal = append_sight(
            journal,
            game_time_s=1_000.0,
            body="sun",
            kind="natural_horizon",
            pressure_pa=100_000.0,
            temperature_c=15.0,
        )
        revised = _epoch("epoch-b", sextant_index_error_deg=-0.2, bubble_bias_deg=-0.4)
        journal = append_sight(
            journal,
            game_time_s=5_000.0,
            body="moon",
            kind="bubble",
            pressure_pa=98_000.0,
            temperature_c=5.0,
            calibration=revised,
        )
        replayed = replay_sight_journal(journal)
        self.assertEqual(replayed, tuple(entry.reduction for entry in journal.entries))
        self.assertEqual(replay_sight_journal(journal), replayed)
        direct = reduce_sight(
            _site(),
            epoch,
            game_time_s=1_000.0,
            body="sun",
            kind="natural_horizon",
            pressure_pa=100_000.0,
            temperature_c=15.0,
        )
        self.assertEqual(replayed[0], direct)
        self.assertNotEqual(replayed[0].apparent_altitude_deg, replayed[1].apparent_altitude_deg)
        stored_epochs = journal.epochs
        stored_active = journal.calibration
        with self.assertRaises(EphemerisError):
            append_sight(
                journal,
                game_time_s=6_000.0,
                body="sun",
                kind="natural_horizon",
                pressure_pa=100_000.0,
                temperature_c=15.0,
                calibration=_epoch(sextant_index_error_deg=0.9),
            )
        self.assertIs(journal.epochs, stored_epochs)
        self.assertIs(journal.calibration, stored_active)
        restored = load_sight_journal(dump_sight_journal(journal))
        self.assertEqual(replay_sight_journal(restored), replayed)
        payload = json.loads(dump_sight_journal(journal))
        payload["entries"][0]["reduction"]["apparent_altitude_deg"] = 1.0
        with self.assertRaises(EphemerisError):
            load_sight_journal(json.dumps(payload))

    def test_bench_returns_both_columns_and_rejects_a_bad_adjustment(self):
        epoch = _epoch()
        bench = open_calibration_bench(epoch)
        pair = compare_instruments(
            bench,
            site=_site(),
            game_time_s=1_000.0,
            true_heading_deg=100.0,
            angular_rate_dps=(0.0, 0.0, 1.0),
            yaw_deg=10.0,
            pitch_deg=0.0,
            roll_deg=0.0,
            delta_s=5.0,
            observed_pressure_pa=95_000.0,
            air_temperature_c=15.0,
        )
        self.assertEqual(pair.label, SIMULATED_LABEL)
        self.assertTrue(pair.simulated)
        self.assertEqual(pair.datum, DATUM)
        self.assertEqual(pair.ephemeris, EPHEMERIS)
        self.assertTrue(pair.uncorrected.simulated)
        self.assertTrue(pair.corrected.simulated)
        self.assertEqual(pair.uncorrected.label, SIMULATED_LABEL)
        self.assertEqual(pair.corrected.label, SIMULATED_LABEL)
        self.assertAlmostEqual(pair.uncorrected.gyro_yaw_deg - pair.corrected.gyro_yaw_deg, 1.0, places=6)
        self.assertAlmostEqual(pair.uncorrected.compass_heading_deg, 88.0, places=6)
        self.assertAlmostEqual(pair.corrected.compass_heading_deg, 100.0, places=6)
        self.assertAlmostEqual(
            pair.uncorrected.sextant_altitude_deg - pair.corrected.sextant_altitude_deg,
            0.4,
            delta=0.2,
        )
        self.assertGreater(pair.uncorrected.bubble_altitude_deg, pair.corrected.bubble_altitude_deg)
        self.assertNotAlmostEqual(
            pair.uncorrected.barometric_altitude_m,
            pair.corrected.barometric_altitude_m,
            places=3,
        )
        neutral = open_calibration_bench(_epoch(
            gyro_bias_dps=(0.0, 0.0, 0.0),
            compass_declination_deg=0.0,
            sextant_index_error_deg=0.0,
            bubble_bias_deg=0.0,
            barometer_reference_pa=FACTORY_BAROMETER_PA,
        ))
        level = compare_instruments(
            neutral,
            site=_site(observer_height_m=0.0),
            game_time_s=1_000.0,
            true_heading_deg=40.0,
            angular_rate_dps=(0.0, 0.0, 0.0),
            yaw_deg=4.0,
            pitch_deg=1.0,
            roll_deg=-2.0,
            delta_s=2.0,
            observed_pressure_pa=FACTORY_BAROMETER_PA,
            air_temperature_c=15.0,
            body="moon",
        )
        self.assertAlmostEqual(level.uncorrected.gyro_yaw_deg, level.corrected.gyro_yaw_deg, places=9)
        self.assertAlmostEqual(level.uncorrected.compass_heading_deg, level.corrected.compass_heading_deg, places=9)
        self.assertAlmostEqual(level.uncorrected.barometric_altitude_m, 0.0, places=9)
        self.assertAlmostEqual(level.corrected.barometric_altitude_m, 0.0, places=9)
        self.assertNotAlmostEqual(
            level.uncorrected.sextant_altitude_deg,
            level.corrected.sextant_altitude_deg,
            places=4,
        )
        stored_epochs = bench.epochs
        stored_active = bench.active
        with self.assertRaises(EphemerisError):
            submit_calibration(
                bench,
                epoch_id=epoch.epoch_id,
                gyro_bias_dps=epoch.gyro_bias_dps,
                compass_declination_deg=epoch.compass_declination_deg,
                sextant_index_error_deg=0.9,
                bubble_bias_deg=epoch.bubble_bias_deg,
                barometer_reference_pa=epoch.barometer_reference_pa,
            )
        with self.assertRaises(EphemerisError):
            submit_calibration(
                bench,
                epoch_id="epoch-out",
                gyro_bias_dps=(0.0, 0.0, 0.0),
                compass_declination_deg=0.0,
                sextant_index_error_deg=0.0,
                bubble_bias_deg=10.1,
                barometer_reference_pa=FACTORY_BAROMETER_PA,
            )
        with self.assertRaises(EphemerisError):
            submit_calibration(
                bench,
                epoch_id="epoch-nan",
                gyro_bias_dps=(0.0, 0.0, math.nan),
                compass_declination_deg=0.0,
                sextant_index_error_deg=0.0,
                bubble_bias_deg=0.0,
                barometer_reference_pa=FACTORY_BAROMETER_PA,
            )
        self.assertIs(bench.epochs, stored_epochs)
        self.assertIs(bench.active, stored_active)
        self.assertEqual(len(bench.epochs), 1)
        updated = submit_calibration(
            bench,
            epoch_id="epoch-b",
            gyro_bias_dps=(0.0, 0.0, -0.5),
            compass_declination_deg=-8.0,
            sextant_index_error_deg=-0.25,
            bubble_bias_deg=0.0,
            barometer_reference_pa=102_000.0,
        )
        self.assertIs(bench.active, stored_active)
        self.assertEqual(updated.active.epoch_id, "epoch-b")
        self.assertEqual(len(updated.epochs), 2)
        self.assertEqual(submit_calibration(
            updated,
            epoch_id="epoch-b",
            gyro_bias_dps=(0.0, 0.0, -0.5),
            compass_declination_deg=-8.0,
            sextant_index_error_deg=-0.25,
            bubble_bias_deg=0.0,
            barometer_reference_pa=102_000.0,
        ), updated)
        with self.assertRaises(EphemerisError):
            InstrumentSample(0, 0, 0, 0, 0, 0, 0, label="device-fix", simulated=False)

    def test_package_source_stays_on_the_game_clock(self):
        root = Path(__file__).resolve().parents[1] / "skeleton" / "frontier_ephemeris"
        sources = sorted(root.glob("*.py"))
        self.assertGreaterEqual(len(sources), 4)
        forbidden_roots = {"time", "datetime", "os", "gps", "geolocation", "random"}
        for path in sources:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("NotImplemented", source)
            self.assertNotIn("time.time", source)
            self.assertNotIn("datetime.now", source)
            self.assertNotIn("random.", source)
            self.assertNotIn("wgs84", source.lower())
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    imported = [(node.module or "").split(".")[0]]
                else:
                    continue
                for name in imported:
                    self.assertNotIn(name, forbidden_roots)


if __name__ == "__main__":
    unittest.main()
