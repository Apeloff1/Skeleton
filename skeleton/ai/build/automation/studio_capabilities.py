"""Machine-readable capability contract for Autonomous Studio."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class Capability:
    name: str
    risk: str
    extensions: tuple[str, ...]
    requires_validation: bool = True

CAPABILITIES = (
    Capability("python.modify", "bounded", (".py",)),
    Capability("python.create", "bounded", (".py",)),
    Capability("tests.modify", "bounded", (".py",)),
    Capability("tests.create", "bounded", (".py",)),
    Capability("docs.modify", "low", (".md", ".txt")),
    Capability("structured_data.modify", "bounded", (".json", ".yaml", ".yml")),
)
DENIED_CAPABILITIES = frozenset({"workflow.modify","dependency.modify","secret.modify","binary.modify","delete","rename"})

def capability_for(path: str, *, creating: bool) -> str:
    lower = path.lower()
    suffix = "." + lower.rsplit(".", 1)[-1] if "." in lower.rsplit("/", 1)[-1] else ""
    if suffix == ".py":
        if "/test" in lower or lower.rsplit("/",1)[-1].startswith("test_"):
            return "tests.create" if creating else "tests.modify"
        return "python.create" if creating else "python.modify"
    if suffix in {".md", ".txt"}:
        return "docs.modify"
    if suffix in {".json", ".yaml", ".yml"}:
        return "structured_data.modify"
    raise ValueError(f"no Studio capability for path: {path}")

def validate_capabilities(paths: Iterable[str], *, new_paths: Iterable[str] = ()) -> tuple[str, ...]:
    new = set(new_paths)
    return tuple(capability_for(path, creating=path in new) for path in paths)
