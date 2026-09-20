"""Broad OmniFabric volume, projection, merkle, query, service tests."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from skeleton.kernel.omnifabric import (
    ChainBroken,
    FabricOutbox,
    LedgerCatalog,
    OmniFabric,
    OmniFabricService,
    OutboxFull,
    ProjectionHub,
    KindCounterProjection,
    LastValueProjection,
    verify_events,
    evidence_bundle,
)
from skeleton.kernel.omnifabric.batch import BatchItem, append_batch
from skeleton.kernel.omnifabric.merkle import (
    CheckpointBook,
    build_checkpoint,
    inclusion_proof,
    verify_inclusion,
)
from skeleton.kernel.omnifabric.persistence import JsonlEventLog
from skeleton.kernel.omnifabric.projections import QuorumAttestationProjection
from skeleton.kernel.omnifabric.queries import filter_events, query_fabric, range_by_seq
from skeleton.kernel.omnifabric.replay import FabricReplayer
from skeleton.kernel.omnifabric.segment import SegmentStore, seal_segment
from skeleton.kernel.omnifabric.subscribers import RecordingObserver, SubscriberBus
from skeleton.kernel.omnifabric.windows import WindowStore, seal_window
from skeleton.kernel.omnifabric.adapters import (
    from_rs_json,
    to_rs_json,
    from_zaibatsu_dict,
    to_zaibatsu_dict,
    wire_append_request,
)
from skeleton.kernel.omnifabric import doctrine

def test_volume_append_chain_0():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(10):
        ev = fab.append("ledger_0", f"kind_{i}", {"i": i, "n": 0}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 10
    assert len(fab.tail("ledger_0", 5)) == min(5, 10)

def test_volume_append_chain_1():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(11):
        ev = fab.append("ledger_1", f"kind_{i}", {"i": i, "n": 1}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 11
    assert len(fab.tail("ledger_1", 5)) == min(5, 11)

def test_volume_append_chain_2():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(12):
        ev = fab.append("ledger_2", f"kind_{i}", {"i": i, "n": 2}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 12
    assert len(fab.tail("ledger_2", 5)) == min(5, 12)

def test_volume_append_chain_3():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(13):
        ev = fab.append("ledger_3", f"kind_{i}", {"i": i, "n": 3}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 13
    assert len(fab.tail("ledger_3", 5)) == min(5, 13)

def test_volume_append_chain_4():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(14):
        ev = fab.append("ledger_4", f"kind_{i}", {"i": i, "n": 4}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 14
    assert len(fab.tail("ledger_4", 5)) == min(5, 14)

def test_volume_append_chain_5():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(15):
        ev = fab.append("ledger_5", f"kind_{i}", {"i": i, "n": 5}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 15
    assert len(fab.tail("ledger_5", 5)) == min(5, 15)

def test_volume_append_chain_6():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(16):
        ev = fab.append("ledger_6", f"kind_{i}", {"i": i, "n": 6}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 16
    assert len(fab.tail("ledger_6", 5)) == min(5, 16)

def test_volume_append_chain_7():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(17):
        ev = fab.append("ledger_7", f"kind_{i}", {"i": i, "n": 7}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 17
    assert len(fab.tail("ledger_7", 5)) == min(5, 17)

def test_volume_append_chain_8():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(18):
        ev = fab.append("ledger_8", f"kind_{i}", {"i": i, "n": 8}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 18
    assert len(fab.tail("ledger_8", 5)) == min(5, 18)

def test_volume_append_chain_9():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(19):
        ev = fab.append("ledger_9", f"kind_{i}", {"i": i, "n": 9}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 19
    assert len(fab.tail("ledger_9", 5)) == min(5, 19)

def test_volume_append_chain_10():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(20):
        ev = fab.append("ledger_10", f"kind_{i}", {"i": i, "n": 10}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 20
    assert len(fab.tail("ledger_10", 5)) == min(5, 20)

def test_volume_append_chain_11():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(21):
        ev = fab.append("ledger_11", f"kind_{i}", {"i": i, "n": 11}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 21
    assert len(fab.tail("ledger_11", 5)) == min(5, 21)

def test_volume_append_chain_12():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(22):
        ev = fab.append("ledger_12", f"kind_{i}", {"i": i, "n": 12}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 22
    assert len(fab.tail("ledger_12", 5)) == min(5, 22)

def test_volume_append_chain_13():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(23):
        ev = fab.append("ledger_13", f"kind_{i}", {"i": i, "n": 13}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 23
    assert len(fab.tail("ledger_13", 5)) == min(5, 23)

def test_volume_append_chain_14():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(24):
        ev = fab.append("ledger_14", f"kind_{i}", {"i": i, "n": 14}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 24
    assert len(fab.tail("ledger_14", 5)) == min(5, 24)

def test_volume_append_chain_15():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(25):
        ev = fab.append("ledger_15", f"kind_{i}", {"i": i, "n": 15}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 25
    assert len(fab.tail("ledger_15", 5)) == min(5, 25)

def test_volume_append_chain_16():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(26):
        ev = fab.append("ledger_16", f"kind_{i}", {"i": i, "n": 16}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 26
    assert len(fab.tail("ledger_16", 5)) == min(5, 26)

def test_volume_append_chain_17():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(27):
        ev = fab.append("ledger_17", f"kind_{i}", {"i": i, "n": 17}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 27
    assert len(fab.tail("ledger_17", 5)) == min(5, 27)

def test_volume_append_chain_18():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(28):
        ev = fab.append("ledger_18", f"kind_{i}", {"i": i, "n": 18}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 28
    assert len(fab.tail("ledger_18", 5)) == min(5, 28)

def test_volume_append_chain_19():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(29):
        ev = fab.append("ledger_19", f"kind_{i}", {"i": i, "n": 19}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 29
    assert len(fab.tail("ledger_19", 5)) == min(5, 29)

def test_volume_append_chain_20():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(30):
        ev = fab.append("ledger_20", f"kind_{i}", {"i": i, "n": 20}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 30
    assert len(fab.tail("ledger_20", 5)) == min(5, 30)

def test_volume_append_chain_21():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(31):
        ev = fab.append("ledger_21", f"kind_{i}", {"i": i, "n": 21}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 31
    assert len(fab.tail("ledger_21", 5)) == min(5, 31)

def test_volume_append_chain_22():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(32):
        ev = fab.append("ledger_22", f"kind_{i}", {"i": i, "n": 22}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 32
    assert len(fab.tail("ledger_22", 5)) == min(5, 32)

def test_volume_append_chain_23():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(33):
        ev = fab.append("ledger_23", f"kind_{i}", {"i": i, "n": 23}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 33
    assert len(fab.tail("ledger_23", 5)) == min(5, 33)

def test_volume_append_chain_24():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(34):
        ev = fab.append("ledger_24", f"kind_{i}", {"i": i, "n": 24}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 34
    assert len(fab.tail("ledger_24", 5)) == min(5, 34)

def test_volume_append_chain_25():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(35):
        ev = fab.append("ledger_25", f"kind_{i}", {"i": i, "n": 25}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 35
    assert len(fab.tail("ledger_25", 5)) == min(5, 35)

def test_volume_append_chain_26():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(36):
        ev = fab.append("ledger_26", f"kind_{i}", {"i": i, "n": 26}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 36
    assert len(fab.tail("ledger_26", 5)) == min(5, 36)

def test_volume_append_chain_27():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(37):
        ev = fab.append("ledger_27", f"kind_{i}", {"i": i, "n": 27}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 37
    assert len(fab.tail("ledger_27", 5)) == min(5, 37)

def test_volume_append_chain_28():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(38):
        ev = fab.append("ledger_28", f"kind_{i}", {"i": i, "n": 28}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 38
    assert len(fab.tail("ledger_28", 5)) == min(5, 38)

def test_volume_append_chain_29():
    fab = OmniFabric(hot_cap=128)
    last = None
    for i in range(39):
        ev = fab.append("ledger_29", f"kind_{i}", {"i": i, "n": 29}, [f"a{i%3}"])
        if last is not None:
            assert ev.prev_hash == last.hash
        last = ev
    assert fab.verify_chain() is True
    assert fab.current_seq == 39
    assert len(fab.tail("ledger_29", 5)) == min(5, 39)

def test_kind_counter_projection_0():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_0"))
    hub.add(LastValueProjection(f"lv_0", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_0"))
    fab = OmniFabric()
    for i in range(5):
        ev = fab.append("L0", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_0").state
    assert st["total"] == 5
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_0"] == 5

def test_kind_counter_projection_1():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_1"))
    hub.add(LastValueProjection(f"lv_1", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_1"))
    fab = OmniFabric()
    for i in range(6):
        ev = fab.append("L1", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_1").state
    assert st["total"] == 6
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_1"] == 6

def test_kind_counter_projection_2():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_2"))
    hub.add(LastValueProjection(f"lv_2", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_2"))
    fab = OmniFabric()
    for i in range(7):
        ev = fab.append("L2", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_2").state
    assert st["total"] == 7
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_2"] == 7

def test_kind_counter_projection_3():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_3"))
    hub.add(LastValueProjection(f"lv_3", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_3"))
    fab = OmniFabric()
    for i in range(8):
        ev = fab.append("L3", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_3").state
    assert st["total"] == 8
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_3"] == 8

def test_kind_counter_projection_4():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_4"))
    hub.add(LastValueProjection(f"lv_4", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_4"))
    fab = OmniFabric()
    for i in range(9):
        ev = fab.append("L4", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_4").state
    assert st["total"] == 9
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_4"] == 9

def test_kind_counter_projection_5():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_5"))
    hub.add(LastValueProjection(f"lv_5", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_5"))
    fab = OmniFabric()
    for i in range(10):
        ev = fab.append("L5", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_5").state
    assert st["total"] == 10
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_5"] == 10

def test_kind_counter_projection_6():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_6"))
    hub.add(LastValueProjection(f"lv_6", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_6"))
    fab = OmniFabric()
    for i in range(11):
        ev = fab.append("L6", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_6").state
    assert st["total"] == 11
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_6"] == 11

def test_kind_counter_projection_7():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_7"))
    hub.add(LastValueProjection(f"lv_7", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_7"))
    fab = OmniFabric()
    for i in range(5):
        ev = fab.append("L7", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_7").state
    assert st["total"] == 5
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_7"] == 5

def test_kind_counter_projection_8():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_8"))
    hub.add(LastValueProjection(f"lv_8", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_8"))
    fab = OmniFabric()
    for i in range(6):
        ev = fab.append("L8", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_8").state
    assert st["total"] == 6
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_8"] == 6

def test_kind_counter_projection_9():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_9"))
    hub.add(LastValueProjection(f"lv_9", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_9"))
    fab = OmniFabric()
    for i in range(7):
        ev = fab.append("L9", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_9").state
    assert st["total"] == 7
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_9"] == 7

def test_kind_counter_projection_10():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_10"))
    hub.add(LastValueProjection(f"lv_10", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_10"))
    fab = OmniFabric()
    for i in range(8):
        ev = fab.append("L10", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_10").state
    assert st["total"] == 8
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_10"] == 8

def test_kind_counter_projection_11():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_11"))
    hub.add(LastValueProjection(f"lv_11", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_11"))
    fab = OmniFabric()
    for i in range(9):
        ev = fab.append("L11", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_11").state
    assert st["total"] == 9
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_11"] == 9

def test_kind_counter_projection_12():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_12"))
    hub.add(LastValueProjection(f"lv_12", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_12"))
    fab = OmniFabric()
    for i in range(10):
        ev = fab.append("L12", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_12").state
    assert st["total"] == 10
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_12"] == 10

def test_kind_counter_projection_13():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_13"))
    hub.add(LastValueProjection(f"lv_13", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_13"))
    fab = OmniFabric()
    for i in range(11):
        ev = fab.append("L13", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_13").state
    assert st["total"] == 11
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_13"] == 11

def test_kind_counter_projection_14():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_14"))
    hub.add(LastValueProjection(f"lv_14", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_14"))
    fab = OmniFabric()
    for i in range(5):
        ev = fab.append("L14", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_14").state
    assert st["total"] == 5
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_14"] == 5

def test_kind_counter_projection_15():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_15"))
    hub.add(LastValueProjection(f"lv_15", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_15"))
    fab = OmniFabric()
    for i in range(6):
        ev = fab.append("L15", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_15").state
    assert st["total"] == 6
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_15"] == 6

def test_kind_counter_projection_16():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_16"))
    hub.add(LastValueProjection(f"lv_16", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_16"))
    fab = OmniFabric()
    for i in range(7):
        ev = fab.append("L16", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_16").state
    assert st["total"] == 7
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_16"] == 7

def test_kind_counter_projection_17():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_17"))
    hub.add(LastValueProjection(f"lv_17", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_17"))
    fab = OmniFabric()
    for i in range(8):
        ev = fab.append("L17", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_17").state
    assert st["total"] == 8
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_17"] == 8

def test_kind_counter_projection_18():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_18"))
    hub.add(LastValueProjection(f"lv_18", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_18"))
    fab = OmniFabric()
    for i in range(9):
        ev = fab.append("L18", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_18").state
    assert st["total"] == 9
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_18"] == 9

def test_kind_counter_projection_19():
    hub = ProjectionHub()
    hub.add(KindCounterProjection("kc_19"))
    hub.add(LastValueProjection(f"lv_19", key_field="k"))
    hub.add(QuorumAttestationProjection(f"qa_19"))
    fab = OmniFabric()
    for i in range(10):
        ev = fab.append("L19", f"kind{i%3}", {"k": f"key{i%2}", "v": i}, [f"att{i%2}"])
        hub.observe(ev)
    st = hub.get("kc_19").state
    assert st["total"] == 10
    rebuilt = hub.rebuild_all(fab.snapshot_tail())
    assert rebuilt["kc_19"] == 10

def test_merkle_checkpoint_and_inclusion_0():
    fab = OmniFabric()
    for i in range(8):
        fab.append("M0", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=0)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[0].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=0)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_1():
    fab = OmniFabric()
    for i in range(9):
        fab.append("M1", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=1)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[1].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=1)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_2():
    fab = OmniFabric()
    for i in range(10):
        fab.append("M2", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=2)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[2].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=2)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_3():
    fab = OmniFabric()
    for i in range(11):
        fab.append("M3", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=3)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[3].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=3)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_4():
    fab = OmniFabric()
    for i in range(12):
        fab.append("M4", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=4)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[4].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=4)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_5():
    fab = OmniFabric()
    for i in range(8):
        fab.append("M5", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=5)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[0].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=5)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_6():
    fab = OmniFabric()
    for i in range(9):
        fab.append("M6", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=6)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[1].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=6)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_7():
    fab = OmniFabric()
    for i in range(10):
        fab.append("M7", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=7)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[2].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=7)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_8():
    fab = OmniFabric()
    for i in range(11):
        fab.append("M8", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=8)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[3].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=8)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_9():
    fab = OmniFabric()
    for i in range(12):
        fab.append("M9", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=9)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[4].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=9)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_10():
    fab = OmniFabric()
    for i in range(8):
        fab.append("M10", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=10)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[0].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=10)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_11():
    fab = OmniFabric()
    for i in range(9):
        fab.append("M11", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=11)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[1].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=11)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_12():
    fab = OmniFabric()
    for i in range(10):
        fab.append("M12", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=12)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[2].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=12)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_13():
    fab = OmniFabric()
    for i in range(11):
        fab.append("M13", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=13)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[3].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=13)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_merkle_checkpoint_and_inclusion_14():
    fab = OmniFabric()
    for i in range(12):
        fab.append("M14", "evt", {"i": i}, ["q"])
    events = fab.snapshot_tail()
    cp = build_checkpoint(events, tag=14)
    assert cp.leaf_count == len(events)
    book = CheckpointBook()
    book.add(cp)
    assert book.latest().checkpoint_id == cp.checkpoint_id
    proof = inclusion_proof(events, events[4].seq)
    assert verify_inclusion(proof["leaf"], proof["path"], proof["root"])
    window = seal_window(events)
    store = WindowStore()
    store.add(window)
    assert store.verify_links() is True
    seg = seal_segment(events, round=14)
    seg.verify()
    ss = SegmentStore()
    ss.add(seg)
    assert ss.stats()["count"] == 1

def test_omnifabric_service_roundtrip_0():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_0", "test ledger 0")
    rec = svc.subscribe_recorder(f"rec_0")
    for i in range(6):
        ev = svc.append("main_0", f"k{i}", {"i": i, "n": 0}, [f"q{i%2}"])
        assert ev["ledger"] == "main_0"
    assert len(rec.events) == 6
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_0", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 6
    assert st["metrics"]["appends_ok"] == 6
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 6

def test_omnifabric_service_roundtrip_1():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_1", "test ledger 1")
    rec = svc.subscribe_recorder(f"rec_1")
    for i in range(7):
        ev = svc.append("main_1", f"k{i}", {"i": i, "n": 1}, [f"q{i%2}"])
        assert ev["ledger"] == "main_1"
    assert len(rec.events) == 7
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_1", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 7
    assert st["metrics"]["appends_ok"] == 7
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 7

def test_omnifabric_service_roundtrip_2():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_2", "test ledger 2")
    rec = svc.subscribe_recorder(f"rec_2")
    for i in range(8):
        ev = svc.append("main_2", f"k{i}", {"i": i, "n": 2}, [f"q{i%2}"])
        assert ev["ledger"] == "main_2"
    assert len(rec.events) == 8
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_2", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 8
    assert st["metrics"]["appends_ok"] == 8
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 8

def test_omnifabric_service_roundtrip_3():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_3", "test ledger 3")
    rec = svc.subscribe_recorder(f"rec_3")
    for i in range(9):
        ev = svc.append("main_3", f"k{i}", {"i": i, "n": 3}, [f"q{i%2}"])
        assert ev["ledger"] == "main_3"
    assert len(rec.events) == 9
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_3", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 9
    assert st["metrics"]["appends_ok"] == 9
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 9

def test_omnifabric_service_roundtrip_4():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_4", "test ledger 4")
    rec = svc.subscribe_recorder(f"rec_4")
    for i in range(6):
        ev = svc.append("main_4", f"k{i}", {"i": i, "n": 4}, [f"q{i%2}"])
        assert ev["ledger"] == "main_4"
    assert len(rec.events) == 6
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_4", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 6
    assert st["metrics"]["appends_ok"] == 6
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 6

def test_omnifabric_service_roundtrip_5():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_5", "test ledger 5")
    rec = svc.subscribe_recorder(f"rec_5")
    for i in range(7):
        ev = svc.append("main_5", f"k{i}", {"i": i, "n": 5}, [f"q{i%2}"])
        assert ev["ledger"] == "main_5"
    assert len(rec.events) == 7
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_5", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 7
    assert st["metrics"]["appends_ok"] == 7
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 7

def test_omnifabric_service_roundtrip_6():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_6", "test ledger 6")
    rec = svc.subscribe_recorder(f"rec_6")
    for i in range(8):
        ev = svc.append("main_6", f"k{i}", {"i": i, "n": 6}, [f"q{i%2}"])
        assert ev["ledger"] == "main_6"
    assert len(rec.events) == 8
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_6", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 8
    assert st["metrics"]["appends_ok"] == 8
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 8

def test_omnifabric_service_roundtrip_7():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_7", "test ledger 7")
    rec = svc.subscribe_recorder(f"rec_7")
    for i in range(9):
        ev = svc.append("main_7", f"k{i}", {"i": i, "n": 7}, [f"q{i%2}"])
        assert ev["ledger"] == "main_7"
    assert len(rec.events) == 9
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_7", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 9
    assert st["metrics"]["appends_ok"] == 9
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 9

def test_omnifabric_service_roundtrip_8():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_8", "test ledger 8")
    rec = svc.subscribe_recorder(f"rec_8")
    for i in range(6):
        ev = svc.append("main_8", f"k{i}", {"i": i, "n": 8}, [f"q{i%2}"])
        assert ev["ledger"] == "main_8"
    assert len(rec.events) == 6
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_8", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 6
    assert st["metrics"]["appends_ok"] == 6
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 6

def test_omnifabric_service_roundtrip_9():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_9", "test ledger 9")
    rec = svc.subscribe_recorder(f"rec_9")
    for i in range(7):
        ev = svc.append("main_9", f"k{i}", {"i": i, "n": 9}, [f"q{i%2}"])
        assert ev["ledger"] == "main_9"
    assert len(rec.events) == 7
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_9", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 7
    assert st["metrics"]["appends_ok"] == 7
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 7

def test_omnifabric_service_roundtrip_10():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_10", "test ledger 10")
    rec = svc.subscribe_recorder(f"rec_10")
    for i in range(8):
        ev = svc.append("main_10", f"k{i}", {"i": i, "n": 10}, [f"q{i%2}"])
        assert ev["ledger"] == "main_10"
    assert len(rec.events) == 8
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_10", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 8
    assert st["metrics"]["appends_ok"] == 8
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 8

def test_omnifabric_service_roundtrip_11():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_11", "test ledger 11")
    rec = svc.subscribe_recorder(f"rec_11")
    for i in range(9):
        ev = svc.append("main_11", f"k{i}", {"i": i, "n": 11}, [f"q{i%2}"])
        assert ev["ledger"] == "main_11"
    assert len(rec.events) == 9
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_11", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 9
    assert st["metrics"]["appends_ok"] == 9
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 9

def test_omnifabric_service_roundtrip_12():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_12", "test ledger 12")
    rec = svc.subscribe_recorder(f"rec_12")
    for i in range(6):
        ev = svc.append("main_12", f"k{i}", {"i": i, "n": 12}, [f"q{i%2}"])
        assert ev["ledger"] == "main_12"
    assert len(rec.events) == 6
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_12", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 6
    assert st["metrics"]["appends_ok"] == 6
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 6

def test_omnifabric_service_roundtrip_13():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_13", "test ledger 13")
    rec = svc.subscribe_recorder(f"rec_13")
    for i in range(7):
        ev = svc.append("main_13", f"k{i}", {"i": i, "n": 13}, [f"q{i%2}"])
        assert ev["ledger"] == "main_13"
    assert len(rec.events) == 7
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_13", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 7
    assert st["metrics"]["appends_ok"] == 7
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 7

def test_omnifabric_service_roundtrip_14():
    svc = OmniFabricService(hot_cap=64)
    svc.register_ledger("main_14", "test ledger 14")
    rec = svc.subscribe_recorder(f"rec_14")
    for i in range(8):
        ev = svc.append("main_14", f"k{i}", {"i": i, "n": 14}, [f"q{i%2}"])
        assert ev["ledger"] == "main_14"
    assert len(rec.events) == 8
    v = svc.verify(full_evidence=True)
    assert v["report"]["ok"] is True
    q = svc.query(ledger="main_14", limit=3)
    assert len(q["events"]) == 3
    st = svc.status()
    assert st["fabric"]["seq"] == 8
    assert st["metrics"]["appends_ok"] == 8
    cp = svc.checkpoint_tail()
    assert cp["leaf_count"] == 8

def test_query_filters_0():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_1():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_2():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_3():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_4():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_5():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_6():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_7():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_8():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_9():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_10():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_query_filters_11():
    fab = OmniFabric()
    for i in range(20):
        fab.append("A" if i % 2 == 0 else "B", f"k{i%4}", {"i": i}, ["alice"] if i % 3 == 0 else ["bob"])
    r = filter_events(fab.snapshot_tail(), ledger="A", kind="k0", limit=50, newest_first=False)
    assert all(e.ledger == "A" and e.kind == "k0" for e in r.events)
    r2 = query_fabric(fab, attester="alice", limit=10)
    assert all("alice" in e.quorum for e in r2.events)
    spanned = range_by_seq(fab, 5, 10)
    assert [e.seq for e in spanned] == list(range(5, 11))

def test_outbox_reconcile_and_replay_0():
    outbox = FabricOutbox(cap=100)
    fab = OmniFabric(outbox, auto_confirm=False, hot_cap=32)
    for i in range(3):
        fab.append("R0", "k", {"i": i}, [])
    assert outbox.pending_count() == 3
    confirmed = outbox.reconcile()
    assert confirmed == 3
    assert outbox.pending_count() == 0
    # fresh fabric + journaled-only path: use confirmed sink docs N/A;
    # exercise replayer confirm on empty pending
    rep = FabricReplayer(outbox)
    assert rep.confirm_pending() == 0

def test_outbox_reconcile_and_replay_1():
    outbox = FabricOutbox(cap=100)
    fab = OmniFabric(outbox, auto_confirm=False, hot_cap=32)
    for i in range(4):
        fab.append("R1", "k", {"i": i}, [])
    assert outbox.pending_count() == 4
    confirmed = outbox.reconcile()
    assert confirmed == 4
    assert outbox.pending_count() == 0
    # fresh fabric + journaled-only path: use confirmed sink docs N/A;
    # exercise replayer confirm on empty pending
    rep = FabricReplayer(outbox)
    assert rep.confirm_pending() == 0

def test_outbox_reconcile_and_replay_2():
    outbox = FabricOutbox(cap=100)
    fab = OmniFabric(outbox, auto_confirm=False, hot_cap=32)
    for i in range(5):
        fab.append("R2", "k", {"i": i}, [])
    assert outbox.pending_count() == 5
    confirmed = outbox.reconcile()
    assert confirmed == 5
    assert outbox.pending_count() == 0
    # fresh fabric + journaled-only path: use confirmed sink docs N/A;
    # exercise replayer confirm on empty pending
    rep = FabricReplayer(outbox)
    assert rep.confirm_pending() == 0

def test_outbox_reconcile_and_replay_3():
    outbox = FabricOutbox(cap=100)
    fab = OmniFabric(outbox, auto_confirm=False, hot_cap=32)
    for i in range(6):
        fab.append("R3", "k", {"i": i}, [])
    assert outbox.pending_count() == 6
    confirmed = outbox.reconcile()
    assert confirmed == 6
    assert outbox.pending_count() == 0
    # fresh fabric + journaled-only path: use confirmed sink docs N/A;
    # exercise replayer confirm on empty pending
    rep = FabricReplayer(outbox)
    assert rep.confirm_pending() == 0

def test_outbox_reconcile_and_replay_4():
    outbox = FabricOutbox(cap=100)
    fab = OmniFabric(outbox, auto_confirm=False, hot_cap=32)
    for i in range(7):
        fab.append("R4", "k", {"i": i}, [])
    assert outbox.pending_count() == 7
    confirmed = outbox.reconcile()
    assert confirmed == 7
    assert outbox.pending_count() == 0
    # fresh fabric + journaled-only path: use confirmed sink docs N/A;
    # exercise replayer confirm on empty pending
    rep = FabricReplayer(outbox)
    assert rep.confirm_pending() == 0

def test_outbox_reconcile_and_replay_5():
    outbox = FabricOutbox(cap=100)
    fab = OmniFabric(outbox, auto_confirm=False, hot_cap=32)
    for i in range(3):
        fab.append("R5", "k", {"i": i}, [])
    assert outbox.pending_count() == 3
    confirmed = outbox.reconcile()
    assert confirmed == 3
    assert outbox.pending_count() == 0
    # fresh fabric + journaled-only path: use confirmed sink docs N/A;
    # exercise replayer confirm on empty pending
    rep = FabricReplayer(outbox)
    assert rep.confirm_pending() == 0

def test_outbox_reconcile_and_replay_6():
    outbox = FabricOutbox(cap=100)
    fab = OmniFabric(outbox, auto_confirm=False, hot_cap=32)
    for i in range(4):
        fab.append("R6", "k", {"i": i}, [])
    assert outbox.pending_count() == 4
    confirmed = outbox.reconcile()
    assert confirmed == 4
    assert outbox.pending_count() == 0
    # fresh fabric + journaled-only path: use confirmed sink docs N/A;
    # exercise replayer confirm on empty pending
    rep = FabricReplayer(outbox)
    assert rep.confirm_pending() == 0

def test_outbox_reconcile_and_replay_7():
    outbox = FabricOutbox(cap=100)
    fab = OmniFabric(outbox, auto_confirm=False, hot_cap=32)
    for i in range(5):
        fab.append("R7", "k", {"i": i}, [])
    assert outbox.pending_count() == 5
    confirmed = outbox.reconcile()
    assert confirmed == 5
    assert outbox.pending_count() == 0
    # fresh fabric + journaled-only path: use confirmed sink docs N/A;
    # exercise replayer confirm on empty pending
    rep = FabricReplayer(outbox)
    assert rep.confirm_pending() == 0

def test_outbox_reconcile_and_replay_8():
    outbox = FabricOutbox(cap=100)
    fab = OmniFabric(outbox, auto_confirm=False, hot_cap=32)
    for i in range(6):
        fab.append("R8", "k", {"i": i}, [])
    assert outbox.pending_count() == 6
    confirmed = outbox.reconcile()
    assert confirmed == 6
    assert outbox.pending_count() == 0
    # fresh fabric + journaled-only path: use confirmed sink docs N/A;
    # exercise replayer confirm on empty pending
    rep = FabricReplayer(outbox)
    assert rep.confirm_pending() == 0

def test_outbox_reconcile_and_replay_9():
    outbox = FabricOutbox(cap=100)
    fab = OmniFabric(outbox, auto_confirm=False, hot_cap=32)
    for i in range(7):
        fab.append("R9", "k", {"i": i}, [])
    assert outbox.pending_count() == 7
    confirmed = outbox.reconcile()
    assert confirmed == 7
    assert outbox.pending_count() == 0
    # fresh fabric + journaled-only path: use confirmed sink docs N/A;
    # exercise replayer confirm on empty pending
    rep = FabricReplayer(outbox)
    assert rep.confirm_pending() == 0

def test_adapters_batch_persistence_0():
    fab = OmniFabric()
    ev = fab.append("L", "k", {"n": 0}, ["q"])
    z = to_zaibatsu_dict(ev)
    assert from_zaibatsu_dict(z).hash == ev.hash
    rs = to_rs_json(ev)
    assert from_rs_json(rs).seq == ev.seq
    req = wire_append_request({"ledger": "X", "kind": "Y", "payload": {"a": 1}, "quorum": ["z"]})
    assert req["ledger"] == "X"
    batch = append_batch(fab, [BatchItem("L", f"b{i}", {"i": i}, []) for i in range(3)])
    assert batch.admitted == 3
    assert doctrine.SIBLING_MODULE.endswith("OmniFabric")
    with tempfile.TemporaryDirectory() as td:
        log = JsonlEventLog(Path(td) / f"fab_0.jsonl")
        log.append_many(fab.snapshot_tail())
        assert log.verify()["ok"] is True
        assert log.stats()["events"] == fab.current_seq

def test_adapters_batch_persistence_1():
    fab = OmniFabric()
    ev = fab.append("L", "k", {"n": 1}, ["q"])
    z = to_zaibatsu_dict(ev)
    assert from_zaibatsu_dict(z).hash == ev.hash
    rs = to_rs_json(ev)
    assert from_rs_json(rs).seq == ev.seq
    req = wire_append_request({"ledger": "X", "kind": "Y", "payload": {"a": 1}, "quorum": ["z"]})
    assert req["ledger"] == "X"
    batch = append_batch(fab, [BatchItem("L", f"b{i}", {"i": i}, []) for i in range(3)])
    assert batch.admitted == 3
    assert doctrine.SIBLING_MODULE.endswith("OmniFabric")
    with tempfile.TemporaryDirectory() as td:
        log = JsonlEventLog(Path(td) / f"fab_1.jsonl")
        log.append_many(fab.snapshot_tail())
        assert log.verify()["ok"] is True
        assert log.stats()["events"] == fab.current_seq

def test_adapters_batch_persistence_2():
    fab = OmniFabric()
    ev = fab.append("L", "k", {"n": 2}, ["q"])
    z = to_zaibatsu_dict(ev)
    assert from_zaibatsu_dict(z).hash == ev.hash
    rs = to_rs_json(ev)
    assert from_rs_json(rs).seq == ev.seq
    req = wire_append_request({"ledger": "X", "kind": "Y", "payload": {"a": 1}, "quorum": ["z"]})
    assert req["ledger"] == "X"
    batch = append_batch(fab, [BatchItem("L", f"b{i}", {"i": i}, []) for i in range(3)])
    assert batch.admitted == 3
    assert doctrine.SIBLING_MODULE.endswith("OmniFabric")
    with tempfile.TemporaryDirectory() as td:
        log = JsonlEventLog(Path(td) / f"fab_2.jsonl")
        log.append_many(fab.snapshot_tail())
        assert log.verify()["ok"] is True
        assert log.stats()["events"] == fab.current_seq

def test_adapters_batch_persistence_3():
    fab = OmniFabric()
    ev = fab.append("L", "k", {"n": 3}, ["q"])
    z = to_zaibatsu_dict(ev)
    assert from_zaibatsu_dict(z).hash == ev.hash
    rs = to_rs_json(ev)
    assert from_rs_json(rs).seq == ev.seq
    req = wire_append_request({"ledger": "X", "kind": "Y", "payload": {"a": 1}, "quorum": ["z"]})
    assert req["ledger"] == "X"
    batch = append_batch(fab, [BatchItem("L", f"b{i}", {"i": i}, []) for i in range(3)])
    assert batch.admitted == 3
    assert doctrine.SIBLING_MODULE.endswith("OmniFabric")
    with tempfile.TemporaryDirectory() as td:
        log = JsonlEventLog(Path(td) / f"fab_3.jsonl")
        log.append_many(fab.snapshot_tail())
        assert log.verify()["ok"] is True
        assert log.stats()["events"] == fab.current_seq

def test_adapters_batch_persistence_4():
    fab = OmniFabric()
    ev = fab.append("L", "k", {"n": 4}, ["q"])
    z = to_zaibatsu_dict(ev)
    assert from_zaibatsu_dict(z).hash == ev.hash
    rs = to_rs_json(ev)
    assert from_rs_json(rs).seq == ev.seq
    req = wire_append_request({"ledger": "X", "kind": "Y", "payload": {"a": 1}, "quorum": ["z"]})
    assert req["ledger"] == "X"
    batch = append_batch(fab, [BatchItem("L", f"b{i}", {"i": i}, []) for i in range(3)])
    assert batch.admitted == 3
    assert doctrine.SIBLING_MODULE.endswith("OmniFabric")
    with tempfile.TemporaryDirectory() as td:
        log = JsonlEventLog(Path(td) / f"fab_4.jsonl")
        log.append_many(fab.snapshot_tail())
        assert log.verify()["ok"] is True
        assert log.stats()["events"] == fab.current_seq

def test_adapters_batch_persistence_5():
    fab = OmniFabric()
    ev = fab.append("L", "k", {"n": 5}, ["q"])
    z = to_zaibatsu_dict(ev)
    assert from_zaibatsu_dict(z).hash == ev.hash
    rs = to_rs_json(ev)
    assert from_rs_json(rs).seq == ev.seq
    req = wire_append_request({"ledger": "X", "kind": "Y", "payload": {"a": 1}, "quorum": ["z"]})
    assert req["ledger"] == "X"
    batch = append_batch(fab, [BatchItem("L", f"b{i}", {"i": i}, []) for i in range(3)])
    assert batch.admitted == 3
    assert doctrine.SIBLING_MODULE.endswith("OmniFabric")
    with tempfile.TemporaryDirectory() as td:
        log = JsonlEventLog(Path(td) / f"fab_5.jsonl")
        log.append_many(fab.snapshot_tail())
        assert log.verify()["ok"] is True
        assert log.stats()["events"] == fab.current_seq

def test_adapters_batch_persistence_6():
    fab = OmniFabric()
    ev = fab.append("L", "k", {"n": 6}, ["q"])
    z = to_zaibatsu_dict(ev)
    assert from_zaibatsu_dict(z).hash == ev.hash
    rs = to_rs_json(ev)
    assert from_rs_json(rs).seq == ev.seq
    req = wire_append_request({"ledger": "X", "kind": "Y", "payload": {"a": 1}, "quorum": ["z"]})
    assert req["ledger"] == "X"
    batch = append_batch(fab, [BatchItem("L", f"b{i}", {"i": i}, []) for i in range(3)])
    assert batch.admitted == 3
    assert doctrine.SIBLING_MODULE.endswith("OmniFabric")
    with tempfile.TemporaryDirectory() as td:
        log = JsonlEventLog(Path(td) / f"fab_6.jsonl")
        log.append_many(fab.snapshot_tail())
        assert log.verify()["ok"] is True
        assert log.stats()["events"] == fab.current_seq

def test_adapters_batch_persistence_7():
    fab = OmniFabric()
    ev = fab.append("L", "k", {"n": 7}, ["q"])
    z = to_zaibatsu_dict(ev)
    assert from_zaibatsu_dict(z).hash == ev.hash
    rs = to_rs_json(ev)
    assert from_rs_json(rs).seq == ev.seq
    req = wire_append_request({"ledger": "X", "kind": "Y", "payload": {"a": 1}, "quorum": ["z"]})
    assert req["ledger"] == "X"
    batch = append_batch(fab, [BatchItem("L", f"b{i}", {"i": i}, []) for i in range(3)])
    assert batch.admitted == 3
    assert doctrine.SIBLING_MODULE.endswith("OmniFabric")
    with tempfile.TemporaryDirectory() as td:
        log = JsonlEventLog(Path(td) / f"fab_7.jsonl")
        log.append_many(fab.snapshot_tail())
        assert log.verify()["ok"] is True
        assert log.stats()["events"] == fab.current_seq

def test_adapters_batch_persistence_8():
    fab = OmniFabric()
    ev = fab.append("L", "k", {"n": 8}, ["q"])
    z = to_zaibatsu_dict(ev)
    assert from_zaibatsu_dict(z).hash == ev.hash
    rs = to_rs_json(ev)
    assert from_rs_json(rs).seq == ev.seq
    req = wire_append_request({"ledger": "X", "kind": "Y", "payload": {"a": 1}, "quorum": ["z"]})
    assert req["ledger"] == "X"
    batch = append_batch(fab, [BatchItem("L", f"b{i}", {"i": i}, []) for i in range(3)])
    assert batch.admitted == 3
    assert doctrine.SIBLING_MODULE.endswith("OmniFabric")
    with tempfile.TemporaryDirectory() as td:
        log = JsonlEventLog(Path(td) / f"fab_8.jsonl")
        log.append_many(fab.snapshot_tail())
        assert log.verify()["ok"] is True
        assert log.stats()["events"] == fab.current_seq

def test_adapters_batch_persistence_9():
    fab = OmniFabric()
    ev = fab.append("L", "k", {"n": 9}, ["q"])
    z = to_zaibatsu_dict(ev)
    assert from_zaibatsu_dict(z).hash == ev.hash
    rs = to_rs_json(ev)
    assert from_rs_json(rs).seq == ev.seq
    req = wire_append_request({"ledger": "X", "kind": "Y", "payload": {"a": 1}, "quorum": ["z"]})
    assert req["ledger"] == "X"
    batch = append_batch(fab, [BatchItem("L", f"b{i}", {"i": i}, []) for i in range(3)])
    assert batch.admitted == 3
    assert doctrine.SIBLING_MODULE.endswith("OmniFabric")
    with tempfile.TemporaryDirectory() as td:
        log = JsonlEventLog(Path(td) / f"fab_9.jsonl")
        log.append_many(fab.snapshot_tail())
        assert log.verify()["ok"] is True
        assert log.stats()["events"] == fab.current_seq

def test_catalog_and_subscribers_0():
    cat = LedgerCatalog(max_ledgers=50)
    for i in range(10):
        cat.register(f"led_0_{i}", f"d{i}")
    fab = OmniFabric()
    bus = SubscriberBus()
    rec = RecordingObserver()
    bus.subscribe(f"s_0", rec, kinds={"keep"}, ledgers={f"led_0_0"})
    cat.register(f"led_0_0")
    ev1 = fab.append(f"led_0_0", "keep", {"x": 1}, [])
    cat.observe(ev1)
    bus.publish(ev1)
    ev2 = fab.append(f"led_0_0", "drop", {"x": 2}, [])
    bus.publish(ev2)
    assert len(rec.events) == 1
    assert cat.get(f"led_0_0").event_count == 1

def test_catalog_and_subscribers_1():
    cat = LedgerCatalog(max_ledgers=50)
    for i in range(10):
        cat.register(f"led_1_{i}", f"d{i}")
    fab = OmniFabric()
    bus = SubscriberBus()
    rec = RecordingObserver()
    bus.subscribe(f"s_1", rec, kinds={"keep"}, ledgers={f"led_1_0"})
    cat.register(f"led_1_0")
    ev1 = fab.append(f"led_1_0", "keep", {"x": 1}, [])
    cat.observe(ev1)
    bus.publish(ev1)
    ev2 = fab.append(f"led_1_0", "drop", {"x": 2}, [])
    bus.publish(ev2)
    assert len(rec.events) == 1
    assert cat.get(f"led_1_0").event_count == 1

def test_catalog_and_subscribers_2():
    cat = LedgerCatalog(max_ledgers=50)
    for i in range(10):
        cat.register(f"led_2_{i}", f"d{i}")
    fab = OmniFabric()
    bus = SubscriberBus()
    rec = RecordingObserver()
    bus.subscribe(f"s_2", rec, kinds={"keep"}, ledgers={f"led_2_0"})
    cat.register(f"led_2_0")
    ev1 = fab.append(f"led_2_0", "keep", {"x": 1}, [])
    cat.observe(ev1)
    bus.publish(ev1)
    ev2 = fab.append(f"led_2_0", "drop", {"x": 2}, [])
    bus.publish(ev2)
    assert len(rec.events) == 1
    assert cat.get(f"led_2_0").event_count == 1

def test_catalog_and_subscribers_3():
    cat = LedgerCatalog(max_ledgers=50)
    for i in range(10):
        cat.register(f"led_3_{i}", f"d{i}")
    fab = OmniFabric()
    bus = SubscriberBus()
    rec = RecordingObserver()
    bus.subscribe(f"s_3", rec, kinds={"keep"}, ledgers={f"led_3_0"})
    cat.register(f"led_3_0")
    ev1 = fab.append(f"led_3_0", "keep", {"x": 1}, [])
    cat.observe(ev1)
    bus.publish(ev1)
    ev2 = fab.append(f"led_3_0", "drop", {"x": 2}, [])
    bus.publish(ev2)
    assert len(rec.events) == 1
    assert cat.get(f"led_3_0").event_count == 1

def test_catalog_and_subscribers_4():
    cat = LedgerCatalog(max_ledgers=50)
    for i in range(10):
        cat.register(f"led_4_{i}", f"d{i}")
    fab = OmniFabric()
    bus = SubscriberBus()
    rec = RecordingObserver()
    bus.subscribe(f"s_4", rec, kinds={"keep"}, ledgers={f"led_4_0"})
    cat.register(f"led_4_0")
    ev1 = fab.append(f"led_4_0", "keep", {"x": 1}, [])
    cat.observe(ev1)
    bus.publish(ev1)
    ev2 = fab.append(f"led_4_0", "drop", {"x": 2}, [])
    bus.publish(ev2)
    assert len(rec.events) == 1
    assert cat.get(f"led_4_0").event_count == 1

def test_catalog_and_subscribers_5():
    cat = LedgerCatalog(max_ledgers=50)
    for i in range(10):
        cat.register(f"led_5_{i}", f"d{i}")
    fab = OmniFabric()
    bus = SubscriberBus()
    rec = RecordingObserver()
    bus.subscribe(f"s_5", rec, kinds={"keep"}, ledgers={f"led_5_0"})
    cat.register(f"led_5_0")
    ev1 = fab.append(f"led_5_0", "keep", {"x": 1}, [])
    cat.observe(ev1)
    bus.publish(ev1)
    ev2 = fab.append(f"led_5_0", "drop", {"x": 2}, [])
    bus.publish(ev2)
    assert len(rec.events) == 1
    assert cat.get(f"led_5_0").event_count == 1

def test_catalog_and_subscribers_6():
    cat = LedgerCatalog(max_ledgers=50)
    for i in range(10):
        cat.register(f"led_6_{i}", f"d{i}")
    fab = OmniFabric()
    bus = SubscriberBus()
    rec = RecordingObserver()
    bus.subscribe(f"s_6", rec, kinds={"keep"}, ledgers={f"led_6_0"})
    cat.register(f"led_6_0")
    ev1 = fab.append(f"led_6_0", "keep", {"x": 1}, [])
    cat.observe(ev1)
    bus.publish(ev1)
    ev2 = fab.append(f"led_6_0", "drop", {"x": 2}, [])
    bus.publish(ev2)
    assert len(rec.events) == 1
    assert cat.get(f"led_6_0").event_count == 1

def test_catalog_and_subscribers_7():
    cat = LedgerCatalog(max_ledgers=50)
    for i in range(10):
        cat.register(f"led_7_{i}", f"d{i}")
    fab = OmniFabric()
    bus = SubscriberBus()
    rec = RecordingObserver()
    bus.subscribe(f"s_7", rec, kinds={"keep"}, ledgers={f"led_7_0"})
    cat.register(f"led_7_0")
    ev1 = fab.append(f"led_7_0", "keep", {"x": 1}, [])
    cat.observe(ev1)
    bus.publish(ev1)
    ev2 = fab.append(f"led_7_0", "drop", {"x": 2}, [])
    bus.publish(ev2)
    assert len(rec.events) == 1
    assert cat.get(f"led_7_0").event_count == 1

def test_catalog_and_subscribers_8():
    cat = LedgerCatalog(max_ledgers=50)
    for i in range(10):
        cat.register(f"led_8_{i}", f"d{i}")
    fab = OmniFabric()
    bus = SubscriberBus()
    rec = RecordingObserver()
    bus.subscribe(f"s_8", rec, kinds={"keep"}, ledgers={f"led_8_0"})
    cat.register(f"led_8_0")
    ev1 = fab.append(f"led_8_0", "keep", {"x": 1}, [])
    cat.observe(ev1)
    bus.publish(ev1)
    ev2 = fab.append(f"led_8_0", "drop", {"x": 2}, [])
    bus.publish(ev2)
    assert len(rec.events) == 1
    assert cat.get(f"led_8_0").event_count == 1

def test_catalog_and_subscribers_9():
    cat = LedgerCatalog(max_ledgers=50)
    for i in range(10):
        cat.register(f"led_9_{i}", f"d{i}")
    fab = OmniFabric()
    bus = SubscriberBus()
    rec = RecordingObserver()
    bus.subscribe(f"s_9", rec, kinds={"keep"}, ledgers={f"led_9_0"})
    cat.register(f"led_9_0")
    ev1 = fab.append(f"led_9_0", "keep", {"x": 1}, [])
    cat.observe(ev1)
    bus.publish(ev1)
    ev2 = fab.append(f"led_9_0", "drop", {"x": 2}, [])
    bus.publish(ev2)
    assert len(rec.events) == 1
    assert cat.get(f"led_9_0").event_count == 1
