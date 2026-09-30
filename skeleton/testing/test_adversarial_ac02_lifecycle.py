from __future__ import annotations
from dataclasses import dataclass
import pytest

@dataclass
class DrainController:
    state: str = "running"
    committed: int = 0
    pending: list[str] | None = None
    def __post_init__(self) -> None:
        self.pending = [] if self.pending is None else list(self.pending)
    def submit(self, effect_id: str) -> None:
        if self.state != "running":
            raise RuntimeError("shutdown has fenced new work")
        if effect_id not in self.pending:
            self.pending.append(effect_id)
    def begin_shutdown(self) -> None:
        if self.state == "running":
            self.state = "draining"
    def commit_next(self) -> str | None:
        if not self.pending:
            if self.state == "draining":
                self.state = "stopped"
            return None
        effect_id = self.pending.pop(0)
        self.committed += 1
        return effect_id
    def restart(self) -> None:
        if self.state != "stopped":
            raise RuntimeError("restart requires a completed drain")
        self.state = "running"

def test_shutdown_fences_new_effects_and_drains_existing_work() -> None:
    ctl = DrainController()
    ctl.submit("a"); ctl.submit("b"); ctl.begin_shutdown()
    with pytest.raises(RuntimeError, match="fenced"): ctl.submit("c")
    assert ctl.commit_next() == "a"
    assert ctl.commit_next() == "b"
    assert ctl.commit_next() is None
    assert ctl.state == "stopped"
    assert ctl.committed == 2

def test_shutdown_is_idempotent_and_does_not_duplicate_commits() -> None:
    ctl = DrainController()
    ctl.submit("a"); ctl.begin_shutdown(); ctl.begin_shutdown()
    assert ctl.commit_next() == "a"
    assert ctl.commit_next() is None
    assert ctl.committed == 1
    assert ctl.pending == []

def test_restart_requires_quiescent_boundary() -> None:
    ctl = DrainController()
    ctl.submit("a"); ctl.begin_shutdown()
    with pytest.raises(RuntimeError, match="completed drain"): ctl.restart()
    assert ctl.commit_next() == "a"
    assert ctl.commit_next() is None
    ctl.restart()
    assert ctl.state == "running"
    ctl.submit("b")
    assert ctl.pending == ["b"]

def test_restart_after_drain_accepts_new_work_once() -> None:
    ctl = DrainController()
    ctl.submit("before"); ctl.begin_shutdown()
    assert ctl.commit_next() == "before"
    assert ctl.commit_next() is None
    ctl.restart(); ctl.submit("after")
    assert ctl.pending == ["after"]
    assert ctl.committed == 1
