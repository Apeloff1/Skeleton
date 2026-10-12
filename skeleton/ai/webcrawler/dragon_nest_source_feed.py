"""Bridge canonical game-source research leads into Dragon's three idle hatchlings.

This is an OFFLINE planning adapter. Importing an atlas source, having an
approved revision, or receiving a suggested publication timestamp cannot
authorize a fetch, a video download, model training, or hatchling growth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs, _auth
from skeleton.ai.game_builder.dragon_technical_source_atlas import CATALOG, DragonTechnicalSources
from skeleton.ai.game_builder.dragon_source_catalog import canonical_source_url
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore, _integer

from .dragon_nest_store import DragonNestStore
from .dragon_nest_progression import _instant
from .dragon_nest_research_scheduler import (
    IdleResearchPlan, IdleResearchPolicy, ResearchLead, plan_idle_research,
)
from .dragon_resource_session import HardwareSample


@dataclass(frozen=True, slots=True)
class SourceFedNestPlan:
    """Read-only, owner-scoped operator preview of actual research intents."""
    plan: IdleResearchPlan
    curated_article_leads: int
    registered_video_leads: int
    reviewed_revision_leads: int
    rejected_external_leads: int
    duplicate_source_leads: int
    network_requests: int = 0
    queue_modified: bool = False
    memory_promotion_authorized: bool = False


class DragonNestSourceFeed:
    """Unify curated articles, registered videos and reviewed source deltas.

    The supplied leads are hints from independent discovery workers. Each
    external lead must resolve to the canonical owner-scoped policy queue.
    Only genuinely changed, current approved library revisions can be
    suggested for the update lane. A publication hint remains unverified.
    """

    def __init__(self, almanacs: DragonAlmanacs,
                 atlas: DragonTechnicalSources, nest: DragonNestStore):
        if not isinstance(almanacs, DragonAlmanacs):
            raise TypeError("canonical DragonAlmanacs required")
        if not isinstance(atlas, DragonTechnicalSources) or atlas.a is not almanacs:
            raise TypeError("technical atlas must share canonical owner")
        if not isinstance(nest, DragonNestStore):
            raise TypeError("signed durable Dragon nest required")
        self.almanacs = almanacs
        self.atlas = atlas
        self.nest = nest
        self.library: ReviewedKnowledgeStore = almanacs.library
        self.db = almanacs.db

    def _registered(self, owner: str, lead: ResearchLead) -> bool:
        """Verify metadata + queue identity without interpreting rights."""
        url = canonical_source_url(lead.url)
        if url != lead.url or (
            "source-" + sha256(url.encode("utf-8")).hexdigest()
        ) != lead.source_id:
            raise ValueError("source lead is not its canonical acquisition identity")
        row = self.db.execute(
            """SELECT s.body,s.digest,j.stage,j.state,j.input_digest
               FROM dragon_almanac_sources s
               JOIN dragon_almanac_jobs j ON j.owner=s.owner AND j.source=s.source
               WHERE s.owner=? AND s.source=?""",
            (owner, lead.source_id),
        ).fetchone()
        if row is None:
            return False
        raw,digest,stage,state,job_input = row
        if not isinstance(raw, str) or len(raw) > 32768:
            raise ValueError("source metadata exceeds bounded review size")
        body = json.loads(raw)
        if (canonical_digest(body) != digest
            or body.get("source_id") != lead.source_id
            or body.get("url") != url
            or body.get("training_authorized") is not False
            or stage not in range(6)
            or state not in {"pending", "blocked", "leased", "reviewed"}):
            raise ValueError("untrusted or corrupt source policy metadata")
        if stage == 0 and job_input != digest:
            raise ValueError("stale policy-stage source identity")
        if (state == "reviewed") != (stage == 5):
            raise ValueError("policy job state and stage disagree")
        if state == "blocked":
            return False
        is_video = body.get("kind") == "video_candidate"
        if (lead.lane == "video") != is_video:
            return False
        return True

    def _valid_update(self, owner: str, lead: ResearchLead,
                      current: dict[str, dict]) -> bool:
        """Require a genuine current source-text revision, not a link revisit."""
        source = current.get(lead.source_id)
        if (source is None or source.get("source_url") != lead.url
            or source.get("status") != "active"
            or "design_reference" not in source.get("allowed_scopes", ())
            or lead.published_at is None
            or lead.revision_hint != source.get("source_text_digest")):
            return False
        if (_instant(source["observed_at"]) > _instant(lead.discovered_at)
            or _instant(lead.published_at) > _instant(source["observed_at"])):
            return False
        # The latest revision is a document revision; a second observation
        # with identical text must not masquerade as updated information.
        history = self.library.history(owner, lead.source_id, authorized=True)
        if (len(history) < 2
            or history[-1].revision_digest != source["revision_digest"]
            or history[-1].source_text_digest == history[-2].source_text_digest):
            return False
        allowed = {entry["note"]["mechanic"]
                   for entry in source.get("notes", ())}
        return bool(allowed.intersection(lead.tags))

    def preview(self, owner: str, *, sample: HardwareSample,
                at: str, idle_since: str, now_seconds: float,
                authorized: bool, consented: bool,
                article_consent: bool, video_consent: bool,
                updates_consent: bool,
                video_hints: tuple[ResearchLead, ...] = (),
                update_hints: tuple[ResearchLead, ...] = (),
                policy: IdleResearchPolicy = IdleResearchPolicy(),
                article_limit: int = 64,
                max_per_host: int = 2) -> SourceFedNestPlan:
        _auth(owner, authorized)
        if not isinstance(video_hints, tuple) or not isinstance(update_hints, tuple):
            raise ValueError("typed research hint batches required")
        if (len(video_hints) > 128 or len(update_hints) > 128
            or any(not isinstance(x, ResearchLead) or x.lane != "video"
                   for x in video_hints)
            or any(not isinstance(x, ResearchLead) or x.lane != "updates"
                   for x in update_hints)):
            raise ValueError("bounded specialist research hints required")
        for flag in (consented, article_consent, video_consent, updates_consent):
            if type(flag) is not bool:
                raise ValueError("explicit per-specialist consent flags required")
        _integer(article_limit, "article candidate limit", 1, 100)
        _integer(max_per_host, "source host cap", 1, 20)
        if not isinstance(policy, IdleResearchPolicy):
            raise ValueError("typed idle research policy required")
        nest = self.nest.read(owner, authorized=True)
        if nest is None:
            raise ValueError("signed Dragon nest must be initialized")
        # No source history, URL or activity inspection before consent and
        # actual idle/resource preflight. Foreground preemption wins.
        early = plan_idle_research(
            nest, (), sample, at=at, idle_since=idle_since,
            now_seconds=now_seconds, authorized=True,
            consented=consented, policy=policy,
        )
        if early.reason != "untrusted_intents_require_separate_worker_admission":
            return SourceFedNestPlan(early, 0, 0, 0, 0, 0)
        collected: list[ResearchLead] = []
        rejected=duplicates=articles=videos=updates=0
        seen: set[tuple[str, str]] = set()
        approved_update_ids = set()
        # All current revisions and rights are read through the canonical
        # validator, never a browser-supplied summary or index.
        current = ({r["source_id"]: r for r in self.library._rows(owner)}
                   if updates_consent and update_hints else {})
        if updates_consent:
            for hint in sorted(update_hints, key=lambda x:(x.source_id,x.url)):
                if not self._registered(owner,hint) or not self._valid_update(owner,hint,current):
                    rejected+=1
                    continue
                identity=(hint.lane,hint.source_id)
                if identity in seen:
                    duplicates+=1
                    continue
                seen.add(identity);approved_update_ids.add(hint.source_id)
                collected.append(hint);updates+=1
        if article_consent:
            query=" ".join((*nest.focus_tags,*nest.adjacent_tags))[:300].strip()
            if query:
                proposal=self.atlas.plan(
                    owner,query,authorized=True,limit=max(article_limit,len(CATALOG)),
                    max_per_host=max_per_host,
                )
                for hit in proposal["selected"]:
                    if hit["policy_state"] == "blocked":
                        continue
                    # Use exact curated topic membership; never derive
                    # article text or publication date from a URL.
                    seed=next((s for s in CATALOG if s["slug"]==hit["slug"]), None)
                    if seed is None:
                        raise ValueError("curated atlas identity changed")
                    tags=tuple(sorted(set(seed["topics"]) & (
                        set(nest.focus_tags)|set(nest.adjacent_tags))))
                    if not tags:
                        continue
                    if hit["source_id"] in approved_update_ids:
                        duplicates+=1
                        continue
                    event_time=datetime.fromtimestamp(
                        hit["editorial_recorded_at"],timezone.utc
                    ).isoformat().replace("+00:00","Z")
                    lead=ResearchLead(hit["source_id"],hit["url"],tags,
                                      "article",event_time)
                    if not self._registered(owner,lead):
                        rejected+=1
                        continue
                    identity=(lead.lane,lead.source_id)
                    if identity in seen:
                        duplicates+=1
                        continue
                    seen.add(identity);collected.append(lead);articles+=1
                    if articles >= article_limit:
                        break
        if video_consent:
            for hint in sorted(video_hints,key=lambda x:(x.source_id,x.url)):
                if not self._registered(owner,hint):
                    rejected+=1
                    continue
                identity=(hint.lane,hint.source_id)
                if identity in seen:
                    duplicates+=1
                    continue
                seen.add(identity);collected.append(hint);videos+=1
        if len(collected)>policy.max_leads:
            # Never silently truncate a security-sensitive scheduled batch.
            raise ValueError("specialist research budget exceeded")
        planned=plan_idle_research(
            nest,tuple(collected),sample,at=at,idle_since=idle_since,
            now_seconds=now_seconds,authorized=True,consented=True,
            policy=policy,
        )
        return SourceFedNestPlan(
            planned,articles,videos,updates,rejected,duplicates,
        )
