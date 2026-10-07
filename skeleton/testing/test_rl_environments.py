from __future__ import annotations
import hashlib,pytest
from skeleton.training.rl_environment import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def env(): return RLEnvironment("ENV.1",2,S("reward-v2"),S("sandbox"),100)
def ep(): return Episode("EPISODE.1","ENV.1",2,42,3)
def reward(**kw):
 v=dict(episode_id="EPISODE.1",step=3,value=1.0,reward_logic_digest=S("reward-v2"),components=(("task",1.0),));v.update(kw);return RewardSignal(**v)
def test_reproducible_episode_binds_environment_version_seed_and_reward(): assert EpisodeRuntime(env()).validate_reward(ep(),reward())
def test_reward_logic_drift_rejected():
 with pytest.raises(RLError,match="reward logic"): EpisodeRuntime(env()).validate_reward(ep(),reward(reward_logic_digest=S("hacked")))
def test_cross_episode_reward_rejected():
 with pytest.raises(RLError,match="mismatch"): EpisodeRuntime(env()).validate_reward(ep(),reward(episode_id="EPISODE.2"))
def test_step_limit_prevents_unbounded_episode():
 with pytest.raises(RLError,match="terminated"): EpisodeRuntime(env()).validate_reward(Episode("EPISODE.1","ENV.1",2,42,100),reward(step=100))
def test_duplicate_reward_components_rejected():
 with pytest.raises(RLError,match="duplicate"): EpisodeRuntime(env()).validate_reward(ep(),reward(components=(("task",1.0),("task",2.0))))