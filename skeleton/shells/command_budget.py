"""Per-command aggregate execution budgets across sessions."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

@dataclass(frozen=True)
class CommandBudgetPolicy:
    max_starts:int=1000
    max_failures:int=100
    max_runtime_ms:float=3_600_000
    max_output_bytes:int=128*1024*1024
    window_seconds:float=3600.0

    def __post_init__(self)->None:
        if self.max_starts<0 or self.max_failures<0 or self.max_runtime_ms<0 or self.max_output_bytes<0:
            raise ValueError("command budget limits may not be negative")
        if self.window_seconds<=0:
            raise ValueError("window_seconds must be positive")

@dataclass(frozen=True)
class CommandBudgetUsage:
    window_started_at:float
    starts:int=0
    failures:int=0
    runtime_ms:float=0.0
    output_bytes:int=0

    def to_dict(self)->dict[str,int|float]:
        return {
            "window_started_at":self.window_started_at,
            "starts":self.starts,
            "failures":self.failures,
            "runtime_ms":self.runtime_ms,
            "output_bytes":self.output_bytes,
        }

@dataclass(frozen=True)
class CommandBudgetDecision:
    allowed:bool
    reason:str
    retry_after_seconds:float
    usage:CommandBudgetUsage

class CommandBudgets:
    def __init__(
        self,
        default:CommandBudgetPolicy|None=None,
        *,
        clock:Callable[[],float]=time.monotonic,
        max_commands:int=4096,
    )->None:
        self.default=default or CommandBudgetPolicy()
        self._clock=clock
        self.max_commands=max_commands
        self._policies:dict[str,CommandBudgetPolicy]={}
        self._usage:dict[str,CommandBudgetUsage]={}
        self._lock=threading.RLock()

    def set_policy(self,command:str,policy:CommandBudgetPolicy)->None:
        if not command or len(command)>128:
            raise ValueError("invalid command")
        with self._lock:
            self._policies[command]=policy

    def policy(self,command:str)->CommandBudgetPolicy:
        return self._policies.get(command,self.default)

    def _current(self,command:str)->CommandBudgetUsage:
        now=self._clock()
        usage=self._usage.get(command)
        policy=self.policy(command)
        if usage is None:
            if len(self._usage)>=self.max_commands:
                raise RuntimeError("command budget cardinality exhausted")
            usage=CommandBudgetUsage(now)
            self._usage[command]=usage
        elif now-usage.window_started_at>=policy.window_seconds:
            usage=CommandBudgetUsage(now)
            self._usage[command]=usage
        return usage

    def inspect(self,command:str)->CommandBudgetDecision:
        with self._lock:
            usage=self._current(command)
            policy=self.policy(command)
            retry=max(0.0,policy.window_seconds-(self._clock()-usage.window_started_at))
            checks=(
                (usage.starts>=policy.max_starts,"start budget exhausted"),
                (usage.failures>=policy.max_failures,"failure budget exhausted"),
                (usage.runtime_ms>=policy.max_runtime_ms,"runtime budget exhausted"),
                (usage.output_bytes>=policy.max_output_bytes,"output budget exhausted"),
            )
            for denied,reason in checks:
                if denied:
                    return CommandBudgetDecision(False,reason,retry,usage)
            return CommandBudgetDecision(True,"allowed",0.0,usage)

    def reserve_start(self,command:str)->CommandBudgetUsage:
        with self._lock:
            decision=self.inspect(command)
            if not decision.allowed:
                raise RuntimeError(decision.reason)
            usage=decision.usage
            updated=CommandBudgetUsage(
                usage.window_started_at,usage.starts+1,usage.failures,
                usage.runtime_ms,usage.output_bytes,
            )
            self._usage[command]=updated
            return updated

    def record_result(self,command:str,*,ok:bool,runtime_ms:float,output_bytes:int)->CommandBudgetUsage:
        if runtime_ms<0 or output_bytes<0:
            raise ValueError("result metrics may not be negative")
        with self._lock:
            usage=self._current(command)
            updated=CommandBudgetUsage(
                usage.window_started_at,usage.starts,
                usage.failures+(0 if ok else 1),
                usage.runtime_ms+runtime_ms,
                usage.output_bytes+output_bytes,
            )
            self._usage[command]=updated
            return updated

    def snapshot(self)->dict[str,CommandBudgetUsage]:
        with self._lock:
            return {command:self._current(command) for command in sorted(self._usage)}
