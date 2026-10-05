from __future__ import annotations
import hashlib
import pytest
from skeleton.ai.evaluation.long_horizon_benchmarks import HorizonCheckpoint,LongHorizonBenchmarkError,LongHorizonEpisode

def d(x): return hashlib.sha256(x.encode()).hexdigest()

def cp(step,progress): return HorizonCheckpoint(step,d(f"s{step}"),d(f"i{step}"),progress)

def test_long_horizon_episode_is_bounded_and_monotonic():
    episode=LongHorizonEpisode("e","scenario",100,(cp(0,0),cp(50,500000),cp(100,1000000)),True,d("accept"))
    assert episode.completed is True
    assert len(episode.digest)==64

def test_checkpoint_progress_cannot_regress():
    with pytest.raises(LongHorizonBenchmarkError,match="progress cannot regress"):
        LongHorizonEpisode("e","s",10,(cp(1,700000),cp(2,600000)),False,d("a"))

def test_checkpoint_cannot_exceed_step_budget():
    with pytest.raises(LongHorizonBenchmarkError,match="exceeds max_steps"):
        LongHorizonEpisode("e","s",10,(cp(11,1000000),),True,d("a"))

def test_completed_episode_requires_full_progress():
    with pytest.raises(LongHorizonBenchmarkError,match="full progress"):
        LongHorizonEpisode("e","s",10,(cp(10,900000),),True,d("a"))
