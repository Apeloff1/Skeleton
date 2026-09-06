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
"""

import argparse
import sys
from pathlib import Path


def cmd_boot(args):
    """Boot the full Skeleton system."""
    from skeleton.deploy.harness import Harness
    
    harness = Harness(seed=args.seed)
    harness.boot()
    
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
        # Run specific test
        suite = loader.loadTestsFromName(args.test)
    else:
        # Discover all tests
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


def main():
    parser = argparse.ArgumentParser(
        prog="deploy.py",
        description="Skeleton Deployment Script"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Boot command
    boot_parser = subparsers.add_parser("boot", help="Boot the full system")
    boot_parser.add_argument("--seed", type=int, default=42)
    boot_parser.add_argument("--materialize", help="Blueprint name to materialize")
    boot_parser.add_argument("--era", default="extraction_now")
    boot_parser.add_argument("--target", default="json")
    boot_parser.add_argument("--serve", action="store_true", help="Start API server after boot")
    boot_parser.add_argument("--host", default="0.0.0.0")
    boot_parser.add_argument("--port", type=int, default=8000)
    
    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start API server")
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8000)
    
    # Test command
    test_parser = subparsers.add_parser("test", help="Run tests")
    test_parser.add_argument("--test", help="Specific test to run (e.g., TestClass.test_method)")
    test_parser.add_argument("--verbose", "-v", type=int, default=2)
    
    # Health command
    health_parser = subparsers.add_parser("health", help="Check system health")
    health_parser.add_argument("--verbose", "-v", action="store_true")
    
    # Scaffold command
    scaffold_parser = subparsers.add_parser("scaffold", help="Create project from template")
    scaffold_parser.add_argument("template", help="Template name")
    scaffold_parser.add_argument("name", help="Project name")
    scaffold_parser.add_argument("--output", "-o", default=".")
    scaffold_parser.add_argument("--force", "-f", action="store_true")
    
    # Wizard command
    wizard_parser = subparsers.add_parser("wizard", help="Interactive project builder")
    wizard_parser.add_argument("--mode", choices=["full", "quick", "expert"], default="full")
    
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
