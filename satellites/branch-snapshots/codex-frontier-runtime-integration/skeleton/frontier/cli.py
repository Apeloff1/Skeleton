"""Run frontier pipelines and inspect persistent memory from the Skeleton CLI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="skeleton frontier", description=__doc__)
    result.add_argument("--state-root", type=Path, default=Path(".skeleton"))
    result.add_argument("--namespace", default="default", help="persistent memory namespace")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("agents", help="list installed local pipeline adapters")
    run = commands.add_parser("run", help="execute a local pipeline through runtime policy")
    run.add_argument("agent")
    run.add_argument("task", nargs="?")
    run.add_argument("--task-file", type=Path)
    run.add_argument("--context", default="{}", help="JSON object of adapter options")
    run.add_argument("--timeout", type=float)
    memory = commands.add_parser("memory", help="persist, find, or delete memory records")
    operations = memory.add_subparsers(dest="operation", required=True)
    put = operations.add_parser("put")
    put.add_argument("text")
    put.add_argument("--id")
    put.add_argument("--metadata", default="{}")
    search = operations.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--filters", default="{}")
    delete = operations.add_parser("delete")
    delete.add_argument("id")
    return result


def _object(raw: str) -> dict:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("JSON options must be objects")
    return value


async def _dispatch(args) -> tuple[object, int]:
    if args.command == "memory":
        from skeleton.frontier.sqlite_memory import SQLiteMemoryStore

        args.state_root.mkdir(parents=True, exist_ok=True)
        async with SQLiteMemoryStore(
            args.state_root / "frontier-memory.sqlite3", namespace=args.namespace
        ) as store:
            if args.operation == "put":
                item = {**_object(args.metadata), "text": args.text}
                if args.id is not None:
                    item["id"] = args.id
                return {"id": await store.put(item)}, 0
            if args.operation == "search":
                return {
                    "items": await store.search(args.query, limit=args.limit, filters=_object(args.filters))
                }, 0
            await store.delete(args.id)
            return {"id": args.id, "deleted": True}, 0
    from skeleton.services.frontier import create_frontier_runtime

    async with create_frontier_runtime(state_root=args.state_root) as runtime:
        if args.command == "agents":
            return {
                "agents": [
                    {"name": name, "capabilities": sorted(agent.capabilities)}
                    for name, agent in runtime.agents.items()
                ]
            }, 0
        if (args.task is None) == (args.task_file is None):
            raise ValueError("supply exactly one task argument or --task-file")
        if args.task_file is not None:
            with args.task_file.open(encoding="utf-8") as source:
                task = source.read(20_001)
        else:
            task = args.task
        if len(task) > 20_000:
            raise ValueError("task exceeds 20000 characters")
        result = await runtime.execute(args.agent, task, context=_object(args.context), timeout=args.timeout)
        return result.as_dict(), 0 if result.succeeded else 1


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        output, code = asyncio.run(_dispatch(args))
    except (ValueError, TypeError, KeyError, OSError, OverflowError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(output, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
