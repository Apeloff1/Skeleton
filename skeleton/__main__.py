"""Skeleton CLI entry point.

Usage:
    python -m skeleton <command> [options]

Commands:
    run         Start the skeleton runtime
    forge       Blueprint compilation and materialization
    test        Run test suites
    dev         Developer CLI (scaffold, wizard, health, visualize)
    help        Show this help message
"""

import sys
import json


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]
    rest = args[1:]

    if cmd == "run":
        from skeleton.genesis import Genesis
        genesis = Genesis(seed=42).boot()
        print("Skeleton runtime booted.")
        print(f"Handles: {list(genesis.handles.keys())}")

    elif cmd == "forge":
        from skeleton.forge.universal import Forge
        forge = Forge()
        print("Forge ready.")
        if rest:
            bp = forge.new_blueprint(rest[0])
            print(f"Blueprint '{rest[0]}' created with {len(bp.components)} components.")

    elif cmd == "test":
        import unittest
        loader = unittest.TestLoader()
        suite = loader.discover("skeleton/testing", pattern="test_*.py")
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        sys.exit(0 if result.wasSuccessful() else 1)

    elif cmd == "dev":
        from skeleton.developer.cli import run_dev_cli
        result = run_dev_cli(rest)
        if isinstance(result, dict):
            print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if (isinstance(result, dict) and "error" not in result) else 1)

    elif cmd in ("help", "-h", "--help"):
        print(__doc__)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
