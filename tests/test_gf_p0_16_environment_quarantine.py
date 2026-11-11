"""Quarantined environment custody: strict replay data and holdout isolation."""
from __future__ import annotations
import math
import pytest
from skeleton.provider_environment import (
    EnvironmentIdentity, ExactEnvironmentRegistry, EnvironmentMismatchError,
    HoldoutSplit, DeterministicReplayBuffer, make_record, replay_episode, ReplayRecord,
)
from .test_gf_p0_16_environment_replay import ID, SPLIT, _Env


def test_source_and_retained_sample_are_isolated_from_mutable_callers():
    payload = {"nested":{"x":[1]}}
    record = make_record("safe", ID, payload)
    buffer = DeterministicReplayBuffer(SPLIT, max_items=10)
    example = next(f"record-{i}" for i in range(1000) if not SPLIT.is_holdout(f"record-{i}"))
    record = make_record(example, ID, payload)
    buffer.add(record)
    payload["nested"]["x"][0]=999
    record.payload["nested"]["x"][0]=888
    sample=buffer.sample(1,seed=5)[0]
    assert sample.payload["nested"]["x"][0]==1
    sample.payload["nested"]["x"][0]=777
    assert buffer.records()[0].payload["nested"]["x"][0]==1


def test_forged_digest_fails_closed():
    sample=next(f"record-{i}" for i in range(1000) if not SPLIT.is_holdout(f"record-{i}"))
    valid=make_record(sample,ID,{"x":1})
    forged=ReplayRecord(valid.example_id,valid.environment_key,valid.payload_digest,{"x":2})
    buffer=DeterministicReplayBuffer(SPLIT,max_items=10)
    with pytest.raises(ValueError):
        buffer.add(forged)
    assert len(buffer)==0


@pytest.mark.parametrize("item",[float("nan"),float("inf"),object()])
def test_replay_rejects_noncannonical_records(item):
    with pytest.raises(ValueError):
        make_record("x",ID,{"x":item})


def test_replay_nonfinite_split_and_negative_sample_fail():
    for value in (float("nan"),float("inf"),-1.0):
        with pytest.raises(ValueError):
            HoldoutSplit(salt="safe",holdout_fraction=value)
    buffer=DeterministicReplayBuffer(SPLIT,max_items=10)
    with pytest.raises(ValueError):
        buffer.sample(-1,seed=0)


def test_registry_cannot_replace_same_exact_identity():
    registry=ExactEnvironmentRegistry()
    original=_Env()
    registry.register(ID,original)
    with pytest.raises(EnvironmentMismatchError):
        registry.register(ID,_Env())
    assert registry.resolve(ID) is original


def test_unbounded_replay_episode_holds():
    with pytest.raises(ValueError):
        replay_episode(_Env(),({"dx":1} for _ in range(10001)))
