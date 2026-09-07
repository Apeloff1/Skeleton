#!/usr/bin/env python3
"""
Skeleton Deployment Script

Usage:
    python deploy.py [command] [options]

Commands:
    boot        Boot the full Skeleton system
    serve       Start the API server
    test        Run all tests
    health      Check system health
    scaffold    Create a new project from template
    wizard      Interactive project builder
    snapshot    Save memory plane state to disk
    restore     Boot and restore memory plane state from disk
"""

import argparse
import sys
from pathlib import Path


def cmd_boot(args):
    """Boot the full Skeleton system."""
    from skeleton.deploy.harness import Harness

    harness = Harness(seed=args.seed, snapshot_root=args.snapshot_root)
    harness.boot(restore=args.restore)

    if args.materialize:
        result = harness.materialize(args.materialize, era=args.era, target=args.target)
        print(f"Materialized: {result.get('blueprint_id', 'N/A')}")

    if args.serve:
        harness.serve(host=args.host, port=args.port)
        harness.run()  # Block until signal
    else:
        health = harness.health()
        print(f"System health: {health['status']}")
        print(f"Handles wired: {len(health['handles'])}")
        return 0 if health['status'] == 'healthy' else 1


def cmd_serve(args):
    """Start the API server."""
    from skeleton.api.server import run_server

    print(f"Starting Skeleton API server on {args.host}:{args.port}")
    run_server(host=args.host, port=args.port)
    return 0


def cmd_test(args):
    """Run the test suite."""
    import unittest

    loader = unittest.TestLoader()

    if args.test:
        suite = loader.loadTestsFromName(args.test)
    else:
        suite = loader.discover("skeleton/testing", pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=args.verbose)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


def cmd_health(args):
    """Check system health."""
    from skeleton.genesis import Genesis

    genesis = Genesis(seed=42).boot()
    health = genesis.health()

    print(f"Overall: {'HEALTHY' if health['healthy'] else 'DEGRADED'}")
    print(f"Phases: {', '.join(health['phases'])}")
    print(f"Subsystems: {health['subsystems']}")
    print(f"Invariant violations: {health['invariant_violations']}")

    if args.verbose:
        print(f"\nBus stats: {health['bus']}")

    return 0 if health['healthy'] else 1


def cmd_scaffold(args):
    """Scaffold a new project."""
    from skeleton.developer.scaffold import ScaffoldEngine

    engine = ScaffoldEngine(output_dir=args.output)
    result = engine.create_project(args.template, args.name, force=args.force)
    print(result)
    return 0


def cmd_wizard(args):
    """Run the interactive wizard."""
    from skeleton.developer.wizard import Wizard, WizardMode

    mode_map = {
        'full': WizardMode.FULL,
        'quick': WizardMode.QUICK,
        'expert': WizardMode.EXPERT,
    }

    mode = mode_map.get(args.mode, WizardMode.FULL)
    wizard = Wizard(mode=mode)
    result = wizard.run()
    print(result)
    return 0


def cmd_snapshot(args):
    """Boot, populate from an optional seed file, and snapshot state."""
    from skeleton.deploy.harness import Harness

    harness = Harness(seed=args.seed, snapshot_root=args.snapshot_root)
    harness.boot(restore=args.restore_first)

    if args.ingest:
        quad = harness.genesis.get("quad")
        text = Path(args.ingest).read_text()
        chunks = quad.ingest_document(Path(args.ingest).stem, text)
        print(f"Ingested {chunks} chunk(s) from {args.ingest}")

    captured = harness.snapshot_state(name=args.name)
    print(f"Snapshot '{captured['name']}': {captured['planes']}")
    return 0


def cmd_restore(args):
    """Boot and restore state, then report what's live."""
    from skeleton.deploy.harness import Harness

    harness = Harness(seed=args.seed, snapshot_root=args.snapshot_root)
    harness.boot(restore=False)
    restored = harness.restore_state(name=args.name)
    print(f"Restored: {restored}")

    quad = harness.genesis.get("quad")
    kag = quad._planes.get("kag")
    print(f"Live planes: rag={len(harness.genesis.get('rag')._entries)} docs, "
          f"kag={kag.graph.stats()['triples'] if kag else 0} triples, "
          f"mag={len(harness.genesis.get('mag')._episodes)} episodes")
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="deploy.py",
        description="Skeleton Deployment Script"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    boot_parser = subparsers.add_parser("boot", help="Boot the full system")
    boot_parser.add_argument("--seed", type=int, default=42)
    boot_parser.add_argument("--restore", action="store_true", help="Restore state on boot")
    boot_parser.add_argument("--snapshot-root", help="Snapshot directory")
    boot_parser.add_argument("--materialize", help="Blueprint name to materialize")
    boot_parser.add_argument("--era", default="extraction_now")
    boot_parser.add_argument("--target", default="json")
    boot_parser.add_argument("--serve", action="store_true", help="Start API server after boot")
    boot_parser.add_argument("--host", default="0.0.0.0")
    boot_parser.add_argument("--port", type=int, default=8000)

    serve_parser = subparsers.add_parser("serve", help="Start API server")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)

    test_parser = subparsers.add_parser("test", help="Run tests")
    test_parser.add_argument("--test", help="Specific test to run (e.g., TestClass.test_method)")
    test_parser.add_argument("--verbose", "-v", type=int, default=2)

    health_parser = subparsers.add_parser("health", help="Check system health")
    health_parser.add_argument("--verbose", "-v", action="store_true")

    scaffold_parser = subparsers.add_parser("scaffold", help="Create project from template")
    scaffold_parser.add_argument("template", help="Template name")
    scaffold_parser.add_argument("name", help="Project name")
    scaffold_parser.add_argument("--output", "-o", default=".")
    scaffold_parser.add_argument("--force", "-f", action="store_true")

    wizard_parser = subparsers.add_parser("wizard", help="Interactive project builder")
    wizard_parser.add_argument("--mode", choices=["full", "quick", "expert"], default="full")

    snap_parser = subparsers.add_parser("snapshot", help="Save memory plane state")
    snap_parser.add_argument("--seed", type=int, default=42)
    snap_parser.add_argument("--name", default="genesis", help="Snapshot name")
    snap_parser.add_argument("--snapshot-root", help="Snapshot directory")
    snap_parser.add_argument("--ingest", help="Text file to ingest before snapshotting")
    snap_parser.add_argument("--restore-first", action="store_true", help="Restore before adding new content")

    restore_parser = subparsers.add_parser("restore", help="Boot and restore state")
    restore_parser.add_argument("--seed", type=int, default=42)
    restore_parser.add_argument("--name", default="genesis", help="Snapshot name")
    restore_parser.add_argument("--snapshot-root", help="Snapshot directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "boot": cmd_boot,
        "serve": cmd_serve,
        "test": cmd_test,
        "health": cmd_health,
        "scaffold": cmd_scaffold,
        "wizard": cmd_wizard,
        "snapshot": cmd_snapshot,
        "restore": cmd_restore,
    }

    handler = commands.get(args.command)
    if not handler:
        print(f"Unknown command: {args.command}")
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
