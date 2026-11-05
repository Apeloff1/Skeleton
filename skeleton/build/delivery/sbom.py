"""Minimal, deterministic CycloneDX-style SBOM generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from skeleton.build.delivery._util import DeliveryError, canonical_json, require_sha256, sha256_json

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ECOSYSTEMS = frozenset({"pypi", "npm", "cargo", "generic"})


@dataclass(frozen=True)
class Component:
    name: str
    version: str
    ecosystem: str
    license: str = "NOASSERTION"
    sha256: str | None = None

    def __post_init__(self) -> None:
        if not _NAME.fullmatch(self.name):
            raise DeliveryError(f"invalid component name {self.name!r}")
        if not self.version or len(self.version) > 64 or any(c.isspace() for c in self.version):
            raise DeliveryError(f"invalid component version for {self.name}")
        if self.ecosystem not in ECOSYSTEMS:
            raise DeliveryError(f"unknown ecosystem {self.ecosystem!r}")
        if self.sha256 is not None:
            require_sha256(self.sha256, field=f"{self.name}.sha256")

    @property
    def purl(self) -> str:
        name = self.name.lower().replace("_", "-") if self.ecosystem == "pypi" else self.name
        return f"pkg:{self.ecosystem}/{name}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "type": "library",
            "name": self.name,
            "version": self.version,
            "purl": self.purl,
            "licenses": [{"license": {"id": self.license}}],
        }
        if self.sha256:
            out["hashes"] = [{"alg": "SHA-256", "content": self.sha256}]
        return out


def parse_requirements(text: str) -> tuple[Component, ...]:
    """Parse pinned ``name==version`` lines; unpinned requirements are rejected."""
    out: list[Component] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        line = line.split(";", 1)[0].strip()
        if "==" not in line:
            raise DeliveryError(f"line {lineno}: requirement must be pinned with ==")
        name, version = (part.strip() for part in line.split("==", 1))
        name = name.split("[", 1)[0]
        out.append(Component(name, version, "pypi"))
    return tuple(out)


def parse_package_lock(data: Mapping[str, Any]) -> tuple[Component, ...]:
    packages = data.get("packages")
    if not isinstance(packages, Mapping):
        raise DeliveryError("package-lock must contain a packages object")
    out = []
    for key, meta in packages.items():
        if not key or not isinstance(meta, Mapping) or "version" not in meta:
            continue
        name = key.rsplit("node_modules/", 1)[-1]
        safe = name.replace("@", "").replace("/", ".")
        out.append(Component(safe, str(meta["version"]), "npm", str(meta.get("license", "NOASSERTION"))))
    return tuple(out)


def build_sbom(subject: str, version: str, components: Iterable[Component]) -> dict[str, Any]:
    items = sorted({(c.purl, c) for c in components}, key=lambda pair: pair[0])
    purls = [p for p, _ in items]
    if len(purls) != len(set(purls)):
        raise DeliveryError("duplicate components")
    body = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": subject, "version": version}},
        "components": [c.to_dict() for _, c in items],
    }
    body["serialNumber"] = "urn:sha256:" + sha256_json(body)
    return body


def serialize(sbom: Mapping[str, Any]) -> bytes:
    return canonical_json(sbom).encode("ascii")
