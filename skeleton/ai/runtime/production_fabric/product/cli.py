"""Offline game CLI; never starts a server or downloads model weights."""
from __future__ import annotations
import argparse
from contextlib import closing
from pathlib import Path
import os
import sqlite3
import stat
import sys
from ..contracts.canonical import MAX_JSON_BYTES, loads
from ..contracts.errors import FabricError
from ..persistence.journal import Journal
from ..planning.engine import ProductionEngine
from .dispatcher import LocalAPI

def _bounded_regular_world(path: Path) -> bytes:
    # POSIX O_NOFOLLOW closes the final-component symlink race. Windows
    # retains the earlier explicit link rejection; never open a directory,
    # FIFO, device, or unbounded content stream as a game world.
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_CLOEXEC', 0)
    flags |= getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise FabricError('world input must be a regular file')
        return source.read(MAX_JSON_BYTES + 1)


def main(argv: list[str] | None=None) -> int:
    parser = argparse.ArgumentParser(description='Skeleton deterministic offline production fabric')
    parser.add_argument('--world', required=True, type=Path)
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--request', required=True, help='JSON request object')
    args = parser.parse_args(argv)
    try:
        if args.world.is_symlink() or args.db.is_symlink():
            raise FabricError('symlink input not admitted')
        # The JSON parser has a 2 MiB ceiling; enforce it before allocation.
        raw = _bounded_regular_world(args.world)
        if len(raw) > MAX_JSON_BYTES:
            raise FabricError('world input exceeds byte limit')
        world = loads(raw)
        # Always close operator-owned SQLite even when engine validation,
        # request dispatch or the output pipe fails.
        with closing(Journal(args.db)) as journal:
            engine = ProductionEngine(world, journal)
            sys.stdout.buffer.write(LocalAPI(engine).json(args.request.encode('utf-8')))
    except (OSError, sqlite3.Error, FabricError) as exc:
        sys.stderr.write(f'offline production CLI: {exc}\n')
        return 1
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
