"""Minimal, deterministic CycloneDX-style SBOM generation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from skeleton.build.delivery._util import DeliveryError, canonical_json, require_sha256, sha256_json

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ECOSYSTEMS = frozenset({"pypi", "npm", "cargo", "generic"})
MAX_SBOM_COMPONENTS = 8192
MAX_REQUIREMENTS_CHARS = 2 * 1024 * 1024


@dataclass(frozen=True)
class Component:
    name: str
    version: str
    ecosystem: str
    license: str = "NOASSERTION"
    sha256: str | None = None

    def __post_init__(self) -> None:
        if type(self.name) is not str or not _NAME.fullmatch(self.name):
            raise DeliveryError(f"invalid component name {self.name!r}")
        if (type(self.version) is not str or not self.version
                or len(self.version) > 64 or any(c.isspace() for c in self.version)):
            raise DeliveryError(f"invalid component version for {self.name}")
        if (type(self.license) is not str or not 1 <= len(self.license) <= 256
                or any(ord(c) < 32 or ord(c) == 127 for c in self.license)):
            raise DeliveryError("invalid component license evidence")
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
    if type(text) is not str or len(text) > MAX_REQUIREMENTS_CHARS:
        raise DeliveryError("requirements text exceeds bound")
    out: list[Component] = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        if lineno > MAX_SBOM_COMPONENTS:
            raise DeliveryError("requirements component count exceeds bound")
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        # -r, -e, index overrides and direct URLs can pull dependencies not
        # represented by the generated SBOM; never silently omit them.
        if line.startswith("-"):
            raise DeliveryError(f"line {lineno}: unsupported requirements directive")
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
    if len(packages) > MAX_SBOM_COMPONENTS:
        raise DeliveryError("package-lock component count exceeds bound")
    out = []
    for key, meta in packages.items():
        if key == "":
            continue  # root package is the SBOM subject, not a dependency
        if not isinstance(key, str) or not isinstance(meta, Mapping) or "version" not in meta:
            raise DeliveryError("package-lock dependency lacks version evidence")
        name = key.rsplit("node_modules/", 1)[-1]
        safe = name.replace("@", "").replace("/", ".")
        if type(meta["version"]) is not str or type(meta.get("license", "NOASSERTION")) is not str:
            raise DeliveryError("package-lock dependency has invalid version or license")
        out.append(Component(safe, meta["version"], "npm", meta.get("license", "NOASSERTION")))
    return tuple(out)


def build_sbom(subject: str, version: str, components: Iterable[Component]) -> dict[str, Any]:
    from itertools import islice

    bounded = list(islice(components, MAX_SBOM_COMPONENTS + 1))
    if len(bounded) > MAX_SBOM_COMPONENTS:
        raise DeliveryError("SBOM component count exceeds bound")
    if any(not isinstance(c, Component) for c in bounded):
        raise DeliveryError("SBOM requires validated components")
    # A set would silently erase repeated identical components before the
    # duplicate check, hiding malformed provenance inventory.
    items = sorted(((c.purl, c) for c in bounded), key=lambda pair: pair[0])
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
