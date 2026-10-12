"""Versioned research campaign receipts for Dragon game-creator discovery.

A campaign preserves the task/axis configuration, unreviewed source proposal,
source metadata hashes and raw provenance lineage. It is not a crawler dispatch,
training job, factual almanac entry, promotion decision or legal approval.
Hashes detect repository/database drift; they are not cryptographic signatures.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import re

from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import DragonAlmanacs, _auth
from .dragon_discovery_facets import DiscoveryFacetIndex
from .dragon_discovery_portfolio import MissionPortfolio, PortfolioRequest, PortfolioAxis
from .dragon_discovery_mission import SourceMission
from .reviewed_knowledge import _id


SCHEMA = "skeleton.dragon.discovery_campaign_revision.v1"
MAX_REVISIONS = 128
HASH = re.compile(r"[0-9a-f]{64}\Z")


class DiscoveryCampaigns:
    """Owner-scoped, append-only research proposal ledger with integrity checks."""

    def __init__(self, almanacs: DragonAlmanacs):
        if not isinstance(almanacs, DragonAlmanacs):
            raise TypeError("canonical DragonAlmanacs required")
        self.db = almanacs.db
        self.facets = DiscoveryFacetIndex(almanacs)
        self.portfolio = MissionPortfolio(almanacs)
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_discovery_campaigns (
          owner TEXT NOT NULL, campaign TEXT NOT NULL,
          revision INTEGER NOT NULL, body TEXT NOT NULL,
          digest TEXT NOT NULL,
          PRIMARY KEY(owner,campaign,revision),
          UNIQUE(owner,campaign,digest))""")

    def _history(self, owner: str, campaign: str) -> list[dict]:
        rows = self.db.execute(
            """SELECT revision,body,digest FROM dragon_discovery_campaigns
               WHERE owner=? AND campaign=? ORDER BY revision LIMIT ?""",
            (owner, campaign, MAX_REVISIONS + 1),
        ).fetchall()
        if len(rows) > MAX_REVISIONS:
            raise ValueError("campaign revision budget exceeded")
        history = []
        parent = None
        for version, raw, digest in rows:
            if not isinstance(raw, str) or len(raw) > 1_000_000:
                raise ValueError("campaign receipt byte budget exceeded")
            body = json.loads(raw)
            if (not isinstance(body, dict)
                    or canonical_digest(body) != digest
                    or body.get("schema") != SCHEMA
                    or body.get("owner") != owner
                    or body.get("campaign") != campaign
                    or type(version) is not int or version != len(history)
                    or body.get("revision") != version
                    or body.get("parent_digest") != parent
                    or not isinstance(body.get("plan"), dict)
                    or canonical_digest(body["plan"]) != body.get("plan_digest")
                    or not isinstance(body.get("request"), dict)
                    or not isinstance(body.get("source_dependencies"), dict)
                    or body.get("crawl_authorized") is not False
                    or body.get("source_rights_approved") is not False
                    or body.get("training_authorized") is not False
                    or body.get("memory_promotion_authorized") is not False):
                raise ValueError("campaign revision lineage is corrupt")
            for sid, ref in body["source_dependencies"].items():
                if (not isinstance(sid, str) or
                        not isinstance(ref, dict) or
                        set(ref) != {"source_digest", "provenance_digest",
                                     "job_input_digest", "policy_state"} or
                        any(not isinstance(ref[k], str) or not HASH.fullmatch(ref[k])
                            for k in ("source_digest", "provenance_digest",
                                      "job_input_digest")) or
                        ref["policy_state"] not in {"pending", "blocked"}):
                    raise ValueError("campaign source dependencies are corrupt")
            history.append({"body": body, "digest": digest})
            parent = digest
        return history

    def _dependencies(self, owner: str, plan: dict) -> dict:
        selected = plan.get("selected")
        if not isinstance(selected, list) or len(selected) > 100:
            raise ValueError("bounded campaign source selection required")
        result = {}
        for item in selected:
            if not isinstance(item, dict) or not isinstance(item.get("source_id"), str):
                raise ValueError("invalid campaign source reference")
            sid = item["source_id"]
            row = self.db.execute(
                "SELECT body,digest FROM dragon_almanac_sources WHERE owner=? AND source=?",
                (owner, sid),
            ).fetchone()
            if row is None:
                raise ValueError("selected campaign source disappeared")
            source = json.loads(row[0])
            if source.get("url") != item.get("url"):
                raise ValueError("campaign proposal URL differs from canonical source")
            _, receipts = self.facets._metadata_tokens(owner, sid, row[0], row[1])
            job = self.db.execute(
                """SELECT stage,state,input_digest FROM dragon_almanac_jobs
                   WHERE owner=? AND source=?""", (owner, sid)).fetchone()
            if (job is None or job[0] != 0 or
                    job[1] != item.get("policy_state") or
                    job[1] not in {"pending", "blocked"} or
                    job[2] != row[1]):
                raise ValueError("campaign source policy-stage input has changed")
            result[sid] = {
                "source_digest": row[1],
                "provenance_digest": receipts,
                "job_input_digest": job[2],
                "policy_state": job[1],
            }
        if len(result) != len(selected):
            raise ValueError("duplicate campaign source selection")
        return dict(sorted(result.items()))

    @staticmethod
    def _request_body(request: PortfolioRequest, topic: str | None) -> dict:
        return {
            "mission": asdict(request.mission),
            "axes": [asdict(axis) for axis in request.axes],
            "total_limit": request.total_limit,
            "per_axis_candidates": request.per_axis_candidates,
            "max_per_host": request.max_per_host,
            "indexed": request.indexed,
            "topic": topic,
        }

    def record(self, owner: str, campaign: str, request: PortfolioRequest, *,
               authorized: bool, topic: str | None = None,
               expected_parent: str | None = None) -> dict:
        _auth(owner, authorized)
        _id(campaign, "campaign")
        if not isinstance(request, PortfolioRequest):
            raise ValueError("typed research campaign required")
        if expected_parent is not None and (
                not isinstance(expected_parent, str) or not HASH.fullmatch(expected_parent)):
            raise ValueError("invalid expected campaign revision digest")
        # Scouting is read-only, and captures no personal/source content.
        proposal = self.portfolio.build(
            owner, request, authorized=True, topic=topic)
        request_body = self._request_body(request, topic)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            previous = self._history(owner, campaign)
            if len(previous) >= MAX_REVISIONS:
                raise ValueError("campaign revision budget exceeded")
            parent = previous[-1]["digest"] if previous else None
            dependencies = self._dependencies(owner, proposal)
            if previous:
                prior = previous[-1]["body"]
                if (prior["plan"] == proposal and
                        prior["request"] == request_body and
                        prior["source_dependencies"] == dependencies):
                    self.db.execute("COMMIT")
                    return {
                        "owner": owner, "campaign": campaign,
                        "revision": prior["revision"],
                        "digest": parent, "unchanged": True,
                        "training_authorized": False,
                    }
            if expected_parent != parent:
                raise ValueError("campaign CAS parent mismatch")
            body = {
                "schema": SCHEMA, "owner": owner,
                "campaign": campaign, "revision": len(previous),
                "parent_digest": parent,
                "request": request_body,
                "plan": proposal, "plan_digest": canonical_digest(proposal),
                "source_dependencies": dependencies,
                "crawl_authorized": False,
                "source_rights_approved": False,
                "training_authorized": False,
                "memory_promotion_authorized": False,
            }
            digest = canonical_digest(body)
            self.db.execute(
                "INSERT INTO dragon_discovery_campaigns VALUES(?,?,?,?,?)",
                (owner, campaign, body["revision"], canonical_json(body), digest),
            )
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        return {
            "owner": owner, "campaign": campaign,
            "revision": body["revision"], "digest": digest,
            "unchanged": False,
            "selected_leads": len(proposal["selected"]),
            "discovery_gaps": proposal["uncovered_axes"],
            "training_authorized": False,
        }

    @staticmethod
    def _restore_request(body: dict) -> tuple[PortfolioRequest, str | None]:
        """Strictly decode a committed campaign's original typed mission.

        Do not accept inferred or added parameter fields when resuming. All
        admitted options must have existed at the time the campaign was made.
        """
        if not isinstance(body, dict) or set(body) != {
                "mission", "axes", "total_limit", "per_axis_candidates",
                "max_per_host", "indexed", "topic"}:
            raise ValueError("campaign request schema mismatch")
        allowed_mission = {
            "goal", "platform", "genre", "era", "prefer_video", "limit",
            "scan_budget"}
        mission = body["mission"]
        axes = body["axes"]
        if not isinstance(mission, dict) or set(mission) != allowed_mission:
            raise ValueError("campaign mission schema mismatch")
        if not isinstance(axes, list) or not all(
                isinstance(x, dict) and set(x) ==
                {"axis_id", "question", "minimum", "importance"} for x in axes):
            raise ValueError("campaign axis schema mismatch")
        topic = body["topic"]
        if topic is not None:
            _id(topic, "campaign topic")
        try:
            restored = PortfolioRequest(
                SourceMission(**mission),
                tuple(PortfolioAxis(**x) for x in axes),
                total_limit=body["total_limit"],
                per_axis_candidates=body["per_axis_candidates"],
                max_per_host=body["max_per_host"],
                indexed=body["indexed"],
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("committed campaign parameters invalid") from exc
        if DiscoveryCampaigns._request_body(restored, topic) != body:
            raise ValueError("campaign typed request is not canonical")
        return restored, topic

    def refresh(self, owner: str, campaign: str, *,
                authorized: bool, expected_parent: str | None = None) -> dict:
        """Recompute the saved plan, preserving its original policy boundaries.

        Reuses the same typed source mission and axes. No crawl, source use or
        training occurs. CAS serializes competing refreshes/revisions.
        """
        _auth(owner, authorized)
        _id(campaign, "campaign")
        history = self._history(owner, campaign)
        if not history:
            raise ValueError("unknown owner campaign")
        digest = history[-1]["digest"]
        if expected_parent is not None and expected_parent != digest:
            raise ValueError("campaign refresh expected parent differs")
        request, topic = self._restore_request(history[-1]["body"]["request"])
        result = self.record(
            owner, campaign, request, authorized=True, topic=topic,
            expected_parent=digest)
        result["reused_saved_request"] = True
        result["crawl_authorized"] = False
        result["source_rights_approved"] = False
        return result

    def inspect(self, owner: str, campaign: str, *, authorized: bool) -> dict:
        _auth(owner, authorized)
        _id(campaign, "campaign")
        history = self._history(owner, campaign)
        if not history:
            raise ValueError("unknown owner campaign")
        latest = history[-1]["body"]
        stale = []
        for sid, captured in latest["source_dependencies"].items():
            row = self.db.execute(
                "SELECT body,digest FROM dragon_almanac_sources WHERE owner=? AND source=?",
                (owner, sid),
            ).fetchone()
            if row is None:
                stale.append(sid)
                continue
            _, receipts = self.facets._metadata_tokens(owner, sid, row[0], row[1])
            job = self.db.execute(
                """SELECT stage,state,input_digest FROM dragon_almanac_jobs
                   WHERE owner=? AND source=?""", (owner, sid)).fetchone()
            if (row[1] != captured["source_digest"] or
                    receipts != captured["provenance_digest"] or
                    job is None or job[0] != 0 or
                    job[1] != captured["policy_state"] or
                    job[2] != captured["job_input_digest"]):
                stale.append(sid)
        earlier = history[-2]["body"]["plan"] if len(history) > 1 else None
        current = latest["plan"]
        selected = {item["source_id"] for item in current["selected"]}
        prior_selected = (
            {item["source_id"] for item in earlier["selected"]}
            if earlier is not None else set())
        previous_gaps = (
            {row["axis_id"]: row["missing_leads"]
             for row in earlier["axis_coverage"]}
            if earlier is not None else {})
        gaps = {row["axis_id"]: row["missing_leads"]
                for row in current["axis_coverage"]}
        return {
            "owner": owner, "campaign": campaign,
            "revision": latest["revision"],
            "digest": history[-1]["digest"],
            "parent_digest": latest["parent_digest"],
            "revision_count": len(history),
            "plan": current, "plan_digest": latest["plan_digest"],
            "source_dependencies_current": not stale,
            "stale_source_ids": stale,
            "selected_added_since_previous": sorted(selected-prior_selected),
            "selected_removed_since_previous": sorted(prior_selected-selected),
            "gap_delta_since_previous": {
                axis: gaps[axis] - previous_gaps.get(axis, gaps[axis])
                for axis in sorted(gaps)},
            "integrity_checked": True,
            "cryptographically_signed": False,
            "crawl_authorized": False,
            "source_rights_approved": False,
            "training_authorized": False,
            "memory_promotion_authorized": False,
        }
