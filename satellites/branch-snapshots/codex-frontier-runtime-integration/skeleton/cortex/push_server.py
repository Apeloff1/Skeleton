"""Cortex WebSocket handler — push updates for operator dashboard.

Provides async WebSocket-style push of dashboard updates, alerts,
and subsystem cards. Falls back to SSE (Server-Sent Events) if
WebSocket is unavailable. Integrates with the operator dashboard
for real-time operator awareness.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Callable

from skeleton.cortex.operator_dashboard import OperatorDashboard


class DashboardPushServer:
    """Push server for dashboard updates."""

    def __init__(self, dashboard: OperatorDashboard, interval_s: float = 2.0):
        self.dashboard = dashboard
        self.interval_s = interval_s
        self._clients: List[Callable[[Dict[str, Any]], None]] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def connect(self, send_fn: Callable[[Dict[str, Any]], None]) -> None:
        self._clients.append(send_fn)
        send_fn(self.dashboard.card())

    def disconnect(self, send_fn: Callable[[Dict[str, Any]], None]) -> None:
        if send_fn in self._clients:
            self._clients.remove(send_fn)

    async def _loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.interval_s)
            card = self.dashboard.refresh()
            dead: List[Callable[[Dict[str, Any]], None]] = []
            for client in self._clients:
                try:
                    client(card)
                except Exception:
                    dead.append(client)
            for d in dead:
                self.disconnect(d)

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    def broadcast_alert(self, severity: str, subsystem: str, message: str) -> None:
        alert = self.dashboard.fire_alert(severity, subsystem, message)
        payload = {"kind": "alert", "alert": alert.to_dict()}
        dead: List[Callable[[Dict[str, Any]], None]] = []
        for client in self._clients:
            try:
                client(payload)
            except Exception:
                dead.append(client)
        for d in dead:
            self.disconnect(d)

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "push-server-card",
            "clients": len(self._clients),
            "running": self._running,
            "interval_s": self.interval_s,
        }
