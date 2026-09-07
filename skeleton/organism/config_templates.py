"""Config templates — reusable, parameterized configuration profiles.

Defines config templates (small/medium/large deployment profiles,
per-environment baselines) with parameter substitution and validation.
Operators instantiate templates instead of hand-editing config, and
the template registry tracks which live configs derive from which
template version for drift analysis.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Template:
    name: str
    version: int
    config: Dict[str, Any]
    parameters: Dict[str, Any] = field(default_factory=dict)
    created_ns: int = 0


@dataclass
class Instantiation:
    template: str
    version: int
    params: Dict[str, Any]
    instantiated_ns: int
    resolved: Dict[str, Any]


class ConfigTemplates:
    """Parameterized config templates with instantiation tracking."""

    def __init__(self):
        self._templates: Dict[str, Dict[int, Template]] = {}
        self._instantiations: List[Instantiation] = []

    def define(self, name: str, config: Dict[str, Any],
               parameters: Optional[Dict[str, Any]] = None) -> Template:
        versions = self._templates.setdefault(name, {})
        version = max(versions.keys(), default=0) + 1
        t = Template(name=name, version=version, config=config,
                     parameters=parameters or {}, created_ns=time.time_ns())
        versions[version] = t
        return t

    def _resolve(self, value: Any, params: Dict[str, Any]) -> Any:
        if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            key = value[2:-1]
            if key not in params:
                raise KeyError(f"missing template parameter: {key}")
            return params[key]
        if isinstance(value, dict):
            return {k: self._resolve(v, params) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve(v, params) for v in value]
        return value

    def instantiate(self, name: str, params: Optional[Dict[str, Any]] = None,
                    version: Optional[int] = None) -> Dict[str, Any]:
        versions = self._templates.get(name, {})
        if not versions:
            raise KeyError(f"unknown template: {name}")
        t = versions[version or max(versions.keys())]
        merged = {**t.parameters, **(params or {})}
        missing = [k for k, default in t.parameters.items() if default is ... and k not in (params or {})]
        if missing:
            raise ValueError(f"required parameters missing: {missing}")
        resolved = self._resolve(t.config, merged)
        self._instantiations.append(Instantiation(
            template=name, version=t.version, params=merged,
            instantiated_ns=time.time_ns(), resolved=resolved,
        ))
        return resolved

    def derived_from(self, name: str) -> List[Dict[str, Any]]:
        return [
            {"version": i.version, "params": i.params, "instantiated_ns": i.instantiated_ns}
            for i in self._instantiations if i.template == name
        ]

    def latest(self, name: str) -> Optional[Template]:
        versions = self._templates.get(name, {})
        return versions[max(versions.keys())] if versions else None

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "config-templates-card",
            "templates": {n: list(v.keys()) for n, v in self._templates.items()},
            "instantiations": len(self._instantiations),
        }
