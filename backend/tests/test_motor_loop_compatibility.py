"""Regression for the shared Motor client's cached, closed asyncio loop.

Only the I/O loop accessor is exercised: no database process, credentials or
network calls are required. All three canonical databases stay on one client.
"""

from __future__ import annotations

import asyncio

from core.databases import client, content_db, core_db, swarm_db


def test_mongo_operations_follow_current_loop_after_restarts() -> None:
    async def check_loop():
        current = asyncio.get_running_loop()
        assert client.get_io_loop() is current
        assert core_db.get_io_loop() is current
        assert content_db.get_io_loop() is current
        assert swarm_db.get_io_loop() is current
        return current

    first = asyncio.run(check_loop())
    assert first.is_closed()
    second = asyncio.run(check_loop())
    assert second.is_closed()
    assert first is not second


def test_single_canonical_motor_client_retained() -> None:
    assert core_db.client is client
    assert content_db.client is client
    assert swarm_db.client is client
