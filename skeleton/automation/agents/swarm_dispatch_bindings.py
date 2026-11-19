"""Bounded, deterministic result-to-input binding for durable dispatcher jobs.

Only exact JSON values flow from verified historical results into explicit
null placeholders. There is no interpolation, expression evaluator, shell,
attribute lookup, dynamic tool selection or arbitrary object construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Callable

from skeleton.automation.agents.swarm_durable import (
    DurableSwarmError, _wait_bytes, _wait_digest, _wait_identifier,
)

MAX_BINDINGS = 8
MAX_PATH_DEPTH = 12
MAX_INPUT_BYTES = 32768
MAX_BINDING_WAIT_MS = 7 * 24 * 60 * 60 * 1000


class BindingError(ValueError):
    """Invalid or permanently unavailable exact dataflow input."""


class BindingDeferred(Exception):
    """Earlier durable command/result is not yet ready; leave pending."""


def _path(value: object) -> tuple[str | int, ...]:
    if type(value) is not list or len(value) > MAX_PATH_DEPTH:
        raise BindingError("binding path must be a bounded JSON array")
    for item in value:
        if type(item) is str:
            if not 1 <= len(item) <= 128 or any(ord(ch) < 32 for ch in item):
                raise BindingError("invalid binding object key")
        elif type(item) is not int or not 0 <= item <= 65535:
            raise BindingError("invalid binding list index")
    return tuple(value)


def _at(value: object, path: tuple[str | int, ...]) -> object:
    for part in path:
        if type(value) is dict and type(part) is str and part in value:
            value = value[part]
        elif type(value) is list and type(part) is int and part < len(value):
            value = value[part]
        else:
            raise BindingError("binding path does not exist")
    return value


def _replace(value: object, path: tuple[str | int, ...], replacement: object) -> object:
    if not path:
        if value is not None:
            raise BindingError("binding target is not a null placeholder")
        return replacement
    parent = _at(value, path[:-1])
    if _at(parent, path[-1:]) is not None:
        raise BindingError("binding target is not a null placeholder")
    parent[path[-1]] = replacement
    return value


@dataclass(frozen=True, slots=True)
class InputBinding:
    source_request_id: str
    source_task_id: str
    source_path: tuple[str | int, ...]
    target_path: tuple[str | int, ...]

    @classmethod
    def parse(cls, item: object) -> InputBinding:
        if type(item) is not dict or set(item) != {
            "source_request_id", "source_task_id", "source_path", "target_path",
        }:
            raise BindingError("invalid exact input binding properties")
        try:
            return cls(
                _wait_identifier(item["source_request_id"]), _wait_identifier(item["source_task_id"]),
                _path(item["source_path"]), _path(item["target_path"]),
            )
        except DurableSwarmError as exc:
            raise BindingError("invalid binding source identity") from exc

    def record(self) -> dict:
        return {
            "source_request_id": self.source_request_id, "source_task_id": self.source_task_id,
            "source_path": list(self.source_path), "target_path": list(self.target_path),
        }


def parse_bindings(value: object, template: object, *, task_id: str) -> tuple[InputBinding, ...]:
    if type(value) is not list or not 1 <= len(value) <= MAX_BINDINGS:
        raise BindingError("invalid binding count")
    bindings = tuple(InputBinding.parse(item) for item in value)
    targets = []
    for binding in bindings:
        if binding.source_task_id == task_id:
            raise BindingError("self-referential result binding")
        if _at(template, binding.target_path) is not None:
            raise BindingError("binding must overwrite an explicit null placeholder")
        target = binding.target_path
        if any(target[:len(other)] == other or other[:len(target)] == target for other in targets):
            raise BindingError("overlapping result binding targets")
        targets.append(target)
    return bindings


def _bounded_copy(value: object) -> object:
    try:
        data = _wait_bytes(value)
        if len(data) > MAX_INPUT_BYTES:
            raise BindingError("bound JSON value exceeds input capacity")
        return json.loads(data)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise BindingError("invalid or oversized bound JSON value") from exc


def materialize(
    template: object, bindings: tuple[InputBinding, ...],
    resolve: Callable[[InputBinding], dict],
) -> tuple[object, list[dict]]:
    """Resolve exact source results once and bind detached JSON values.

    The caller proves source command identity, ordering, tenant ownership,
    execution receipt and canonical result before returning a result. This
    function hashes the exact substituted value and receipt for replay audit.
    """
    output = _bounded_copy(template)
    lineage = []
    resolved = {}
    for binding in bindings:
        identity = (binding.source_request_id, binding.source_task_id)
        if identity not in resolved:
            proof = resolve(binding)
            if (type(proof) is not dict or proof.get("task_id") != binding.source_task_id
                    or proof.get("state") != "succeeded" or proof.get("uncertain_on_restore") is not False
                    or "result" not in proof):
                raise DurableSwarmError("binding resolver returned unverified source result")
            _wait_digest(proof.get("receipt_sha256"))
            if proof.get("reconciliation_sha256") is not None:
                _wait_digest(proof["reconciliation_sha256"])
            resolved[identity] = proof
        proof = resolved[identity]
        value = _bounded_copy(_at(proof["result"], binding.source_path))
        output = _replace(output, binding.target_path, value)
        output = _bounded_copy(output)
        lineage.append({
            **binding.record(),
            "receipt_sha256": proof["receipt_sha256"],
            "reconciliation_sha256": proof.get("reconciliation_sha256"),
            "value_sha256": sha256(_wait_bytes(value)).hexdigest(),
        })
    return output, lineage
