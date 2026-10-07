"""Deterministic sandboxed RL environment contracts for VOL-150."""
from __future__ import annotations
from dataclasses import dataclass
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$");_SHA=re.compile(r"^[0-9a-f]{64}$")
class RLError(ValueError): pass
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v): raise RLError(f"{f} must be stable identifier")
 return v
def _sha(v,f):
 if not isinstance(v,str) or not _SHA.fullmatch(v): raise RLError(f"{f} must be sha256")
 return v
@dataclass(frozen=True,slots=True)
class RLEnvironment:
 environment_id:str;version:int;reward_logic_digest:str;sandbox_digest:str;max_steps:int
 def __post_init__(self):
  object.__setattr__(self,"environment_id",_id(self.environment_id,"environment_id"))
  if self.version<1 or self.max_steps<1: raise RLError("version/max_steps must be positive")
  _sha(self.reward_logic_digest,"reward_logic_digest");_sha(self.sandbox_digest,"sandbox_digest")
@dataclass(frozen=True,slots=True)
class Episode:
 episode_id:str;environment_id:str;environment_version:int;seed:int;step:int=0;terminated:bool=False
 def __post_init__(self):
  object.__setattr__(self,"episode_id",_id(self.episode_id,"episode_id"));object.__setattr__(self,"environment_id",_id(self.environment_id,"environment_id"))
  if self.seed<0 or self.step<0: raise RLError("seed/step invalid")
@dataclass(frozen=True,slots=True)
class RewardSignal:
 episode_id:str;step:int;value:float;reward_logic_digest:str;components:tuple[tuple[str,float],...]
 def __post_init__(self):
  object.__setattr__(self,"episode_id",_id(self.episode_id,"episode_id"));_sha(self.reward_logic_digest,"reward_logic_digest")
class EpisodeRuntime:
 def __init__(self,environment):self.environment=environment
 def validate_reward(self,episode,reward):
  if episode.environment_id!=self.environment.environment_id or episode.environment_version!=self.environment.version: raise RLError("environment identity mismatch")
  if episode.terminated or episode.step>=self.environment.max_steps: raise RLError("episode terminated")
  if reward.episode_id!=episode.episode_id or reward.step!=episode.step: raise RLError("reward/episode mismatch")
  if reward.reward_logic_digest!=self.environment.reward_logic_digest: raise RLError("reward logic drift")
  names=[k for k,_ in reward.components]
  if len(names)!=len(set(names)): raise RLError("duplicate reward component")
  return True