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
