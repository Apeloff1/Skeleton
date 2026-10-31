"""Permission-bound live GNSS/GPS ingestion and independently surveyed fixes.

Privacy and authority:
- No OS APIs, background polling, location request, telemetry or persistence.
- Host owns device permission, authentic signed provider stream and retention.
- Receipts NEVER include raw latitude/longitude or a reversible digest thereof.
- Surveyed controls must be user-verified WGS84/ENU benchmarks, not AI guesses.
- Survey is an engineering reference, NOT a legal/cadastral position certificate.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, isfinite, radians, sin, sqrt
from typing import Sequence
from .game_frontier_instruments import NavigationEnvironment

EARTH_RADIUS_M = 6371008.8


class PositionError(ValueError):
    pass


def bounded(v: float, name: str, lo: float, hi: float) -> float:
    if type(v) not in (float, int) or not isfinite(v) or not lo <= v <= hi:
        raise PositionError(f"{name} must be finite in [{lo}, {hi}]")
    return float(v)


@dataclass(frozen=True)
class LocationConsent:
    session_id: str
    purpose: str
    scope: str
    granted_at_ms: int
    expires_at_ms: int
    granted_by_user: bool

    def __post_init__(self) -> None:
        if not self.session_id or len(self.session_id) > 128:
            raise PositionError("session id required")
        if self.purpose not in ("navigation", "survey_alignment", "game_geolocation"):
            raise PositionError("explicit scope-bound GPS purpose required")
        if self.scope != "foreground_precise_session":
            raise PositionError("cannot silently request persistent/background location")
        if type(self.granted_by_user) is not bool or not self.granted_by_user:
            raise PositionError("host user permission missing")
        if (type(self.granted_at_ms) is not int or
                type(self.expires_at_ms) is not int or
                not 0 <= self.granted_at_ms < self.expires_at_ms):
            raise PositionError("invalid location consent interval")


@dataclass(frozen=True)
class DeviceGPSFix:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    horizontal_accuracy_m: float
    vertical_accuracy_m: float
    timestamp_ms: int
    sequence: int
    source: str = "host_os_gnss"

    def __post_init__(self) -> None:
        bounded(self.latitude_deg, "latitude", -90, 90)
        bounded(self.longitude_deg, "longitude", -180, 180)
        bounded(self.altitude_m, "GNSS altitude", -1000, 20000)
        bounded(self.horizontal_accuracy_m, "horizontal accuracy", .01, 100000)
        bounded(self.vertical_accuracy_m, "vertical accuracy", .01, 100000)
        if self.source != "host_os_gnss":
            raise PositionError("untrusted GPS source; host must attest its stream")
        if type(self.timestamp_ms) is not int or self.timestamp_ms < 0:
            raise PositionError("valid UTC host timestamp required")
        if type(self.sequence) is not int or self.sequence < 0:
            raise PositionError("monotone host sequence required")


@dataclass(frozen=True)
class LivePosition:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    horizontal_accuracy_m: float
    timestamp_ms: int
    sequence: int
    status: str = "permission_bound_live_gps_unpersisted"

    def public_receipt(self) -> dict:
        return {
            "schema": "skeleton.game.live_position_receipt.v1",
            "source": "host_os_gnss",
            "precision": "foreground_device_gnss",
            "accuracy_m": self.horizontal_accuracy_m,
            "timestamp_ms": self.timestamp_ms,
            "sequence": self.sequence,
            "retains_coordinates": False,
            "authority": self.status,
        }


def _haversine(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    p1,p2=radians(a_lat),radians(b_lat)
    dp=p2-p1
    dl=radians(b_lon-a_lon)
    h=sin(dp/2)**2+cos(p1)*cos(p2)*sin(dl/2)**2
    return 2*EARTH_RADIUS_M*atan2(sqrt(max(0,h)),sqrt(max(0,1-h)))


def ingest_host_gps(fix: DeviceGPSFix, consent: LocationConsent, *,
                    now_ms: int, prior: DeviceGPSFix | None = None,
                    maximum_age_ms: int = 10000,
                    maximum_accuracy_m: float = 75.,
                    maximum_speed_mps: float = 140.) -> LivePosition:
    """Validate an OS-delivered fix; never acquire GPS from this function."""
    if type(now_ms) is not int or now_ms < 0:
        raise PositionError("host time required")
    if (now_ms < consent.granted_at_ms or now_ms > consent.expires_at_ms or
            not consent.granted_by_user):
        raise PositionError("live GPS consent expired/not yet active")
    if type(maximum_age_ms) is not int or not 0 <= maximum_age_ms <= 60000:
        raise PositionError("invalid max age")
    bounded(maximum_accuracy_m, "maximum accuracy", .01, 1000)
    bounded(maximum_speed_mps, "maximum speed", .01, 1000)
    if not consent.granted_at_ms <= fix.timestamp_ms <= min(now_ms,consent.expires_at_ms):
        raise PositionError("GPS timestamp outside permission lifetime/future")
    if now_ms-fix.timestamp_ms > maximum_age_ms:
        raise PositionError("stale GPS observation")
    if fix.horizontal_accuracy_m > maximum_accuracy_m:
        raise PositionError("GPS uncertainty beyond required quality")
    if prior:
        if fix.sequence <= prior.sequence or fix.timestamp_ms <= prior.timestamp_ms:
            raise PositionError("out of order/replayed GPS fix")
        dt=(fix.timestamp_ms-prior.timestamp_ms)/1000.
        distance=_haversine(fix.latitude_deg,fix.longitude_deg,
                            prior.latitude_deg,prior.longitude_deg)
        if distance > maximum_speed_mps*dt + 3*(
            fix.horizontal_accuracy_m+prior.horizontal_accuracy_m):
            raise PositionError("GPS jump inconsistent with motion and accuracy")
    return LivePosition(fix.latitude_deg,fix.longitude_deg,fix.altitude_m,
                        fix.horizontal_accuracy_m,fix.timestamp_ms,fix.sequence)


@dataclass(frozen=True)
class SurveyControl:
    landmark_id: str
    latitude_deg: float
    longitude_deg: float
    altitude_m: float
    verified: bool
    datum: str = "WGS84"

    def __post_init__(self) -> None:
        if not self.landmark_id or len(self.landmark_id) > 128:
            raise PositionError("control landmark identity required")
        bounded(self.latitude_deg,"control latitude",-90,90)
        bounded(self.longitude_deg,"control longitude",-180,180)
        bounded(self.altitude_m,"control altitude",-1000,20000)
        if self.datum != "WGS84" or type(self.verified) is not bool or not self.verified:
            raise PositionError("verified WGS84 surveyed control required")


@dataclass(frozen=True)
class SurveySighting:
    landmark_id: str
    azimuth_true_deg: float
    bearing_uncertainty_deg: float
    horizontal_range_m: float | None = None

    def __post_init__(self) -> None:
        if not self.landmark_id:
            raise PositionError("sighting landmark id required")
        bounded(self.azimuth_true_deg,"true azimuth",0,360)
        bounded(self.bearing_uncertainty_deg,"bearing uncertainty",.001,20)
        if self.horizontal_range_m is not None:
            bounded(self.horizontal_range_m,"horizontal range",.01,100000)


@dataclass(frozen=True)
class SurveyedFix:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float | None
    rms_cross_track_m: float
    geometry_angle_deg: float
    estimated_horizontal_uncertainty_m: float
    control_ids: tuple[str, ...]
    method: str = "wgs84_control_bearing_least_squares"
    authority: str = "candidate_control_survey_not_cadastral_certified"

    def public_receipt(self) -> dict:
        return {
            "schema":"skeleton.game.survey_receipt.v1",
            "method":self.method,
            "control_count":len(self.control_ids),
            "rms_cross_track_m":self.rms_cross_track_m,
            "geometry_angle_deg":self.geometry_angle_deg,
            "horizontal_uncertainty_m":self.estimated_horizontal_uncertainty_m,
            "retains_coordinates":False,
            "authority":self.authority,
        }


def solve_control_survey(controls: Sequence[SurveyControl],
                         sightings: Sequence[SurveySighting], *,
                         maximum_rms_m: float = 20.) -> SurveyedFix:
    """Weighted least-squares intersection of surveyed station bearings.

    Returns an engineering position in local tangent approximation <=50 km.
    Requires >=2 separated sighting directions; 3+ recommended for residual
    redundancy. Range (if present) is verified independently, not silently
    fitted to a separate authority. Altitude is intentionally unknown until
    a levelled/vertical-angle fix is separately provided.
    """
    bounded(maximum_rms_m,"survey residual tolerance",.01,10000)
    if not 2 <= len(sightings) <= 32 or not 2 <= len(controls) <= 64:
        raise PositionError("at least two controls/sightings required")
    by_id={p.landmark_id:p for p in controls}
    if len(by_id)!=len(controls) or len({s.landmark_id for s in sightings})!=len(sightings):
        raise PositionError("duplicate surveyed controls or sightings")
    if any(s.landmark_id not in by_id for s in sightings):
        raise PositionError("every sighting must reference a verified control")
    origin=by_id[sightings[0].landmark_id]
    if abs(origin.latitude_deg)>85:
        raise PositionError("polar geometry needs ECEF survey solver")
    rows=[]
    for sight in sightings:
        point=by_id[sight.landmark_id]
        dy=EARTH_RADIUS_M*radians(point.latitude_deg-origin.latitude_deg)
        dx=EARTH_RADIUS_M*cos(radians(origin.latitude_deg))*radians(
            point.longitude_deg-origin.longitude_deg)
        if hypot(dx,dy)>50000:
            raise PositionError("survey bounds exceed local ENU approximation")
        angle=radians(sight.azimuth_true_deg)
        ax,ay=cos(angle),-sin(angle)
        b=ax*dx+ay*dy
        # Bearing weights use angular variance; all rows are metres.
        weight=1/(radians(sight.bearing_uncertainty_deg)**2)
        rows.append((ax,ay,b,weight,dx,dy,sight))
    aa=sum(w*x*x for x,y,b,w,dx,dy,s in rows)
    ab=sum(w*x*y for x,y,b,w,dx,dy,s in rows)
    bb=sum(w*y*y for x,y,b,w,dx,dy,s in rows)
    ca=sum(w*x*b for x,y,b,w,dx,dy,s in rows)
    cb=sum(w*y*b for x,y,b,w,dx,dy,s in rows)
    determinant=aa*bb-ab*ab
    strength=determinant/max(1,aa*bb)
    if determinant<=0 or strength<.005:
        raise PositionError("near-parallel sight lines cannot resolve a position")
    x=(ca*bb-cb*ab)/determinant
    y=(cb*aa-ca*ab)/determinant
    residual=[ax*x+ay*y-b for ax,ay,b,w,dx,dy,s in rows]
    rms=sqrt(sum(v*v for v in residual)/len(residual))
    if rms>maximum_rms_m:
        raise PositionError("survey sightings fail independent residual checks")
    # Range is an independent measurement and must not contradict the fix.
    for ax,ay,b,w,dx,dy,sight in rows:
        if sight.horizontal_range_m is not None:
            expected=hypot(x-dx,y-dy)
            error=abs(expected-sight.horizontal_range_m)
            if error>max(maximum_rms_m,3*expected*radians(sight.bearing_uncertainty_deg)):
                raise PositionError("range/bearing surveyed control disagreement")
    minor=math_degrees_survey_strength(strength)
    # Bearing uncertainty scales with sight distance, so do not report zero
    # uncertainty for exactly intersecting synthetic bearings.
    intrinsic=max(hypot(x-dx,y-dy)*radians(s.bearing_uncertainty_deg)
                  for ax,ay,b,w,dx,dy,s in rows)
    uncertainty=max(rms,intrinsic/max(.1,sqrt(strength)))
    if uncertainty>max(100,maximum_rms_m*20):
        raise PositionError("survey geometry has excessive uncertainty")
    lat=origin.latitude_deg+degrees(y/EARTH_RADIUS_M)
    lon=origin.longitude_deg+degrees(x/(EARTH_RADIUS_M*cos(radians(origin.latitude_deg))))
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise PositionError("survey result exceeds WGS84 coordinate range")
    return SurveyedFix(lat,lon,None,rms,minor,uncertainty,
                       tuple(s.landmark_id for s in sightings))


def math_degrees_survey_strength(strength: float) -> float:
    """Effective line intersection angle, bounded 0..90 degrees."""
    from math import asin
    return degrees(asin(min(1,sqrt(max(0,strength)))))


def reconcile_live_and_survey(live: LivePosition, surveyed: SurveyedFix, *,
                              sigma_limit: float = 3.) -> dict:
    """Compare two independent fixes without persisting their coordinates."""
    bounded(sigma_limit,"consistency sigma threshold",1,10)
    distance=_haversine(live.latitude_deg,live.longitude_deg,
                        surveyed.latitude_deg,surveyed.longitude_deg)
    bound=sigma_limit*sqrt(live.horizontal_accuracy_m**2+
                          surveyed.estimated_horizontal_uncertainty_m**2)
    return {
        "schema":"skeleton.game.gps_survey_coherence.v1",
        "separation_m":distance,
        "tolerance_m":bound,
        "consistent":distance<=bound,
        "independent_sources":True,
        "coordinates_redacted":True,
        "authority":"advisory_only_no_location_persistence",
    }
