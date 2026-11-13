"""B095: plugin/extension SDK with stable scoped contracts and conformance tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ._helpers import ContractError, digest, require, require_str

SDK_API = (1, 0)
KINDS = {
    "exporter": ("export",),
    "tool": ("run",),
    "model": ("infer",),
    # Mod content hooks (skeleton.ai.game_builder.mods): plan in, plan out.
    "content_hook": ("apply",),
}


@dataclass(frozen=True)
class Manifest:
    name: str
    kind: str
    api: tuple[int, int]
    scopes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_str(self.name, "name")
        require(self.kind in KINDS, f"unknown plugin kind {self.kind}")
        require(
            self.api[0] == SDK_API[0] and self.api[1] <= SDK_API[1],
            f"incompatible api {self.api}",
        )


class Host:
    def __init__(self, allowed_scopes: frozenset[str]) -> None:
        self.allowed = allowed_scopes
        self.plugins: dict[str, tuple[Manifest, Any]] = {}

    def register(self, m: Manifest, impl: Any) -> None:
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
        return getattr(impl, method)(dict(payload))


def conformance(
    host: Host, name: str, cases: list[tuple[dict, Callable[[Any], bool]]]
) -> dict[str, Any]:
    m, _ = host.plugins[name]
    method = KINDS[m.kind][0]
    results = []
    for payload, check in cases:
        a = host.call(name, method, payload)
        b = host.call(name, method, payload)
        results.append(bool(check(a)) and digest(a) == digest(b))
    return {"plugin": name, "passed": all(results), "cases": len(results)}
