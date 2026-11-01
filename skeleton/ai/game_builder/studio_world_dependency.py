"""Canonical dependency-DAG authoring for bounded read-only Jeeves workflows.

This compiles an operator-authored partial order into the existing source-bound
batch engine. A graph is not an authorization grant, an AI-execution trace,
or evidence that native game runtime integration has been qualified.
"""
from __future__ import annotations

from html import escape
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)
from skeleton.ai.game_builder.studio_world_batch import (
    MAX_STEPS, compile_world_batch_plan, replay_world_batch_plan,
    execute_world_batch,
)

SCHEMA = "skeleton.jeeves.studio_world_dependency_graph.v1"
EXECUTION_SCHEMA = "skeleton.jeeves.studio_world_dependency_execution.v1"
PROMPT = "compile dependency-ordered original world workflow"
FILENAME = "studio_world_dependency_execution.json"
MAX_GRAPH_BYTES = 48 * 1024
MAX_RECEIPT_BYTES = 768 * 1024
_ID = re.compile(r"[a-z][a-z0-9_-]{0,47}\Z", re.ASCII)


def _ordered(graph: object) -> tuple[list[dict[str, Any]], list[str]]:
    if (type(graph) is not dict or set(graph) != {"schema", "prompt", "steps"}
            or graph["schema"] != SCHEMA or graph["prompt"] != PROMPT
            or type(graph["steps"]) is not list
            or not 1 <= len(graph["steps"]) <= MAX_STEPS
            or len(_canonical(graph)) > MAX_GRAPH_BYTES):
        raise StudioQuestError("invalid bounded world dependency graph")
    steps = graph["steps"]
    positions: dict[str, int] = {}
    for index, step in enumerate(steps):
        if (type(step) is not dict or set(step) != {"id", "depends_on", "request"}
                or type(step["id"]) is not str or not _ID.fullmatch(step["id"])
                or step["id"] in positions
                or type(step["depends_on"]) is not list
                or len(step["depends_on"]) > MAX_STEPS
                or type(step["request"]) is not dict):
            raise StudioQuestError("invalid or repeated dependency step")
        positions[step["id"]] = index
    followers: dict[str, list[str]] = {key: [] for key in positions}
    indegree: dict[str, int] = {}
    for step in steps:
        dependencies = step["depends_on"]
        if (any(type(dep) is not str or dep not in positions
                or dep == step["id"] for dep in dependencies)
                or len(set(dependencies)) != len(dependencies)):
            raise StudioQuestError("unknown, self or duplicate world dependency")
        indegree[step["id"]] = len(dependencies)
        for dependency in dependencies:
            followers[dependency].append(step["id"])
    ready = [key for key in positions if indegree[key] == 0]
    order: list[str] = []
    while ready:
        ready.sort(key=positions.__getitem__)
        current = ready.pop(0)
        order.append(current)
        for follower in followers[current]:
            indegree[follower] -= 1
            if indegree[follower] == 0:
                ready.append(follower)
    if len(order) != len(steps):
        raise StudioQuestError("world dependency graph has a causal cycle")
    return steps, order


