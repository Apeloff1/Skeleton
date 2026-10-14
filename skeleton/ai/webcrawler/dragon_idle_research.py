"""Full side-effect-free idle recommendation pipeline for the dragon.

Only catalog metadata and previously consented history/signals are processed.
A separate authorized media worker is needed for actual video digestion.
"""
from __future__ import annotations

from dataclasses import dataclass
from .dragon_interest_signals import InterestSignal, SignalPolicy, build_interest_profile
from .dragon_signal_discovery import SignalDiscoveryPolicy, rank_signal_aware_videos
from .dragon_video_catalog import CatalogPolicy, CatalogReceipt, ingest_video_catalog
from .dragon_video_history import DragonVideoHistory
from .dragon_idle_planner import IdleVideoPlanner
from .dragon_video_discovery import VideoProposal


@dataclass(frozen=True)
class ResearchConsent:
    history: bool = False
    signals: bool = False
    catalog: bool = False
    discovery: bool = False
    digestion: bool = False


@dataclass(frozen=True)
class ResearchReport:
    proposals: tuple[VideoProposal, ...]
    catalog_fingerprint: str
    interest_fingerprint: str
    rejected_catalog_items: int
    rejected_signals: int
    awaiting_approval: int
    ingestion_started: bool = False


def prepare_idle_video_research(
    *,
    owner: str,
    now: float,
    history: DragonVideoHistory,
    signals: tuple[InterestSignal, ...],
    catalog_rows: tuple[dict[str, object], ...],
    planner: IdleVideoPlanner,
    consent: ResearchConsent,
    catalog_policy: CatalogPolicy = CatalogPolicy(),
    signal_policy: SignalPolicy = SignalPolicy(),
    discovery_policy: SignalDiscoveryPolicy = SignalDiscoveryPolicy(),
) -> ResearchReport:
    if not owner or len(owner) > 128:
        raise ValueError("invalid research owner")
    if not (consent.history and consent.signals and consent.catalog and consent.discovery):
        raise PermissionError("history, signals, catalog and discovery must be authorized")
    catalog = ingest_video_catalog(catalog_rows, policy=catalog_policy, authorized=consent.catalog)
    profile = build_interest_profile(signals, now=now, policy=signal_policy)
    visits = history.recent(owner, limit=100)
    proposals = rank_signal_aware_videos(
        visits, catalog.candidates, profile, policy=discovery_policy,
        consent=consent.discovery,
    )
    pending = planner.propose(proposals, now=now, consent=consent.discovery)
    return ResearchReport(
        pending, catalog.fingerprint, profile.fingerprint,
        catalog.rejected, profile.rejected_signals, len(pending),
    )
