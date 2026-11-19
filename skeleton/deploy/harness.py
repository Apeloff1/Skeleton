"""
Skeleton Deployment Harness

Orchestrates the full stack: genesis boot → forge materialization → API server.
Provides lifecycle management, signal handling, and graceful shutdown.
Now with state persistence: boot can restore prior memory planes and
shutdown snapshots them back to disk.

Usage:
    from skeleton.deploy import Harness
    harness = Harness().boot(restore=True).serve().run()
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from typing import Any, Dict, Optional

from skeleton.genesis import Genesis
from skeleton.kernel.events import DomainEvent, EventBus


class Harness:
    """Deployment harness for the full Skeleton stack."""

    def __init__(self, seed: Optional[int] = None, snapshot_name: str = "genesis", snapshot_root: Optional[str] = None):
        self.genesis: Optional[Genesis] = None
        self._bus: Optional[EventBus] = None
        self._shutdown_event = threading.Event()
        self._server_thread: Optional[threading.Thread] = None
        self._seed = seed
        self._snapshot_name = snapshot_name
        self._snapshot_root = snapshot_root

    def boot(self, restore: bool = False) -> "Harness":
        """Boot the genesis protocol, optionally restoring prior state."""
        print("[Harness] Booting Skeleton genesis...")
        self.genesis = Genesis(seed=self._seed).boot()
        self._bus = self.genesis.bus
        print(f"[Harness] Genesis ready: {len(self.genesis.handles)} handles wired")
        print(f"[Harness] Phases: {self.genesis.report.phases}")

        if restore:
            restored = self.restore_state()
            if restored:
                print(f"[Harness] Restored state: {restored}")

        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        return self

    def snapshot_state(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Snapshot memory planes to disk."""
        if self.genesis is None:
            raise RuntimeError("Genesis not booted.")
        from skeleton.persistence import SnapshotStore, snapshot_genesis_state

        store = SnapshotStore(self._snapshot_root) if self._snapshot_root else SnapshotStore()
        captured = snapshot_genesis_state(self.genesis, store=store, name=name or self._snapshot_name)
        print(f"[Harness] State snapshot saved: {captured['planes']}")
        return captured

    def restore_state(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Restore memory planes from disk (no-op when no snapshot exists)."""
        if self.genesis is None:
            raise RuntimeError("Genesis not booted.")
        from skeleton.persistence import SnapshotStore, restore_genesis_state

        store = SnapshotStore(self._snapshot_root) if self._snapshot_root else SnapshotStore()
        restored = restore_genesis_state(self.genesis, store=store, name=name or self._snapshot_name)
        return restored

    def materialize(self, blueprint_name: str, era: str = "extraction_now", target: str = "json") -> Dict[str, Any]:
        """Materialize a blueprint through the forge."""
        if self.genesis is None:
            raise RuntimeError("Genesis not booted. Call boot() first.")

        forge = self.genesis.handles.get("forge")
        if forge is None:
            raise RuntimeError("Forge not wired in genesis.")

        bp = forge.new_blueprint(blueprint_name)
        forge.instantiate(bp, "source", "input")
        forge.instantiate(bp, "transform", "process")
        forge.instantiate(bp, "sink", "output")
        bp.connect(("input", "out"), ("process", "in"))
        bp.connect(("process", "out"), ("output", "in"))

        result = forge.materialise(bp, era=era, target=target)
        print(f"[Harness] Materialized '{blueprint_name}' → {target}")
        return result

    def serve(self, host: str = "0.0.0.0", port: int = 8000) -> "Harness":
        """Start the API server in a background thread."""
        if self.genesis is None:
            raise RuntimeError("Genesis not booted. Call boot() first.")

        try:
            from fastapi import FastAPI
            from uvicorn import Config as UvicornConfig, Server
            from skeleton.api.routes import router
            from skeleton.api.gameforge_routes import router as gameforge_router
            from skeleton.api.server import get_state

            get_state().wire_from_genesis(self.genesis)

            app = FastAPI(title="Skeleton API", version="16.0.0")
            app.include_router(router, prefix="/api/v1")
            app.include_router(gameforge_router, prefix="/api/v1")

            config = UvicornConfig(app, host=host, port=port, log_level="info")
            server = Server(config)

            self._server_thread = threading.Thread(target=server.run, daemon=True)
            self._server_thread.start()

            print(f"[Harness] API server listening on http://{host}:{port}/api/v1")
            print("[Harness] Health check: GET /api/v1/health")

        except ImportError:
            print("[Harness] FastAPI/uvicorn not available. API server skipped.")

        return self

    def run(self, snapshot_on_shutdown: bool = True) -> None:
        """Block until shutdown signal received."""
        print("[Harness] Running. Press Ctrl+C to shutdown.")
        try:
            while not self._shutdown_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown(snapshot=snapshot_on_shutdown)

    def shutdown(self, snapshot: bool = True) -> None:
        """Graceful shutdown, optionally snapshotting state first."""
        print("\n[Harness] Shutting down...")
        self._shutdown_event.set()

        if snapshot and self.genesis is not None:
            try:
                self.snapshot_state()
            except Exception as e:
                print(f"[Harness] Snapshot skipped: {e}")

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="harness.shutdown",
                payload={"handles": list(self.genesis.handles.keys()) if self.genesis else []},
            ))

        print("[Harness] Shutdown complete.")

    def _signal_handler(self, signum, frame) -> None:
        print(f"\n[Harness] Received signal {signum}")
        self.shutdown()
        sys.exit(0)

    def health(self) -> Dict[str, Any]:
        """Full system health check."""
        if self.genesis is None:
            return {"status": "not_booted"}

        genesis_health = self.genesis.health()
        return {
            "status": "healthy" if genesis_health.get("healthy") else "degraded",
            "genesis": genesis_health,
            "handles": list(self.genesis.handles.keys()),
        }
