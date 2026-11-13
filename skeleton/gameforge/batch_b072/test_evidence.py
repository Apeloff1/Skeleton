import pytest

from skeleton.gameforge.batch_b072 import EvidenceError, FailureEvidence, InputRecorder, replay, state_hash


def _init(seed):
    return {"x": seed % 10, "t": 0}


def _step(s, tick, inp):
    s = dict(s)
    s["t"] = tick
    if inp == "R":
        s["x"] += 1
    elif inp == "L":
        s["x"] -= 1
    return s


def _record(seed=13):
    rec = InputRecorder("test_walk", seed)
    s = _init(seed)
    script = {1: "R", 2: "R", 4: "L"}
    for tick in range(6):
        inp = script.get(tick)
        if inp:
            rec.record_input(tick, inp)
        s = _step(s, tick, inp)
        if tick % 2 == 1:
            rec.checkpoint(tick, s)
    return rec, s


def test_state_hash_canonical():
    assert state_hash({"a": 1, "b": 2}) == state_hash({"b": 2, "a": 1})
    with pytest.raises(EvidenceError):
        state_hash({"x": object()})


def test_roundtrip_compact_and_replay():
    rec, final = _record()
    blob = rec.evidence("boom").to_compact()
    ev = FailureEvidence.from_compact(blob)
    assert ev.message == "boom" and ev.seed == 13
    assert replay(ev, _init, _step, 5) == final
    assert len(blob) < 400


def test_replay_detects_divergence():
    rec, _ = _record()
    ev = rec.evidence()
    with pytest.raises(EvidenceError, match="divergence"):
        replay(ev, lambda seed: {"x": 99, "t": 0}, _step, 5)


def test_rejects_corrupt_and_out_of_order():
    with pytest.raises(EvidenceError):
        FailureEvidence.from_compact("not-a-blob")
    rec = InputRecorder("t", 1)
    rec.record_input(5, "R")
    with pytest.raises(EvidenceError):
        rec.record_input(2, "L")
