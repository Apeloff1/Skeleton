"""Archive/history projection over fully re-executed campaign source events."""
from __future__ import annotations

from dataclasses import asdict
from skeleton.app.frontier_campaign_source import build_campaign
from skeleton.app.recovered_evidence import EvidenceError, integer, digest, seal, pin, parse
from skeleton.jeeves.game_frontier_milestone_9 import CampaignArchive
from skeleton.jeeves.game_frontier_milestone_10 import RetentionPolicy,apply_retention,query_by_campaign
from skeleton.jeeves.game_frontier_milestone_11 import diff
from skeleton.jeeves.game_frontier_milestone_12 import SnapshotHistory
from skeleton.jeeves.game_frontier_milestone_13 import HistoryBound,compact,latest
from skeleton.jeeves.game_frontier_milestone_14 import receipt,between

GENESIS="0"*64
MAX_VERSIONS=128
MAX_REPLAY_STEPS=8192
MAX_STORED_BYTES=16*1024*1024


def event_body(scope,sequence,prior,order,evidence):
    return {"schema":"skeleton.frontier-campaign.archive-event.v1","scope":scope,
            "sequence":sequence,"previous":prior,"order_digest":digest(order),
            "manifest":evidence["export"]["manifest"],"execution_digest":digest(evidence),
            "steps":evidence["step_count"]}


def project(scope,rows,*,retention,history_limit,expected_head,campaign_id=None):
    integer(retention,1,MAX_VERSIONS)
    integer(history_limit,1,MAX_VERSIONS)
    if len(rows)>MAX_VERSIONS:
        raise EvidenceError("archive event count exceeds ceiling")
    archive=CampaignArchive(max_entries=MAX_VERSIONS)
    history=SnapshotHistory()
    prior=GENESIS
    bytes_seen=0
    steps=0
    manifests=set()
    records=[]
    for sequence,row in enumerate(rows):
        index,prior_claim,head,manifest,source_bytes,observed_steps=row
        if index!=sequence or prior_claim!=prior:
            raise EvidenceError("archive sequence or predecessor mismatch")
        if type(source_bytes) is not bytes:
            raise EvidenceError("archive source encoding")
        bytes_seen+=len(source_bytes)
        if bytes_seen>MAX_STORED_BYTES:
            raise EvidenceError("archive replay byte ceiling")
        integer(observed_steps,1,512)
        if steps+observed_steps>MAX_REPLAY_STEPS:
            raise EvidenceError("archive cumulative replay work ceiling")
        order=parse(source_bytes)
        # Check count before running the canonical owner. A false stored
        # counter cannot force the replay beyond its declared work budget.
        actual=sum(len(session["steps"]) for session in order["sessions"])
        if actual!=observed_steps:
            raise EvidenceError("stored step accounting diverges")
        export,evidence=build_campaign(order)
        steps+=evidence["step_count"]
        if export.manifest!=manifest or manifest in manifests:
            raise EvidenceError("duplicate or mismatched canonical manifest")
        manifests.add(manifest)
        calculated=digest(event_body(scope,sequence,prior,order,evidence))
        pin(calculated,head)
        prior=calculated
        archive.store(export)
        removed=apply_retention(archive,RetentionPolicy(retention))
        snap=history.record(archive)
        records.append({"sequence":sequence,"event_digest":head,"manifest":manifest,
                        "order_digest":evidence["order_digest"],"steps":observed_steps,
                        "projection_evicted":removed,"snapshot_digest":snap.digest})
    pin(prior,expected_head)
    if not records:
        return seal({"schema":"skeleton.frontier-campaign.archive-audit.v1","scope":scope,
            "head":GENESIS,"event_count":0,"replayed_steps":0,"retained_manifests":[],
            "history":None,"history_compacted":0,"recent_diff":None,"records":[],
            "campaign_matches":[],"physical_device_tested":False,"release_certified":False})
    if not history.verify():
        raise EvidenceError("canonical archive history failed verification")
    unpruned=receipt(history)
    removed=compact(history,HistoryBound(history_limit))
    retained=receipt(history)
    selected=between(history,0,len(history))
    recent=diff(selected[-2],selected[-1]) if len(selected)>1 else None
    if recent is not None:
        recent={**recent,"added":list(recent["added"]),"removed":list(recent["removed"])}
    matches=[] if campaign_id is None else [asdict(row) for row in query_by_campaign(archive,campaign_id)]
    return seal({"schema":"skeleton.frontier-campaign.archive-audit.v1","scope":scope,
                 "head":prior,"event_count":len(records),"replayed_steps":steps,
                 "retained_manifests":list(archive.list_manifests()),
                 "history":{"uncompacted":asdict(unpruned),"retained":asdict(retained),
                            "latest":latest(history).digest},
                 "history_compacted":removed,"recent_diff":recent,"records":records,
                 "campaign_matches":matches,"source_reconstructed":True,
                 "history_compaction_is_projection_only":True,
                 "source_events_physically_deleted":False,
                 "native_model_tested":False,"physical_device_tested":False,
                 "release_certified":False})
