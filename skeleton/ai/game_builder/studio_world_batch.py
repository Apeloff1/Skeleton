"""Bounded, source-replayed read-only Jeeves world-tool batch execution.

Plans contain only exact vetted typed requests. No model string becomes a
Python import, authorization token, filesystem write, or release assertion.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
import os
import re
from pathlib import Path
import secrets
import stat
from typing import Any

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_ecosystem_scene_schedule import (
    _canonical, _digest, _lease, _open_directory, _write_all,
)

SCHEMA = "skeleton.jeeves.studio_world_batch_plan.v1"
EXECUTION_SCHEMA = "skeleton.jeeves.studio_world_batch_execution.v1"
PROMPT = "compile bounded read-only original world workflow"
FILENAME = "studio_world_batch_execution.json"
MAX_STEPS = 8
MAX_PLAN_BYTES = 48 * 1024
MAX_EXECUTION_BYTES = 768 * 1024
BATCH_TOOL = "studio_original_world_batch"
# Only adapters with reviewed explicit False write evidence are admitted.
# The generic router also exposes legacy read-only tools without that evidence;
# they remain excluded until their exact result contracts are audited.
VERIFIED_READ_ONLY_TOOLS = frozenset({
    "studio_faction_reputation",
    "studio_ending_plan",
    "studio_original_npc_continuity",
    "studio_original_npc_continuity_merge",
})


def _registry() -> tuple[dict[str, dict[str, Any]], str]:
    # Imported lazily so the static router can register the batch adapter.
    from skeleton.ai.agents.jeeves.studio_world_tool_router import world_tool_catalog
    catalog = world_tool_catalog()
    descriptors = {}
    for item in catalog["tools"]:
        if (item["name"] not in VERIFIED_READ_ONLY_TOOLS
                or item["explicit_authoring_permission_required"]):
            continue
        descriptors[item["name"]] = item["descriptor"]
    return descriptors, catalog["catalog_digest"]


def _validate_typed(value: object, schema: object, *, depth: int = 0) -> None:
    """Validate reviewed descriptor JSON Schema primitives without coercion.

    Unsupported schema constructs fail closed rather than being interpreted as
    permission to accept arbitrary user-supplied arguments.
    """
    if depth > 12 or type(schema) is not dict:
        raise StudioQuestError("unsupported nested world tool descriptor")
    supported = {
        "type", "const", "enum", "pattern", "minLength", "maxLength",
        "minimum", "maximum", "minItems", "maxItems", "uniqueItems",
        "items", "properties", "required", "additionalProperties",
        "minProperties", "maxProperties", "description", "title",
        "default", "format",
    }
    if set(schema) - supported:
        raise StudioQuestError("unsupported world tool descriptor constraint")
    allowed = schema.get("type")
    if allowed is None:
        raise StudioQuestError("world tool descriptor missing explicit type")
    types = allowed if type(allowed) is list else [allowed]
    def matches(kind: str) -> bool:
        return {
            "object": lambda: type(value) is dict,
            "array": lambda: type(value) is list,
            "string": lambda: type(value) is str,
            "integer": lambda: type(value) is int,
            "number": lambda: type(value) in (int, float),
            "boolean": lambda: type(value) is bool,
            "null": lambda: value is None,
        }.get(kind, lambda: False)()
    if not types or any(type(t) is not str for t in types) or not any(
            matches(t) for t in types):
        raise StudioQuestError("world batch tool argument has wrong JSON type")
    if "const" in schema and value != schema["const"]:
        raise StudioQuestError("world batch tool argument constant mismatch")
    if "enum" in schema and value not in schema["enum"]:
        raise StudioQuestError("world batch tool argument outside enum")
    if type(value) is str:
        if ("minLength" in schema and len(value) < schema["minLength"]
                or "maxLength" in schema and len(value) > schema["maxLength"]
                or "pattern" in schema and re.fullmatch(
                    schema["pattern"], value) is None):
            raise StudioQuestError("world batch tool string violates schema")
    if type(value) in (int, float):
        if ("minimum" in schema and value < schema["minimum"]
                or "maximum" in schema and value > schema["maximum"]):
            raise StudioQuestError("world batch tool number violates schema")
    if type(value) is list:
        if ("minItems" in schema and len(value) < schema["minItems"]
                or "maxItems" in schema and len(value) > schema["maxItems"]):
            raise StudioQuestError("world batch tool array violates schema")
        if schema.get("uniqueItems") and len({
                _canonical(item) for item in value}) != len(value):
            raise StudioQuestError("world batch tool array has duplicates")
        item_schema = schema.get("items")
        if item_schema is None:
            raise StudioQuestError("world batch array lacks typed items")
        for item in value:
            _validate_typed(item, item_schema, depth=depth + 1)
    if type(value) is dict:
        if ("minProperties" in schema and len(value) < schema["minProperties"]
                or "maxProperties" in schema and len(value) > schema["maxProperties"]):
            raise StudioQuestError("world batch tool object violates schema")
        properties = schema.get("properties", {})
        if type(properties) is not dict:
            raise StudioQuestError("invalid world batch descriptor properties")
        required = schema.get("required", [])
        if type(required) is not list or not set(required).issubset(value):
            raise StudioQuestError("world batch tool missing required fields")
        extras = schema.get("additionalProperties", False)
        for key, item in value.items():
            if key in properties:
                _validate_typed(item, properties[key], depth=depth + 1)
            elif extras is False:
                raise StudioQuestError("world batch tool has unknown fields")
            elif type(extras) is dict:
                _validate_typed(item, extras, depth=depth + 1)
            else:
                raise StudioQuestError("unbounded world batch tool object")


def compile_world_batch_plan(
    requests: object, *, authorized: bool, expected_catalog_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world batch planning requires operator authorization")
    _lease(expected_catalog_digest, "world batch catalog")
    descriptors, actual_catalog_digest = _registry()
    if expected_catalog_digest != actual_catalog_digest:
        raise StudioQuestError("world batch catalog changed since planning")
    if (type(requests) is not list or not 1 <= len(requests) <= MAX_STEPS
            or len(_canonical(requests)) > MAX_PLAN_BYTES):
        raise StudioQuestError("invalid bounded world batch requests")
    steps: list[dict[str, Any]] = []
    for index, request in enumerate(requests):
        if (type(request) is not dict or set(request) != {"tool", "arguments"}
                or type(request["tool"]) is not str
                or type(request["arguments"]) is not dict
                or request["tool"] not in descriptors
                or "authorized" in request["arguments"]
                or "allow_authoring" in request["arguments"]):
            raise StudioQuestError("world batch requires static read-only typed tools")
        descriptor = descriptors[request["tool"]]
        fields = descriptor["parameters"]["properties"]
        schema_field = fields.get("schema")
        expected = schema_field.get("const") if type(schema_field) is dict else None
        if request["arguments"].get("schema") != expected:
            raise StudioQuestError("world batch tool schema mismatch")
        if not set(request["arguments"]).issubset(fields):
            raise StudioQuestError("world batch tool has unknown argument fields")
        required = descriptor["parameters"].get("required", [])
        if not set(required).issubset(request["arguments"]):
            raise StudioQuestError("world batch tool missing required arguments")
        _validate_typed(request["arguments"], descriptor["parameters"])
        if len(_canonical(request)) > 64 * 1024:
            raise StudioQuestError("world batch step exceeds router budget")
        steps.append({
            "ordinal": index, "request": request,
            "request_digest": _digest(request),
        })
    result: dict[str, Any] = {
        "schema": SCHEMA, "catalog_digest": actual_catalog_digest,
        "steps": steps, "step_count": len(steps),
        "operator_authorization_required": True,
        "authoring_allowed": False, "file_write_performed": False,
        "release_certified": False,
    }
    if len(_canonical(result)) > MAX_PLAN_BYTES:
        raise StudioQuestError("world batch plan exceeds byte budget")
    result["plan_digest"] = _digest(result)
    return result


def propose_world_batch_plan(
    prompt: str, requests: object, *, authorized: bool,
    expected_catalog_digest: str,
) -> dict[str, Any]:
    if type(prompt) is not str or prompt != PROMPT:
        raise StudioQuestError("unsupported typed world batch prompt")
    return compile_world_batch_plan(
        requests, authorized=authorized,
        expected_catalog_digest=expected_catalog_digest)


def replay_world_batch_plan(plan: object, *, authorized: bool) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world batch plan replay requires authorization")
    if type(plan) is not dict or plan.get("schema") != SCHEMA:
        raise StudioQuestError("invalid world batch plan")
    steps = plan.get("steps")
    if type(steps) is not list or len(steps) > MAX_STEPS:
        raise StudioQuestError("invalid world batch plan steps")
    requests = [step.get("request") if type(step) is dict else None
                for step in steps]
    verified = compile_world_batch_plan(
        requests, authorized=True,
        expected_catalog_digest=plan.get("catalog_digest"))
    if verified != plan:
        raise StudioQuestError("world batch plan failed canonical replay")
    return verified


def execute_world_batch(
    plan: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world batch execution requires authorization")
    verified = replay_world_batch_plan(plan, authorized=True)
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    rows: list[dict[str, Any]] = []
    for step in verified["steps"]:
        # A failure aborts the entire batch; no subsequent tool is invoked.
        result = route_world_tool(step["request"], authorized=True,
                                  allow_authoring=False)
        if result.get("file_write_performed") is not False:
            raise StudioQuestError("world batch refused unverified read-only execution")
        detail = result.get("result")
        if type(detail) is not dict or detail.get("release_certified") is not False:
            raise StudioQuestError("world batch refuses unqualified tool result")
        rows.append({
            "ordinal": step["ordinal"],
            "tool": step["request"]["tool"],
            "request_digest": step["request_digest"],
            "router_receipt": result,
            "router_receipt_digest": result["receipt_digest"],
            "file_write_performed": False,
        })
    output: dict[str, Any] = {
        "schema": EXECUTION_SCHEMA, "catalog_digest": verified["catalog_digest"],
        "plan_digest": verified["plan_digest"], "plan": verified,
        "results": rows, "completed_count": len(rows),
        "all_read_only": True, "file_write_performed": False,
        "native_runtime_verified": False, "release_certified": False,
    }
    if len(_canonical(output)) > MAX_EXECUTION_BYTES - 128:
        raise StudioQuestError("world batch execution exceeds receipt budget")
    output["execution_digest"] = _digest(output)
    return output


def replay_world_batch_execution(
    receipt: object, *, authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world batch execution replay requires authorization")
    if type(receipt) is not dict or receipt.get("schema") != EXECUTION_SCHEMA:
        raise StudioQuestError("invalid world batch execution receipt")
    verified = execute_world_batch(receipt.get("plan"), authorized=True)
    if verified != receipt:
        raise StudioQuestError("world batch execution failed canonical replay")
    return verified


def render_world_batch_html(receipt: object, *, authorized: bool) -> bytes:
    verified = replay_world_batch_execution(receipt, authorized=authorized)
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; ",
        "base-uri 'none'; form-action 'none'\">",
        "<title>Original world workflow receipt</title></head><body><main>",
        "<h1>Canonical read-only world workflow</h1>",
        "<p>Source replay and typed tool outputs; no release or native runtime proof.</p>",
        "<ol>",
    ]
    for row in verified["results"]:
        parts.append(
            "<li><strong>" + escape(row["tool"], quote=True) +
            "</strong> — step " + str(row["ordinal"]) +
            ", read-only verified</li>")
    parts.extend(["</ol></main></body></html>"])
    html = "".join(parts).encode("utf-8")
    if len(html) > 128 * 1024:
        raise StudioQuestError("world batch HTML exceeds byte budget")
    return html


def publish_world_batch_execution(
    receipt: object, directory: Path, *, authorized: bool,
) -> dict[str, Any]:
    verified = replay_world_batch_execution(receipt, authorized=authorized)
    raw = _canonical(verified) + b"\n"
    if len(raw) > MAX_EXECUTION_BYTES:
        raise StudioQuestError("world batch publication exceeds byte budget")
    fd = _open_directory(directory)
    temporary = ".world-batch-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temporary, FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=fd)
        finally:
            os.close(fd)
    return {
        "path": str(Path(directory) / FILENAME),
        "execution_digest": verified["execution_digest"],
        "bytes": len(raw), "file_write_performed": True,
        "release_certified": False,
    }


def restore_world_batch_execution(
    directory: Path, *, authorized: bool,
    expected_catalog_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("world batch restore requires authorization")
    _lease(expected_catalog_digest, "world batch restore catalog")
    fd = _open_directory(directory)
    try:
        handle = os.open(FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            info = os.fstat(handle)
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_EXECUTION_BYTES
                    or (os.name == "posix" and (info.st_uid != os.getuid()
                        or info.st_mode & 0o077 or info.st_nlink != 1))):
                raise StudioQuestError("world batch receipt must be private")
            raw = os.read(handle, MAX_EXECUTION_BYTES + 1)
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    if not raw or len(raw) > MAX_EXECUTION_BYTES:
        raise StudioQuestError("invalid world batch receipt size")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise StudioQuestError("duplicate world batch JSON key")
            out[key] = value
        return out
    try:
        receipt = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                             parse_constant=lambda _: (_ for _ in ()).throw(
                                 StudioQuestError("nonfinite world batch JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid world batch JSON") from exc
    if type(receipt) is not dict or receipt.get("catalog_digest") != expected_catalog_digest:
        raise StudioQuestError("stale world batch catalog lease")
    return replay_world_batch_execution(receipt, authorized=True)
