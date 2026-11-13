"""An accepted live play recovers when its owner's polling observes free capacity."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.game_learning import GameLearningError
from core.game_play import GamePlayAuthority

OWNER = {"tenant_id": "play-tenant", "owner_id": "play-owner"}


class _Plays:
    def __init__(self):
        self.row = {
            "_id": "queued-play", **OWNER, "play_id": "queued-play", "project_id": "project",
            "status": "queued", "cancel_requested": False, "stream_id": "stream",
            "controller": "ai", "execution_kind": "studio", "input": {},
        }

    async def find_one(self, query):
        # Real Mongo yields here, allowing simultaneous browser polls to race.
        await asyncio.sleep(0)
        return deepcopy(self.row) if all(self.row.get(k) == v for k, v in query.items()) else None


def authority():
    app = object.__new__(GamePlayAuthority)
    app.plays = _Plays()
    app.frames = SimpleNamespace(find_one=AsyncMock(return_value=None))
    app.workspace = SimpleNamespace(_authority=AsyncMock())
    app.tasks = {}
    return app


@pytest.mark.asyncio
async def test_owner_poll_retries_accepted_play_after_previous_credit_drains():
    app = authority()
    capacity_held = True
    attempts = []
    running = asyncio.Event()

    async def dispatch(identifier, scope):
        assert identifier == "queued-play" and scope == OWNER
        attempts.append(capacity_held)
        if capacity_held:
            return
        app.plays.row["status"] = "running"
        running.set()

    app._run = dispatch
    # Admission races a previous player's still-live teardown credit.
    await app._schedule("queued-play", OWNER)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert attempts == [True] and not app.tasks
    assert (await app.get(OWNER, "queued-play"))["status"] == "queued"
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert attempts == [True, True] and not app.tasks

    # The next normal product poll resumes the existing intent and uses the
    # same scheduler/identity; it does not require replaying its create command.
    capacity_held = False
    await asyncio.gather(app.get(OWNER, "queued-play"), app.get(OWNER, "queued-play"))
    await asyncio.wait_for(running.wait(), timeout=1)
    await asyncio.sleep(0)
    assert attempts == [True, True, False]
    assert (await app.get(OWNER, "queued-play"))["status"] == "running"


@pytest.mark.asyncio
async def test_foreign_owner_cannot_reconcile_or_dispatch_queued_play():
    app = authority()
    app._run = AsyncMock()
    with pytest.raises(GameLearningError) as failure:
        await app.get({**OWNER, "owner_id": "foreign-owner"}, "queued-play")
    assert failure.value.status == 404
    app._run.assert_not_awaited()
    app.workspace._authority.assert_not_awaited()
    assert not app.tasks


@pytest.mark.asyncio
async def test_revoked_authority_cannot_reconcile_accepted_queued_play():
    app = authority()
    app._run = AsyncMock()
    app.workspace._authority.side_effect = GameLearningError("source_revoked", "Source revoked", 403)
    with pytest.raises(GameLearningError) as failure:
        await app.get(OWNER, "queued-play")
    assert failure.value.status == 403
    app._run.assert_not_awaited()
    assert not app.tasks


@pytest.mark.asyncio
async def test_shorter_play_limit_rejects_policy_before_storage_admission(monkeypatch):
    app = authority()
    app.indexes = AsyncMock()
    app.plays.find_one = AsyncMock(return_value=None)
    app.workspace._project = AsyncMock(return_value={"version": 1})
    app.workspace._input = AsyncMock(return_value={"episode_steps": 8})
    app.workspace.environment_request = AsyncMock(return_value={"kind": "studio"})
    app.workspace._admitted_policy = AsyncMock(return_value={
        "snapshot": {"environment": {"max_episode_steps": 16}},
    })
    app.workspace._admit = AsyncMock()
    monkeypatch.setattr("core.game_play.resource_profiles", lambda: {"profiles": [{"available": True}]})
    with pytest.raises(GameLearningError) as failure:
        await app.create(OWNER, "project", {
            "expected_version": 1, "idempotency_key": "shorter-play", "controller": "ai",
            "policy_id": "policy", "max_steps": 8,
        })
    assert failure.value.code == "policy_environment_mismatch"
    assert failure.value.status == 409
    app.workspace._admit.assert_not_awaited()
    app.workspace.environment_request.assert_awaited_once()
    assert not app.tasks
