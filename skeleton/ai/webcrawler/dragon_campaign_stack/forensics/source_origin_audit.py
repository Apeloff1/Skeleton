"""Canonical URL and observed origin hygiene for selected captured sources.

Only origin metadata and fixed diagnostic codes can leave this inspection.
It never emits a full path, query, credential, URL fragment, username or
untrusted captured page content. Redirect analysis is a review lead only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import parse_qsl, urlsplit

from ...operations import CrawlRun
from ..contracts import CampaignMandate, digest, ensure_snapshot_scope, integer
from .frames import FrameSet


_TRACKER_KEYS = frozenset(("fbclid", "gclid", "msclkid", "yclid", "mc_cid",
                           "mc_eid", "igshid", "utm_source", "utm_medium",
                           "utm_campaign", "utm_term", "utm_content"))
_SENSITIVE_KEYS = frozenset(("token", "auth", "api_key", "key", "password",
                             "passwd", "secret", "access_token",
                             "authorization", "session", "code"))


@dataclass(frozen=True)
class OriginFinding:
    source_id: str
    host: str
    scheme: str
    requested_host: str
    requested_scheme: str
    canonical_query_parameter_count: int
    tracking_parameter_count: int
    sensitive_parameter_name_count: int
    observed_redirect: bool
    external_host_handoff: bool
    flags: tuple[str, ...]
    raw_url_exported: bool = False
    remote_redirect_validated: bool = False


@dataclass(frozen=True)
class SourceOriginAudit:
    mandate_digest: str
    frame_set_digest: str
    source_snapshot_digest: str
    findings: tuple[OriginFinding, ...]
    redirected_sources: tuple[str, ...]
    review_source_ids: tuple[str, ...]
    risky_query_parameter_sources: tuple[str, ...]
    audit_digest: str
    source_url_paths_exported: bool = False
    destination_network_verified: bool = False


def audit_selected_origins(
    mandate: CampaignMandate, snapshot: dict[str, object],
    frames: FrameSet, *, now: float, authorized: bool,
    max_query_parameters: int = 64,
) -> SourceOriginAudit:
    mandate.admit(now=now, authorized=authorized)
    ensure_snapshot_scope(snapshot, mandate)
    integer(max_query_parameters, "origin query parameter cap", 0, 64)
    if not isinstance(frames, FrameSet):
        raise TypeError("selected source frames required")
    run = CrawlRun.from_snapshot(snapshot).snapshot()
    if frames.mandate_digest != mandate.fingerprint or (
        frames.snapshot_digest != run["snapshot_digest"]
    ):
        raise PermissionError("source origin inspection is stale or foreign")
    ids = {frame.anchor.source_id for frame in frames.frames}
    if len(ids) > 32:
        raise ValueError("origin source capacity exceeded")
    rows, redirected, held, risky = [], [], [], []
    for source_id in sorted(ids):
        source = run["sources"].get(source_id)
        if not isinstance(source, dict):
            raise PermissionError("canonical source missing for origin review")
        url = source["canonical_url"]
        fetched = source.get("fetched_url")
        if not isinstance(fetched, str):
            raise PermissionError("missing observed fetch URL")
        canonical, requested = urlsplit(url), urlsplit(fetched)
        if (canonical.scheme not in ("https", "http")
                or not canonical.hostname
                or canonical.hostname not in mandate.scope.allowed_hosts
                or not requested.hostname or not requested.scheme
                or canonical.username or canonical.password
                or requested.username or requested.password):
            raise PermissionError("unsafe canonical or observed source origin")
        params = parse_qsl(canonical.query, keep_blank_values=True,
                           max_num_fields=max_query_parameters+1)
        if len(params) > max_query_parameters:
            raise ValueError("query parameter count exceeds inspection bound")
        keys = [key.casefold() for key, _ in params]
        trackers = sum(k in _TRACKER_KEYS or k.startswith("utm_") for k in keys)
        secrets = sum(k in _SENSITIVE_KEYS for k in keys)
        changed = url != fetched
        cross_host = canonical.hostname != requested.hostname
        flags = []
        if changed:
            flags.append("observed_url_differs_from_canonical")
            redirected.append(source_id)
        if cross_host:
            flags.append("observed_origin_host_handoff")
        if secrets:
            flags.append("possible_sensitive_query_parameter_name")
            risky.append(source_id)
        if trackers:
            flags.append("tracking_parameter_review")
        if canonical.scheme == "http":
            flags.append("plaintext_canonical_scheme")
        if requested.scheme == "http":
            flags.append("plaintext_fetch_scheme")
        if flags:
            held.append(source_id)
        rows.append(OriginFinding(
            source_id, canonical.hostname, canonical.scheme,
            requested.hostname, requested.scheme, len(params),
            trackers, secrets, changed, cross_host, tuple(sorted(flags)),
        ))
    payload = {"mandate": mandate.fingerprint, "frames": frames.frame_set_digest,
               "snapshot": run["snapshot_digest"],
               "origins": [asdict(row) for row in rows],
               "max_params": max_query_parameters}
    return SourceOriginAudit(
        mandate.fingerprint, frames.frame_set_digest,
        run["snapshot_digest"], tuple(rows),
        tuple(redirected), tuple(held), tuple(risky), digest(payload),
    )
