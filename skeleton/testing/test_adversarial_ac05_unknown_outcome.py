from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Effect:
    committed: bool = False
    receipt: str | None = None


class Remote:
    def __init__(self) -> None:
        self.effect = Effect()
        self.calls = 0

    def commit(self, request_id: str) -> None:
        self.calls += 1
        if not self.effect.committed:
            self.effect.committed = True
            self.effect.receipt = request_id
        raise TimeoutError("response lost after commit")

    def inspect(self, request_id: str) -> str | None:
        if self.effect.committed and self.effect.receipt == request_id:
            return self.effect.receipt
        return None


def execute(remote: Remote, request_id: str) -> str:
    try:
        remote.commit(request_id)
    except TimeoutError:
        receipt = remote.inspect(request_id)
        if receipt is None:
            raise RuntimeError("unknown outcome; reconciliation required")
        return receipt
    raise AssertionError("commit must not return normally in this fault model")


def test_timeout_after_commit_reconciles_without_retry():
    remote = Remote()
    receipt = execute(remote, "req-1")
    assert receipt == "req-1"
    assert remote.calls == 1
    assert remote.effect.committed is True


def test_unknown_outcome_blocks_blind_retry():
    class NoState(Remote):
        def inspect(self, request_id: str) -> str | None:
            return None

    remote = NoState()
    try:
        execute(remote, "req-2")
    except RuntimeError as exc:
        assert "reconciliation required" in str(exc)
    else:
        raise AssertionError("unknown outcome was retried or accepted")


def test_replay_is_idempotent_by_request_id():
    remote = Remote()
    assert execute(remote, "req-3") == "req-3"
    # A recovered receipt is authoritative; replay must not create a second effect.
    assert remote.inspect("req-3") == "req-3"
    assert remote.calls == 1
