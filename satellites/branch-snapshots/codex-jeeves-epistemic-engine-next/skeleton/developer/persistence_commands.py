"""
Skeleton Developer CLI — Persistence commands

Provides:
- snapshot: Save memory plane state (rag/mag/kag) to disk
- restore: Boot and restore from a named snapshot
- snapshots: List available snapshots

Registered into the dev command registry as first-class commands.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List


class SnapshotCommand:
    """skeleton dev snapshot — Save memory plane state."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev snapshot")
        parser.add_argument("--name", default="genesis", help="Snapshot name")
        parser.add_argument("--root", help="Snapshot directory (default: .skeleton/snapshots)")
        parser.add_argument("--ingest", help="Text file to ingest before snapshotting")
        parsed = parser.parse_args(args)

        from skeleton.deploy.harness import Harness

        harness = Harness(seed=42, snapshot_root=parsed.root)
        harness.boot(restore=True)  # restore existing state first, so snapshots are cumulative

        ingested = 0
        if parsed.ingest:
            text = Path(parsed.ingest).read_text()
            ingested = harness.genesis.get("quad").ingest_document(Path(parsed.ingest).stem, text)

        captured = harness.snapshot_state(name=parsed.name)

        return {
            "action": "snapshot",
            "name": parsed.name,
            "planes": captured["planes"],
            "ingested_chunks": ingested,
        }


class RestoreCommand:
    """skeleton dev restore — Boot and restore from snapshot."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev restore")
        parser.add_argument("--name", default="genesis", help="Snapshot name")
        parser.add_argument("--root", help="Snapshot directory")
        parsed = parser.parse_args(args)

        from skeleton.deploy.harness import Harness

        harness = Harness(seed=42, snapshot_root=parsed.root)
        harness.boot(restore=False)
        restored = harness.restore_state(name=parsed.name)

        kag = harness.genesis.get("quad")._planes.get("kag")
        return {
            "action": "restore",
            "name": parsed.name,
            "restored": restored,
            "live": {
                "rag_docs": len(harness.genesis.get("rag")._entries),
                "kag_triples": kag.graph.stats()["triples"] if kag else 0,
                "mag_episodes": len(harness.genesis.get("mag")._episodes),
            },
        }


class SnapshotsCommand:
    """skeleton dev snapshots — List available snapshots."""

    def __call__(self, args: List[str]) -> Dict[str, Any]:
        parser = argparse.ArgumentParser(prog="skeleton dev snapshots")
        parser.add_argument("--root", help="Snapshot directory")
        parsed = parser.parse_args(args)

        from skeleton.persistence import SnapshotStore

        store = SnapshotStore(parsed.root) if parsed.root else SnapshotStore()
        snapshots = store.list()

        if not snapshots:
            print("No snapshots found. Run: skeleton dev snapshot --name <name>")
        else:
            print(f"{len(snapshots)} snapshot(s):")
            for s in snapshots:
                import datetime
                ts = datetime.datetime.fromtimestamp(s["saved_at"]).strftime("%Y-%m-%d %H:%M:%S")
                print(f"  {s['name']:<24} saved {ts}")

        return {"snapshots": snapshots, "count": len(snapshots)}
