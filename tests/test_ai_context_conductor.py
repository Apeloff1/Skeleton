"""Focused tests for the AI-tree context conductor."""
from __future__ import annotations

import asyncio

from skeleton.context.conductor import (
    OmegaUltraConductor,
    RepetitionError,
    UserToJeevesConductor,
)


def test_begin_deliver_purge_and_never_repeat() -> None:
    async def run() -> None:
        c = OmegaUltraConductor(node_id="test", keep_full=5)
        start = await c.begin("pages", 10, fresh=True)
        assert start["stored_prose"] == 0
        assert start["active"] is True

        for i in range(1, 8):
            card = await c.deliver_context(f"unique page {i} body")
            assert card["hit"] is True
            assert card["seq"] == i

        assert c.pagecount[-1]["progress"] == 7.0
        assert sum(1 for d in c.deliveries if d.full_content is not None) == 5
        assert all(d.full_content is None for d in c.deliveries[:2])

        try:
            await c.deliver_context("unique page 3 body")
            raise AssertionError("repeat must raise")
        except RepetitionError:
            pass

        bar = c.progress_bar("context", width=10)
        assert bar.startswith("[")
        end = await c.end()
        assert end["event"] == "end"
        assert c._active is False

    asyncio.run(run())


def test_user_to_jeeves_interprets_pages_and_wipe() -> None:
    async def run() -> None:
        u = UserToJeevesConductor(node_id="jeeves")
        card = await u.interpret_and_begin("Write an 8-page report")
        assert card["mode"] == "pages"
        assert card["total"] == 8.0
        await u.user_message("user start")
        await u.jeeves_reply("jeeves page one")
        wiped = await u.wipe_and_restart()
        assert wiped["seq"] == 0
        assert wiped["unique"] == 0
        assert u.pagecount == []

    asyncio.run(run())


def test_ai_tree_mirror_is_importable() -> None:
    from skeleton.ai.runtime.context import conductor as ai_mod
    from skeleton.context import conductor as src_mod

    assert ai_mod.CONDUCTOR_VERSION == src_mod.CONDUCTOR_VERSION
    assert ai_mod.OmegaUltraConductor is not None
