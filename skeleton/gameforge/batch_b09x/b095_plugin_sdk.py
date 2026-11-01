"""B095: plugin/extension SDK with stable scoped contracts and conformance tests."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable, Mapping

from ._helpers import ContractError, digest, require, require_str

SDK_API = (1, 0)
KINDS = {"exporter": ("export",), "tool": ("run",), "model": ("infer",)}


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
        try:
            encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=True, allow_nan=False)
        except (TypeError, ValueError, RecursionError) as exc:
            raise ContractError("plugin payload is not canonical JSON") from exc
        require(len(encoded) <= 65_536, "plugin payload exceeds byte bound")
        return getattr(impl, method)(json.loads(encoded))


def conformance(
    host: Host, name: str, cases: list[tuple[dict, Callable[[Any], bool]]]
) -> dict[str, Any]:
    require(type(cases) is list and len(cases) <= 128,
            "plugin conformance cases exceed bound")
    m, _ = host.plugins[name]
    method = KINDS[m.kind][0]
    results = []
    for payload, check in cases:
        a = host.call(name, method, payload)
        b = host.call(name, method, payload)
        results.append(bool(check(a)) and digest(a) == digest(b))
    return {"plugin": name, "passed": all(results), "cases": len(results)}
