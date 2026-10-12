"""Explicit opt-in pilot of one independently permissioned Dragon source.

No daemon, automatic campaign, or network discovery. A trusted host runtime
supplies actual idleness/consent/telemetry and a socket-bound HTTP transport.
The controller checks a separately signed, revocable reference-capture grant
before requesting a global slot, then delegates *all* requests and retention
to the canonical governed worker which re-verifies that grant each time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from skeleton.ai.webcrawler.dragon_resource_session import HardwareSample
from skeleton.ai.webcrawler.http import SafeHttpFetcher

from .dragon_research_supervisor import DragonResearchSupervisor
from .dragon_source_permission_authority import (
    DragonSourcePermissionAuthority, SourceCaptureGrant,
)
from .dragon_technical_source_acquisition import (
    SourceAcquisitionResult, acquire_canonical_technical_article, _epoch,
)
from .dragon_technical_source_captures import DragonSourceCaptures


@dataclass(frozen=True,slots=True)
class SourcePilotPreview:
    owner: str
    source_id: str
    grant_digest: str
    scheduled: bool
    source_ready: bool
    network_requests: int=0
    execution_authorized: bool=False
    model_training_authorized: bool=False


class DragonResearchPilot:
    """Mandatory permission/grant boundary for *pilot-mode* source execution."""

    def __init__(self,supervisor:DragonResearchSupervisor,
                 authority:DragonSourcePermissionAuthority):
        if not isinstance(supervisor,DragonResearchSupervisor):
            raise TypeError("existing Dragon resource supervisor required")
        if (not isinstance(authority,DragonSourcePermissionAuthority)
            or supervisor.operations.captures is not authority.captures):
            raise TypeError("same canonical reviewed source custody required")
        self.supervisor=supervisor
        self.authority=authority
        self.captures=authority.captures

    def preview(self,grant:SourceCaptureGrant,*,now:int,
                authorized:bool)->SourcePilotPreview:
        if not isinstance(grant,SourceCaptureGrant):
            raise PermissionError("typed owner-bound reference permit required")
        permitted=self.authority.verify(
            grant,owner=grant.owner,source_id=grant.source_id,
            now=now,authorized=authorized)
        ready=self.supervisor.operations.ready_candidates(
            grant.owner,now=now,authorized=True,limit=64)
        return SourcePilotPreview(
            grant.owner,grant.source_id,permitted,
            scheduled=grant.source_id in ready,
            source_ready=grant.source_id in ready,
        )

    def execute(self,grant:SourceCaptureGrant,*,fetcher:SafeHttpFetcher,
                sample_provider:Callable[[],HardwareSample],
                consent_provider:Callable[[],dict],
                idle_since_provider:Callable[[],str],
                at_provider:Callable[[],str],
                clock:Callable[[],float],sleep:Callable[[float],None],
                capture_id:str,authorized:bool,trusted_worker:bool,
                live_network_approved:bool,
                reference_storage_permitted:bool) -> SourceAcquisitionResult | None:
        """Returns None if no safe idle slot; never manufactures a site grant.

        The caller must explicitly authorize this pilot at each invocation.
        Successful entry *can perform real HTTP* through the supplied socket-
        bound transport; no background loop is created here.
        """
        if (authorized is not True or trusted_worker is not True
            or live_network_approved is not True
            or reference_storage_permitted is not True):
            raise PermissionError("explicit trusted, permitted live pilot required")
        if not isinstance(fetcher,SafeHttpFetcher) or not fetcher.bind_dns_to_socket:
            raise PermissionError("public socket-bound HTTP transport required")
        if not all(callable(f) for f in (
            sample_provider,consent_provider,idle_since_provider,at_provider,
            clock,sleep)):
            raise ValueError("trusted live consent/telemetry callbacks required")
        if not isinstance(grant,SourceCaptureGrant):
            raise PermissionError("real signed source permit required")
        at=at_provider()
        now=_epoch(at)
        self.authority.verify(
            grant,owner=grant.owner,source_id=grant.source_id,
            now=now,authorized=True)
        flags=consent_provider()
        if (not isinstance(flags,dict)
            or set(flags)!={"consented","article_consent","video_consent","updates_consent"}
            or flags["consented"] is not True
            or flags["article_consent"] is not True):
            raise PermissionError("current article pilot consent missing")
        sample=sample_provider()
        idle_since=idle_since_provider()
        now_seconds=clock()
        preview=self.supervisor.reserve_next(
            grant.owner,sample=sample,at=at,
            idle_since=idle_since,now_seconds=now_seconds,
            authorized=True,trusted_worker=True,
            consented=True,article_consent=True,
            eligible_source_id=grant.source_id)
        if preview.ticket is None:
            return None
        # This method owns the ONLY ticket created above. The synchronous
        # acquisition finalizer stops the worker even if the permit expires,
        # the site revokes permission, or the foreground interrupts.
        return acquire_canonical_technical_article(
            self.supervisor.admission,self.captures,preview.ticket,
            fetcher=fetcher,sample_provider=sample_provider,
            consent_provider=consent_provider,
            idle_since_provider=idle_since_provider,
            at_provider=at_provider,clock=clock,sleep=sleep,
            capture_id=capture_id,authorized=True,trusted_worker=True,
            reference_storage_permitted=True,
            operations=self.supervisor.operations,
            source_authority=self.authority,source_grant=grant,
        )
