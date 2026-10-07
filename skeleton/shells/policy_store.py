"""Revisioned compare-and-swap store for immutable ShellPolicy objects."""

from __future__ import annotations

from dataclasses import dataclass
import threading

from skeleton.shells.provenance import policy_fingerprint
from skeleton.shells.runner import ShellPolicy


@dataclass(frozen=True)
class PolicyRevision:
    revision:int
    fingerprint:str
    policy:ShellPolicy

    def to_dict(self)->dict[str,object]:
        return {"revision":self.revision,"fingerprint":self.fingerprint}


class PolicyConflict(RuntimeError):pass


class PolicyStore:
    def __init__(self,initial:ShellPolicy)->None:
        self._current=PolicyRevision(1,policy_fingerprint(
            initial.executables,
            initial.cwd_roots,
            allowed_env=tuple(initial.allowed_env),
            inherited_env=tuple(initial.inherited_env),
            limits={
                "default_timeout": initial.default_timeout,
                "max_timeout": initial.max_timeout,
                "max_output_bytes": initial.max_output_bytes,
                "max_input_bytes": initial.max_input_bytes,
                "max_env_bytes": initial.max_env_bytes,
                "max_args": initial.max_args,
                "max_arg_bytes": initial.max_arg_bytes,
            },
        ),initial)
        self._history=[self._current]
        self._lock=threading.RLock()

    def current(self)->PolicyRevision:
        with self._lock:return self._current

    def compare_and_swap(self,expected_revision:int,policy:ShellPolicy)->PolicyRevision:
        with self._lock:
            if self._current.revision!=expected_revision:
                raise PolicyConflict("shell policy revision conflict")
            replacement=PolicyRevision(
                self._current.revision+1,
                policy_fingerprint(
                policy.executables,
                policy.cwd_roots,
                allowed_env=tuple(policy.allowed_env),
                inherited_env=tuple(policy.inherited_env),
                limits={
                    "default_timeout": policy.default_timeout,
                    "max_timeout": policy.max_timeout,
                    "max_output_bytes": policy.max_output_bytes,
                    "max_input_bytes": policy.max_input_bytes,
                    "max_env_bytes": policy.max_env_bytes,
                    "max_args": policy.max_args,
                    "max_arg_bytes": policy.max_arg_bytes,
                },
            ),
                policy,
            )
            self._current=replacement
            self._history.append(replacement)
            return replacement

    def replace(self,policy:ShellPolicy)->PolicyRevision:
        with self._lock:return self.compare_and_swap(self._current.revision,policy)

    def at(self,revision:int)->PolicyRevision:
        with self._lock:
            if revision<=0 or revision>len(self._history):raise KeyError(revision)
            return self._history[revision-1]

    def history(self)->tuple[PolicyRevision,...]:
        with self._lock:return tuple(self._history)