def compile_dependency_world_batch(
    graph: object, *, authorized: bool, expected_catalog_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world dependency compilation requires authorization")
    _lease(expected_catalog_digest, "world dependency catalog")
    steps, order = _ordered(graph)
    by_id = {step["id"]: step for step in steps}
    plan = compile_world_batch_plan(
        [by_id[key]["request"] for key in order],
        authorized=True, expected_catalog_digest=expected_catalog_digest,
    )
    proof: dict[str, Any] = {
        "schema": SCHEMA, "prompt": PROMPT,
        "graph": graph, "graph_digest": _digest(graph),
        "catalog_digest": plan["catalog_digest"],
        "source_projects": plan["provenance"]["projects"],
        "execution_order": order,
        "dependency_edges": [
            {"id": step["id"], "depends_on": list(step["depends_on"])}
            for step in steps
        ],
        "plan": plan, "plan_digest": plan["plan_digest"],
        "source_replay_verified": True,
        "file_write_performed": False,
        "native_runtime_verified": False, "release_certified": False,
    }
    if len(_canonical(proof)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("world dependency proof exceeds budget")
    proof["proof_digest"] = _digest(proof)
    return proof


def replay_dependency_world_batch(proof: object, *, authorized: bool) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world dependency replay requires authorization")
    if type(proof) is not dict or proof.get("schema") != SCHEMA:
        raise StudioQuestError("invalid world dependency proof")
    verified = compile_dependency_world_batch(
        proof.get("graph"), authorized=True,
        expected_catalog_digest=proof.get("catalog_digest"),
    )
    if verified != proof:
        raise StudioQuestError("world dependency proof failed source replay")
    return verified


def execute_dependency_world_batch(proof: object, *, authorized: bool) -> dict[str, Any]:
    verified = replay_dependency_world_batch(proof, authorized=authorized)
    execution = execute_world_batch(verified["plan"], authorized=True)
    result: dict[str, Any] = {
        "schema": EXECUTION_SCHEMA,
        "dependency_proof": verified,
        "proof_digest": verified["proof_digest"],
        "execution": execution,
        "execution_digest": execution["execution_digest"],
        "completed_count": execution["completed_count"],
        "all_read_only": True,
        "file_write_performed": False,
        "native_runtime_verified": False, "release_certified": False,
    }
    if len(_canonical(result)) > MAX_RECEIPT_BYTES - 128:
        raise StudioQuestError("world dependency execution exceeds budget")
    result["result_digest"] = _digest(result)
    return result


def replay_dependency_execution(receipt: object, *, authorized: bool) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world dependency execution replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != EXECUTION_SCHEMA:
        raise StudioQuestError("invalid world dependency execution receipt")
    verified = execute_dependency_world_batch(
        receipt.get("dependency_proof"), authorized=True,
    )
    if verified != receipt:
        raise StudioQuestError("world dependency execution failed canonical replay")
    return verified


def render_dependency_world_html(proof: object, *, authorized: bool) -> bytes:
    verified = replay_dependency_world_batch(proof, authorized=authorized)
    by_id = {row["id"]: row for row in verified["graph"]["steps"]}
    rows = []
    for step_id in verified["execution_order"]:
        row = by_id[step_id]
        dependencies = ", ".join(row["depends_on"]) or "none"
        rows.append(
            "<li><strong>" + escape(step_id, quote=True) + "</strong>: " +
            escape(row["request"]["tool"], quote=True) + "; depends on " +
            escape(dependencies, quote=True) + "</li>"
        )
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        "base-uri 'none'; form-action 'none'; object-src 'none'\">"
        "<title>Original world dependency workflow</title></head><body><main>"
        "<h1>Verified world workflow dependency order</h1>"
        "<p>Source-replayed typed plan; no native runtime or release proof.</p>"
        "<p>Plan SHA-256: " + escape(verified["plan_digest"]) + "</p><ol>" +
        "".join(rows) + "</ol></main></body></html>"
    ).encode("utf-8")
    if len(html) > 64 * 1024:
        raise StudioQuestError("world dependency HTML exceeds budget")
    return html


def publish_dependency_execution(
    receipt: object, directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_dependency_execution(receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("world dependency publication exceeds budget")
    fd = _open_directory(directory)
    temp = ".world-dependency-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temp, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {
        "path": str(Path(directory) / FILENAME),
        "result_digest": verified["result_digest"], "bytes": len(raw),
        "file_write_performed": True, "release_certified": False,
    }


def restore_dependency_execution(
    directory: Path, *, authorized: bool, expected_catalog_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world dependency restore requires authorization")
    _lease(expected_catalog_digest, "world dependency restore catalog")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_RECEIPT_BYTES
                    or (os.name == "posix" and (info.st_uid != os.getuid()
                        or info.st_mode & 0o077 or info.st_nlink != 1))):
                raise StudioQuestError("world dependency receipt must be private")
            raw = os.read(handle, MAX_RECEIPT_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_RECEIPT_BYTES:
        raise StudioQuestError("invalid world dependency receipt size")
    def unique(pairs):
        output = {}
        for key, value in pairs:
            if key in output:
                raise StudioQuestError("duplicate world dependency JSON key")
            output[key] = value
        return output
    try:
        receipt = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite world dependency JSON")),
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid world dependency JSON") from exc
    if (type(receipt) is not dict or
            receipt.get("dependency_proof", {}).get("catalog_digest")
            != expected_catalog_digest):
        raise StudioQuestError("stale world dependency catalog lease")
    return replay_dependency_execution(receipt, authorized=True)
