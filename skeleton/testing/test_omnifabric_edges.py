"""Edge-case and evidence-bundle tests for OmniFabric hex surface."""
from __future__ import annotations

import pytest

from skeleton.kernel.omnifabric import (
    CapacityError,
    ChainBroken,
    FabricOutbox,
    LedgerCatalog,
    LedgerUnknown,
    OmniFabric,
    OmniFabricService,
    OutboxFull,
    QueryBoundsError,
    evidence_bundle,
    verify_events,
)
from skeleton.kernel.omnifabric.errors import ProjectionStale, ReplayConflict, SegmentCorrupt
from skeleton.kernel.omnifabric.queries import MAX_LIMIT, filter_events
from skeleton.kernel.omnifabric.verify import ChainReport, merkle_root_of
from skeleton.kernel.omnifabric.windows import seal_window
from skeleton.kernel.omnifabric.segment import seal_segment
from skeleton.kernel.omnifabric.outbox import MemorySink
from skeleton.kernel.omnifabric.projections import KindCounterProjection
from skeleton.kernel.omnifabric.replay import FabricReplayer
from skeleton.kernel.omnifabric.merkle import verify_inclusion, inclusion_proof



def test_evidence_and_edges_0():
    fab = OmniFabric(hot_cap=32)
    for j in range(4):
        fab.append("E0", f"k{j}", {"j": j, "i": 0}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p0")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S0", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_1():
    fab = OmniFabric(hot_cap=33)
    for j in range(5):
        fab.append("E1", f"k{j}", {"j": j, "i": 1}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p1")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S1", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_2():
    fab = OmniFabric(hot_cap=34)
    for j in range(6):
        fab.append("E2", f"k{j}", {"j": j, "i": 2}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p2")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S2", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_3():
    fab = OmniFabric(hot_cap=35)
    for j in range(7):
        fab.append("E3", f"k{j}", {"j": j, "i": 3}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p3")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S3", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_4():
    fab = OmniFabric(hot_cap=36)
    for j in range(8):
        fab.append("E4", f"k{j}", {"j": j, "i": 4}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p4")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S4", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_5():
    fab = OmniFabric(hot_cap=37)
    for j in range(9):
        fab.append("E5", f"k{j}", {"j": j, "i": 5}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p5")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S5", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_6():
    fab = OmniFabric(hot_cap=38)
    for j in range(4):
        fab.append("E6", f"k{j}", {"j": j, "i": 6}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p6")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S6", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_7():
    fab = OmniFabric(hot_cap=39)
    for j in range(5):
        fab.append("E7", f"k{j}", {"j": j, "i": 7}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p7")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S7", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_8():
    fab = OmniFabric(hot_cap=40)
    for j in range(6):
        fab.append("E8", f"k{j}", {"j": j, "i": 8}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p8")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S8", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_9():
    fab = OmniFabric(hot_cap=41)
    for j in range(7):
        fab.append("E9", f"k{j}", {"j": j, "i": 9}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p9")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S9", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_10():
    fab = OmniFabric(hot_cap=42)
    for j in range(8):
        fab.append("E10", f"k{j}", {"j": j, "i": 10}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p10")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S10", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_11():
    fab = OmniFabric(hot_cap=43)
    for j in range(9):
        fab.append("E11", f"k{j}", {"j": j, "i": 11}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p11")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S11", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_12():
    fab = OmniFabric(hot_cap=44)
    for j in range(4):
        fab.append("E12", f"k{j}", {"j": j, "i": 12}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p12")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S12", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_13():
    fab = OmniFabric(hot_cap=45)
    for j in range(5):
        fab.append("E13", f"k{j}", {"j": j, "i": 13}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p13")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S13", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_14():
    fab = OmniFabric(hot_cap=46)
    for j in range(6):
        fab.append("E14", f"k{j}", {"j": j, "i": 14}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p14")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S14", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_15():
    fab = OmniFabric(hot_cap=47)
    for j in range(7):
        fab.append("E15", f"k{j}", {"j": j, "i": 15}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p15")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S15", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_16():
    fab = OmniFabric(hot_cap=32)
    for j in range(8):
        fab.append("E16", f"k{j}", {"j": j, "i": 16}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p16")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S16", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_17():
    fab = OmniFabric(hot_cap=33)
    for j in range(9):
        fab.append("E17", f"k{j}", {"j": j, "i": 17}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p17")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S17", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_18():
    fab = OmniFabric(hot_cap=34)
    for j in range(4):
        fab.append("E18", f"k{j}", {"j": j, "i": 18}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p18")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S18", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_19():
    fab = OmniFabric(hot_cap=35)
    for j in range(5):
        fab.append("E19", f"k{j}", {"j": j, "i": 19}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p19")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S19", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_20():
    fab = OmniFabric(hot_cap=36)
    for j in range(6):
        fab.append("E20", f"k{j}", {"j": j, "i": 20}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p20")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S20", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_21():
    fab = OmniFabric(hot_cap=37)
    for j in range(7):
        fab.append("E21", f"k{j}", {"j": j, "i": 21}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p21")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S21", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_22():
    fab = OmniFabric(hot_cap=38)
    for j in range(8):
        fab.append("E22", f"k{j}", {"j": j, "i": 22}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p22")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S22", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_23():
    fab = OmniFabric(hot_cap=39)
    for j in range(9):
        fab.append("E23", f"k{j}", {"j": j, "i": 23}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p23")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S23", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_24():
    fab = OmniFabric(hot_cap=40)
    for j in range(4):
        fab.append("E24", f"k{j}", {"j": j, "i": 24}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p24")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S24", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_25():
    fab = OmniFabric(hot_cap=41)
    for j in range(5):
        fab.append("E25", f"k{j}", {"j": j, "i": 25}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p25")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S25", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_26():
    fab = OmniFabric(hot_cap=42)
    for j in range(6):
        fab.append("E26", f"k{j}", {"j": j, "i": 26}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p26")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S26", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_27():
    fab = OmniFabric(hot_cap=43)
    for j in range(7):
        fab.append("E27", f"k{j}", {"j": j, "i": 27}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p27")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S27", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_28():
    fab = OmniFabric(hot_cap=44)
    for j in range(8):
        fab.append("E28", f"k{j}", {"j": j, "i": 28}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p28")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S28", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_29():
    fab = OmniFabric(hot_cap=45)
    for j in range(9):
        fab.append("E29", f"k{j}", {"j": j, "i": 29}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p29")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S29", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_30():
    fab = OmniFabric(hot_cap=46)
    for j in range(4):
        fab.append("E30", f"k{j}", {"j": j, "i": 30}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p30")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S30", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_31():
    fab = OmniFabric(hot_cap=47)
    for j in range(5):
        fab.append("E31", f"k{j}", {"j": j, "i": 31}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p31")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S31", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_32():
    fab = OmniFabric(hot_cap=32)
    for j in range(6):
        fab.append("E32", f"k{j}", {"j": j, "i": 32}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p32")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S32", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_33():
    fab = OmniFabric(hot_cap=33)
    for j in range(7):
        fab.append("E33", f"k{j}", {"j": j, "i": 33}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p33")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S33", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_34():
    fab = OmniFabric(hot_cap=34)
    for j in range(8):
        fab.append("E34", f"k{j}", {"j": j, "i": 34}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p34")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S34", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_35():
    fab = OmniFabric(hot_cap=35)
    for j in range(9):
        fab.append("E35", f"k{j}", {"j": j, "i": 35}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p35")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S35", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_36():
    fab = OmniFabric(hot_cap=36)
    for j in range(4):
        fab.append("E36", f"k{j}", {"j": j, "i": 36}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p36")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S36", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_37():
    fab = OmniFabric(hot_cap=37)
    for j in range(5):
        fab.append("E37", f"k{j}", {"j": j, "i": 37}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p37")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S37", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_38():
    fab = OmniFabric(hot_cap=38)
    for j in range(6):
        fab.append("E38", f"k{j}", {"j": j, "i": 38}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p38")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S38", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_39():
    fab = OmniFabric(hot_cap=39)
    for j in range(7):
        fab.append("E39", f"k{j}", {"j": j, "i": 39}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p39")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S39", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_40():
    fab = OmniFabric(hot_cap=40)
    for j in range(8):
        fab.append("E40", f"k{j}", {"j": j, "i": 40}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p40")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S40", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_41():
    fab = OmniFabric(hot_cap=41)
    for j in range(9):
        fab.append("E41", f"k{j}", {"j": j, "i": 41}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p41")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S41", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_42():
    fab = OmniFabric(hot_cap=42)
    for j in range(4):
        fab.append("E42", f"k{j}", {"j": j, "i": 42}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p42")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S42", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_43():
    fab = OmniFabric(hot_cap=43)
    for j in range(5):
        fab.append("E43", f"k{j}", {"j": j, "i": 43}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p43")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S43", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_44():
    fab = OmniFabric(hot_cap=44)
    for j in range(6):
        fab.append("E44", f"k{j}", {"j": j, "i": 44}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p44")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S44", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_45():
    fab = OmniFabric(hot_cap=45)
    for j in range(7):
        fab.append("E45", f"k{j}", {"j": j, "i": 45}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p45")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S45", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_46():
    fab = OmniFabric(hot_cap=46)
    for j in range(8):
        fab.append("E46", f"k{j}", {"j": j, "i": 46}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p46")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S46", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_47():
    fab = OmniFabric(hot_cap=47)
    for j in range(9):
        fab.append("E47", f"k{j}", {"j": j, "i": 47}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p47")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S47", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_48():
    fab = OmniFabric(hot_cap=32)
    for j in range(4):
        fab.append("E48", f"k{j}", {"j": j, "i": 48}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p48")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S48", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_evidence_and_edges_49():
    fab = OmniFabric(hot_cap=33)
    for j in range(5):
        fab.append("E49", f"k{j}", {"j": j, "i": 49}, [f"q{j%2}"])
    bundle = evidence_bundle(fab.snapshot_tail())
    assert bundle["report"]["ok"] is True
    assert bundle["merkle_root"] == merkle_root_of(fab.snapshot_tail())
    report = verify_events(fab.snapshot_tail(), require_genesis=True)
    assert isinstance(report, ChainReport)
    assert report.ok
    with pytest.raises(QueryBoundsError):
        filter_events(fab.snapshot_tail(), limit=MAX_LIMIT + 1)
    cat = LedgerCatalog(max_ledgers=2, require_registered=True)
    cat.register("only1")
    cat.register("only2")
    with pytest.raises(CapacityError):
        cat.register("only3")
    with pytest.raises(LedgerUnknown):
        cat.ensure("nope")
    proj = KindCounterProjection(f"p49")
    proj.apply_many(fab.snapshot_tail())
    with pytest.raises(ProjectionStale):
        proj.require_fresh(fab.current_seq + 10)
    svc = OmniFabricService(hot_cap=16)
    for j in range(5):
        svc.append("S49", "k", {"j": j}, [])
    # seal oldest 2 if enough
    if svc.fabric.hot_len >= 2:
        sealed = svc.seal_hot_prefix(2)
        assert sealed["window"]["event_count"] == 2

def test_outbox_cap_backpressure_0():
    ob = FabricOutbox(MemorySink(), cap=1)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_1():
    ob = FabricOutbox(MemorySink(), cap=2)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_2():
    ob = FabricOutbox(MemorySink(), cap=3)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_3():
    ob = FabricOutbox(MemorySink(), cap=1)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_4():
    ob = FabricOutbox(MemorySink(), cap=2)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_5():
    ob = FabricOutbox(MemorySink(), cap=3)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_6():
    ob = FabricOutbox(MemorySink(), cap=1)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_7():
    ob = FabricOutbox(MemorySink(), cap=2)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_8():
    ob = FabricOutbox(MemorySink(), cap=3)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_9():
    ob = FabricOutbox(MemorySink(), cap=1)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_10():
    ob = FabricOutbox(MemorySink(), cap=2)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_11():
    ob = FabricOutbox(MemorySink(), cap=3)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_12():
    ob = FabricOutbox(MemorySink(), cap=1)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_13():
    ob = FabricOutbox(MemorySink(), cap=2)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])

def test_outbox_cap_backpressure_14():
    ob = FabricOutbox(MemorySink(), cap=3)
    fab = OmniFabric(ob, auto_confirm=False)
    for _ in range(ob.cap):
        fab.append("L", "k", {}, [])
    with pytest.raises(OutboxFull):
        fab.append("L", "k", {}, [])
