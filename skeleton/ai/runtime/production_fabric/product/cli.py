"""Offline game CLI; never starts a server or downloads model weights."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from ..contracts.canonical import loads
from ..contracts.errors import FabricError
from ..persistence.journal import Journal
from ..planning.engine import ProductionEngine
from .api import LocalAPI

def main(argv: list[str] | None=None) -> int:
    parser = argparse.ArgumentParser(description='Skeleton deterministic offline production fabric')
    parser.add_argument('--world', required=True, type=Path)
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--request', required=True, help='JSON request object')
    args = parser.parse_args(argv)
    try:
        if args.world.is_symlink() or args.db.is_symlink():
            raise FabricError('symlink input not admitted')
        raw = args.world.read_bytes()
        world = loads(raw)
        engine = ProductionEngine(world, Journal(args.db))
        sys.stdout.buffer.write(LocalAPI(engine).json(args.request.encode('utf-8')))
        engine.journal.close()
    except (OSError, FabricError) as exc:
        sys.stderr.write(f'offline production CLI: {exc}\n')
        return 1
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
