from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_session import FrontierSession
from skeleton.jeeves.game_frontier_campaign import CampaignLedger, audit_receipt
from skeleton.jeeves.game_frontier_milestone_8 import export_campaign
from skeleton.jeeves.game_frontier_milestone_9 import CampaignArchive, ArchiveError
import pytest


def _export(cid: str = "c1"):
    ledger = CampaignLedger(campaign_id=cid)
    session = FrontierSession(session_id="s1")
    session.step(
        clock=PresentationClock(fps=60), lod_tier=1, weather_digest="c" * 64,
        evidence=WorldModelEvidence(
            source_digest="a" * 64, mesh_vertex_count=20, mesh_triangle_count=8,
            reconstruction_digest="b" * 64, adapter_id="m9",
        ),
        percepts=("x",), goal="hold",
    )
    ledger.add(session)
    return export_campaign(ledger, audit_receipt(ledger))


def test_store_and_get():
    archive = CampaignArchive()
    export = _export()
    manifest = archive.store(export)
    assert archive.get(manifest).campaign_id == "c1"
    assert len(archive) == 1


def test_rejects_duplicate():
    archive = CampaignArchive()
    export = _export()
    archive.store(export)
    with pytest.raises(ArchiveError):
        archive.store(export)


def test_missing():
    with pytest.raises(ArchiveError):
        CampaignArchive().get("a" * 64)


def test_list_sorted():
    archive = CampaignArchive()
    archive.store(_export("a"))
    archive.store(_export("b"))
    manifests = archive.list_manifests()
    assert list(manifests) == sorted(manifests)
    assert len(manifests) == 2


def test_rejects_forged_or_incomplete_export_evidence():
    from dataclasses import replace

    good = _export("tamper")
    samples = (
        replace(good, manifest="0" * 64),
        replace(good, head="0" * 64),
        replace(good, audit="bad"),
        replace(good, session_count=0),
        replace(good, session_count=True),
        replace(good, campaign_id=""),
        replace(good, campaign_id="too-long-" * 11),
    )
    for forged in samples:
        with pytest.raises(ArchiveError):
            CampaignArchive().store(forged)
    with pytest.raises(ArchiveError):
        CampaignArchive().store(object())


def test_rejects_invalid_keys_and_mutated_index_state():
    from dataclasses import replace

    archive = CampaignArchive()
    original = _export("tampered-index")
    manifest = archive.store(original)
    for key in ("bad", manifest.upper(), 42):
        with pytest.raises(ArchiveError):
            archive.get(key)
    archive.entries[manifest] = replace(original, head="f" * 64)
    with pytest.raises(ArchiveError):
        archive.get(manifest)
    with pytest.raises(ArchiveError):
        archive.list_manifests()


def test_bounded_archive_and_defensive_copy():
    from dataclasses import replace

    with pytest.raises(ArchiveError):
        CampaignArchive(max_entries=0)
    with pytest.raises(ArchiveError):
        CampaignArchive(max_entries=True)
    with pytest.raises(ArchiveError):
        CampaignArchive(max_entries=4097)
    archive = CampaignArchive(max_entries=1)
    export = _export("one")
    key = archive.store(export)
    assert archive.get(key) == export
    with pytest.raises(ArchiveError):
        archive.store(_export("two"))
    # The returned frozen export is not a live reference to the stored entry.
    forged = replace(archive.get(key), audit="a" * 64)
    assert forged != archive.get(key)


def test_staged_ai_mirror_has_identical_archive_contract():
    from skeleton.ai.agents.jeeves.game_frontier_milestone_8 import (
        CampaignExport as StagedExport,
    )
    from skeleton.ai.agents.jeeves.game_frontier_milestone_9 import (
        ArchiveError as StagedArchiveError,
        CampaignArchive as StagedArchive,
    )

    original = _export("staged")
    staged = StagedExport(
        campaign_id=original.campaign_id,
        session_count=original.session_count,
        head=original.head,
        audit=original.audit,
        manifest=original.manifest,
    )
    key = StagedArchive().store(staged)
    assert key == original.manifest
    with pytest.raises(StagedArchiveError):
        StagedArchive().store(StagedExport(
            campaign_id=staged.campaign_id,
            session_count=staged.session_count,
            head=staged.head,
            audit=staged.audit,
            manifest="0" * 64,
        ))
