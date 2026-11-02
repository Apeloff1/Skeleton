"""B095: plugin/extension SDK with stable scoped contracts and conformance tests."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re
from typing import Any, Callable, Mapping

from ._helpers import ContractError, require, require_str

SDK_API = (1, 0)
KINDS = {"exporter": ("export",), "tool": ("run",), "model": ("infer",)}

MAX_JSON_NODES = 4_096
MAX_JSON_DEPTH = 16
MAX_JSON_BYTES = 65_536


def _bounded_json(value: Any) -> str:
    """Validate plugin JSON before encoding, rejecting cycles and resource bombs."""
    active: set[int] = set()
    nodes = 0

    def walk(node: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        require(nodes <= MAX_JSON_NODES and depth <= MAX_JSON_DEPTH,
                "plugin JSON traversal exceeds bound")
        if type(node) in (dict, list, tuple):
            identity = id(node)
            require(identity not in active, "cyclic plugin JSON")
            require(len(node) <= MAX_JSON_NODES, "plugin JSON collection exceeds bound")
            active.add(identity)
            try:
                if type(node) is dict:
                    for key, child in node.items():
                        require(type(key) is str and 1 <= len(key) <= 128,
                                "plugin JSON key exceeds bound")
                        walk(child, depth + 1)
                else:
                    for child in node:
                        walk(child, depth + 1)
            finally:
                active.remove(identity)
        elif type(node) is str:
            require(len(node) <= MAX_JSON_BYTES, "plugin JSON string exceeds bound")
        elif type(node) is int:
            require(node.bit_length() <= 4_096, "plugin JSON integer exceeds bound")
        elif type(node) is float:
            require(math.isfinite(node), "plugin JSON number must be finite")
        else:
            require(type(node) in (bool, type(None)), "plugin JSON value is not canonical")

    walk(value, 0)
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ContractError("plugin JSON encoding rejected") from exc
    require(len(encoded) <= MAX_JSON_BYTES, "plugin JSON exceeds byte bound")
    return encoded


@dataclass(frozen=True)
class Manifest:
    name: str
    kind: str
    api: tuple[int, int]
    scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_str(self.name, "name", max_len=96)
        require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", self.name)),
                "plugin name must be a bounded identifier")
        require(type(self.kind) is str and self.kind in KINDS, "unknown plugin kind")
        require(type(self.api) is tuple and len(self.api) == 2
                and all(type(v) is int and v >= 0 for v in self.api),
                "plugin API version must be two nonnegative integers")
        require(type(self.scopes) is tuple and len(self.scopes) <= 32
                and all(type(s) is str and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", s))
                        for s in self.scopes), "plugin scopes exceed bound")
        require(
            self.api[0] == SDK_API[0] and self.api[1] <= SDK_API[1],
            f"incompatible api {self.api}",
        )


class Host:
    def __init__(self, allowed_scopes: frozenset[str]) -> None:
        require(type(allowed_scopes) is frozenset and len(allowed_scopes) <= 128
                and all(type(scope) is str
                        and bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,96}", scope))
                        for scope in allowed_scopes),
                "host scope policy exceeds bound")
        self.allowed = allowed_scopes
        self.plugins: dict[str, tuple[Manifest, Any]] = {}

    def register(self, m: Manifest, impl: Any) -> None:
        require(isinstance(m, Manifest), "plugin manifest must be typed")
        extra = set(m.scopes) - self.allowed
        require(not extra, f"scopes not permitted: {sorted(extra)}")
        for method in KINDS[m.kind]:
            require(callable(getattr(impl, method, None)), f"{m.name} lacks {method}()")
        require(m.name not in self.plugins, f"duplicate plugin {m.name}")
        self.plugins[m.name] = (m, impl)

    def call(self, name: str, method: str, payload: Mapping[str, Any]) -> Any:
        if name not in self.plugins:
            raise ContractError(f"unknown plugin {name}")
        m, impl = self.plugins[name]
        require(method in KINDS[m.kind], f"{method} not in {m.kind} contract")
        require(isinstance(payload, Mapping) and len(payload) <= 128,
                "plugin payload exceeds entry bound")
        require(all(type(k) is str and 1 <= len(k) <= 128 for k in payload),
                "plugin payload keys are invalid")
        encoded = _bounded_json(dict(payload))
        result = getattr(impl, method)(json.loads(encoded))
        # Return the validated JSON snapshot, never plugin-owned mutable data.
        # Otherwise the plugin could mutate its result after conformance.
        return json.loads(_bounded_json(result))


def conformance(
    host: Host, name: str, cases: list[tuple[dict, Callable[[Any], bool]]]
) -> dict[str, Any]:
    require(type(cases) is list and 1 <= len(cases) <= 128,
            "plugin conformance cases exceed bound")
    require(type(name) is str and name in host.plugins,
            "unknown conformance plugin")
    require(all(type(case) is tuple and len(case) == 2
                and type(case[0]) is dict and callable(case[1])
                for case in cases),
            "invalid plugin conformance case")
    # Admission is atomic with respect to plugin dispatch: a malformed later
    # case must not execute any earlier plugin call or certify an empty suite.
    snapshots = [json.loads(_bounded_json(case[0])) for case in cases]
    m, _ = host.plugins[name]
    method = KINDS[m.kind][0]
    results = []
    for (_, check), payload in zip(cases, snapshots):
        a = host.call(name, method, payload)
        b = host.call(name, method, payload)
        results.append(bool(check(a)) and _bounded_json(a) == _bounded_json(b))
    return {"plugin": name, "passed": all(results), "cases": len(results)}
