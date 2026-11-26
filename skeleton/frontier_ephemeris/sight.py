"""Sextant sight reduction on the game clock.

A natural-horizon sight applies three documented corrections to the
topocentric geometric altitude:

* index error, taken from the stored calibration epoch
* observer-height dip, the geometric horizon depression on the fictional
  ellipsoid scaled by ``HORIZON_REFRACTION_FACTOR`` (0.92)
* body refraction, the Bennett 1982 approximation

    R (arcmin) = 1.02 / tan(h + 10.3 / (h + 5.11))

  with ``h`` in degrees, then multiplied by ``(P / 101000) * (283 / (273.15 + T))``.
  ``P`` is pascals and ``T`` is degrees Celsius. Outside ``-1`` to ``89.9``
  degrees the approximation is undefined and the stand-in contributes 0.

A bubble sight uses the same index and refraction and adds the stored bubble
bias instead of horizon dip. The bias is a calibration number, not a hardware
read. Subtracting the applied terms recovers the geometric altitude, and the
same game time plus the same epoch reproduces the same reduction.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from skeleton.frontier_body.instrument_journal import SIMULATED_LABEL

from .datum import (
    AUTHORITY,
    DATUM,
    EPHEMERIS,
    HORIZON_REFRACTION_FACTOR,
    CalibrationEpoch,
    EphemerisError,
    SimulationSite,
    _real,
    canon,
    digest,
    install_epoch,
    local_gaussian_radius_m,
    require_game_time,
    require_simulated,
)
from .ephemeris import lunar_direction, solar_direction

_SCHEMA = "skeleton.frontier_ephemeris.sight_journal.v1"
_BODIES = ("sun", "moon")
_KINDS = ("natural_horizon", "bubble")


def bennett_refraction_deg(altitude_deg: float, pressure_pa: float, temperature_c: float) -> float:
    """Bennett 1982 refraction stand-in, in degrees.

    See the module docstring for the formula and the pressure/temperature
    scaling. This is an approximation evaluated at the body's apparent
    altitude, not a radiosonde reading.
    """

    altitude = _real(altitude_deg, "refraction altitude", -90.0, 90.0)
    pressure = _real(pressure_pa, "pressure", 1000.0, 120_000.0)
    temperature = _real(temperature_c, "air temperature", -80.0, 70.0)
    if altitude < -1.0 or altitude > 89.9:
        return 0.0
    argument = altitude + 10.3 / (altitude + 5.11)
    arcmin = 1.02 / math.tan(math.radians(argument))
    return (arcmin / 60.0) * (pressure / 101_000.0) * (283.0 / (273.15 + temperature))


def horizon_dip_deg(latitude_deg: float, height_m: float) -> float:
    """Horizon depression for an observer above the fictional ellipsoid.

    Geometric dip is ``acos(R / (R + h))`` with ``R`` the Gaussian radius of
    curvature at the simulation latitude. The result is multiplied by
    ``HORIZON_REFRACTION_FACTOR``. Height 0 has no dip.
    """

    height = _real(height_m, "observer height", 0.0, 10_000.0)
    if height == 0.0:
        return 0.0
    radius = local_gaussian_radius_m(latitude_deg)
    geometric = math.acos(radius / (radius + height))
    return math.degrees(geometric) * HORIZON_REFRACTION_FACTOR


def _body_direction(site: SimulationSite, game_time_s: float, body: str):
    if body == "sun":
        return solar_direction(site, game_time_s)
    if body == "moon":
        return lunar_direction(site, game_time_s)
    raise EphemerisError("body must be sun or moon")


@dataclass(frozen=True)
class SightReduction:
    game_time_s: float
    body: str
    kind: str
    geometric_altitude_deg: float
    azimuth_deg: float
    index_error_deg: float
    observer_height_m: float
    dip_deg: float
    refraction_deg: float
    bubble_bias_deg: float
    apparent_altitude_deg: float
    corrected_altitude_deg: float
    direction_enu: tuple[float, float, float]
    epoch_id: str
    label: str = SIMULATED_LABEL
    simulated: bool = True
    authority: str = AUTHORITY
    datum: str = DATUM
    ephemeris: str = EPHEMERIS

    def __post_init__(self) -> None:
        require_simulated(
            self.label, self.simulated, authority=self.authority, datum=self.datum, ephemeris=self.ephemeris,
        )
        if self.body not in _BODIES or self.kind not in _KINDS:
            raise EphemerisError("sight reduction body or kind is not simulated navigation")
        if type(self.direction_enu) is not tuple or len(self.direction_enu) != 3:
            raise EphemerisError("sight direction must be an ENU triple")

    def payload(self) -> dict:
        return {
            "game_time_s": self.game_time_s,
            "body": self.body,
            "kind": self.kind,
            "geometric_altitude_deg": self.geometric_altitude_deg,
            "azimuth_deg": self.azimuth_deg,
            "index_error_deg": self.index_error_deg,
            "observer_height_m": self.observer_height_m,
            "dip_deg": self.dip_deg,
            "refraction_deg": self.refraction_deg,
            "bubble_bias_deg": self.bubble_bias_deg,
            "apparent_altitude_deg": self.apparent_altitude_deg,
            "corrected_altitude_deg": self.corrected_altitude_deg,
            "direction_enu": list(self.direction_enu),
            "epoch_id": self.epoch_id,
            "label": self.label,
            "simulated": True,
            "authority": self.authority,
            "datum": self.datum,
            "ephemeris": self.ephemeris,
        }


def reduce_sight(
    site: SimulationSite,
    calibration: CalibrationEpoch,
    *,
    game_time_s: float,
    body: str,
    kind: str,
    pressure_pa: float,
    temperature_c: float,
) -> SightReduction:
    """Reduce one sextant sight. Pure in game time, site, and calibration."""

    if not isinstance(site, SimulationSite):
        raise EphemerisError("sight requires a simulation site")
    if not isinstance(calibration, CalibrationEpoch):
        raise EphemerisError("sight requires a calibration epoch")
    if kind not in _KINDS:
        raise EphemerisError("sight kind must be natural_horizon or bubble")
    when = require_game_time(game_time_s)
    direction = _body_direction(site, when, body)
    geometric = direction.altitude_deg
    refraction = 0.0
    for _ in range(2):
        refraction = bennett_refraction_deg(geometric + refraction, pressure_pa, temperature_c)
    dip = horizon_dip_deg(site.latitude_deg, site.observer_height_m) if kind == "natural_horizon" else 0.0
    bubble = calibration.bubble_bias_deg if kind == "bubble" else 0.0
    index = calibration.sextant_index_error_deg
    apparent = geometric + refraction + dip + index + bubble
    corrected = apparent - index - dip - refraction - bubble
    return SightReduction(
        when,
        body,
        kind,
        geometric,
        direction.azimuth_deg,
        index,
        site.observer_height_m,
        dip,
        refraction,
        bubble,
        apparent,
        corrected,
        direction.direction_enu,
        calibration.epoch_id,
    )


@dataclass(frozen=True)
class SightEntry:
    game_time_s: float
    body: str
    kind: str
    pressure_pa: float
    temperature_c: float
    calibration_epoch_id: str
    calibration_digest: str
    reduction: SightReduction
    prior_digest: str
    digest: str


@dataclass(frozen=True)
class SightJournal:
    site: SimulationSite
    calibration: CalibrationEpoch
    epochs: tuple[CalibrationEpoch, ...]
    origin_game_time_s: float
    entries: tuple[SightEntry, ...]
    header_digest: str


def _header_payload(journal: SightJournal) -> dict:
    return {
        "schema": _SCHEMA,
        "origin_game_time_s": journal.origin_game_time_s,
        "site": journal.site.payload(),
        "calibration": journal.epochs[0].payload(),
    }


def _with_header(journal: SightJournal) -> SightJournal:
    return SightJournal(
        journal.site,
        journal.calibration,
        journal.epochs,
        journal.origin_game_time_s,
        journal.entries,
        digest(_header_payload(journal)),
    )


def open_sight_journal(
    site: SimulationSite,
    calibration: CalibrationEpoch,
    *,
    origin_game_time_s: float,
) -> SightJournal:
    if not isinstance(site, SimulationSite):
        raise EphemerisError("sight journal requires a simulation site")
    if not isinstance(calibration, CalibrationEpoch):
        raise EphemerisError("sight journal requires a calibration epoch")
    origin = require_game_time(origin_game_time_s)
    return _with_header(SightJournal(site, calibration, (calibration,), origin, (), ""))


def _entry_payload(entry: SightEntry) -> dict:
    return {
        "game_time_s": entry.game_time_s,
        "body": entry.body,
        "kind": entry.kind,
        "pressure_pa": entry.pressure_pa,
        "temperature_c": entry.temperature_c,
        "calibration_epoch_id": entry.calibration_epoch_id,
        "calibration_digest": entry.calibration_digest,
        "reduction": entry.reduction.payload(),
        "prior_digest": entry.prior_digest,
    }


def append_sight(
    journal: SightJournal,
    *,
    game_time_s: float,
    body: str,
    kind: str,
    pressure_pa: float,
    temperature_c: float,
    calibration: CalibrationEpoch | None = None,
) -> SightJournal:
    """Append one reduced sight. A same-id calibration change is rejected."""

    if not isinstance(journal, SightJournal) or not journal.header_digest:
        raise EphemerisError("append requires an open sight journal")
    when = require_game_time(game_time_s)
    previous = journal.entries[-1].game_time_s if journal.entries else journal.origin_game_time_s
    if when < journal.origin_game_time_s or (journal.entries and when <= previous):
        raise EphemerisError("sights advance on game time")
    active, epochs = install_epoch(
        journal.calibration,
        journal.epochs,
        journal.calibration if calibration is None else calibration,
    )
    reduction = reduce_sight(
        journal.site,
        active,
        game_time_s=when,
        body=body,
        kind=kind,
        pressure_pa=pressure_pa,
        temperature_c=temperature_c,
    )
    prior = journal.entries[-1].digest if journal.entries else journal.header_digest
    provisional = SightEntry(
        when,
        body,
        kind,
        _real(pressure_pa, "pressure", 1000.0, 120_000.0),
        _real(temperature_c, "air temperature", -80.0, 70.0),
        active.epoch_id,
        active.content_digest(),
        reduction,
        prior,
        "",
    )
    sealed = SightEntry(
        provisional.game_time_s,
        provisional.body,
        provisional.kind,
        provisional.pressure_pa,
        provisional.temperature_c,
        provisional.calibration_epoch_id,
        provisional.calibration_digest,
        provisional.reduction,
        provisional.prior_digest,
        digest(_entry_payload(provisional)),
    )
    return SightJournal(
        journal.site,
        active,
        epochs,
        journal.origin_game_time_s,
        journal.entries + (sealed,),
        journal.header_digest,
    )


def replay_sight_journal(journal: SightJournal) -> tuple[SightReduction, ...]:
    """Recompute every reduction from stored game time and calibrations."""

    if not isinstance(journal, SightJournal) or not journal.epochs:
        raise EphemerisError("replay requires a sight journal")
    rebuilt = open_sight_journal(
        journal.site,
        journal.epochs[0],
        origin_game_time_s=journal.origin_game_time_s,
    )
    if rebuilt.header_digest != journal.header_digest:
        raise EphemerisError("replay header does not match the journal")
    known = {epoch.epoch_id: epoch for epoch in journal.epochs}
    for entry in journal.entries:
        if entry.calibration_epoch_id not in known:
            raise EphemerisError("replay is missing a calibration epoch")
        if known[entry.calibration_epoch_id].content_digest() != entry.calibration_digest:
            raise EphemerisError("replay calibration digest mismatch")
        rebuilt = append_sight(
            rebuilt,
            game_time_s=entry.game_time_s,
            body=entry.body,
            kind=entry.kind,
            pressure_pa=entry.pressure_pa,
            temperature_c=entry.temperature_c,
            calibration=known[entry.calibration_epoch_id],
        )
    if tuple(item.digest for item in rebuilt.entries) != tuple(item.digest for item in journal.entries):
        raise EphemerisError("replay diverged from the stored journal")
    readings = tuple(item.reduction for item in rebuilt.entries)
    if readings != tuple(item.reduction for item in journal.entries):
        raise EphemerisError("replay reductions diverged")
    return readings


def dump_sight_journal(journal: SightJournal) -> str:
    if not isinstance(journal, SightJournal):
        raise EphemerisError("sight dump requires a journal")
    if digest(_header_payload(journal)) != journal.header_digest:
        raise EphemerisError("sight journal header digest mismatch")
    entries = []
    for entry in journal.entries:
        payload = _entry_payload(entry)
        if digest(payload) != entry.digest:
            raise EphemerisError("sight entry digest mismatch")
        payload["digest"] = entry.digest
        entries.append(payload)
    body = {
        "schema": _SCHEMA,
        "header_digest": journal.header_digest,
        "origin_game_time_s": journal.origin_game_time_s,
        "site": journal.site.payload(),
        "epochs": [epoch.payload() for epoch in journal.epochs],
        "entries": entries,
    }
    return canon(body)


def _epoch_from_payload(payload: dict) -> CalibrationEpoch:
    try:
        return CalibrationEpoch(
            payload["epoch_id"],
            tuple(payload["gyro_bias_dps"]),
            payload["compass_declination_deg"],
            payload["sextant_index_error_deg"],
            payload["bubble_bias_deg"],
            payload["barometer_reference_pa"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EphemerisError("calibration epoch payload is incomplete") from exc


def load_sight_journal(payload: str) -> SightJournal:
    if type(payload) is not str or not payload:
        raise EphemerisError("sight journal payload must be text")
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise EphemerisError("sight journal payload is not JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema") != _SCHEMA:
        raise EphemerisError("sight journal schema mismatch")
    try:
        site_payload = raw["site"]
        site = SimulationSite(
            site_payload["latitude_deg"],
            site_payload["longitude_deg"],
            site_payload["observer_height_m"],
        )
        epochs = tuple(_epoch_from_payload(item) for item in raw["epochs"])
        journal = open_sight_journal(site, epochs[0], origin_game_time_s=raw["origin_game_time_s"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise EphemerisError("sight journal header is incomplete") from exc
    if journal.header_digest != raw.get("header_digest"):
        raise EphemerisError("sight journal header digest mismatch")
    known = {epoch.epoch_id: epoch for epoch in epochs}
    for item in raw["entries"]:
        if not isinstance(item, dict):
            raise EphemerisError("sight entry is not an object")
        try:
            epoch = known[item["calibration_epoch_id"]]
            if epoch.content_digest() != item["calibration_digest"]:
                raise EphemerisError("stored calibration digest mismatch")
            stored = dict(item)
            claimed = stored.pop("digest")
            if digest(stored) != claimed:
                raise EphemerisError("sight journal digest mismatch")
            journal = append_sight(
                journal,
                game_time_s=item["game_time_s"],
                body=item["body"],
                kind=item["kind"],
                pressure_pa=item["pressure_pa"],
                temperature_c=item["temperature_c"],
                calibration=epoch,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EphemerisError("sight entry is incomplete") from exc
        if journal.entries[-1].digest != item.get("digest"):
            raise EphemerisError("sight journal digest mismatch")
    if len(journal.epochs) != len(epochs):
        raise EphemerisError("sight journal epoch chain mismatch")
    return journal
