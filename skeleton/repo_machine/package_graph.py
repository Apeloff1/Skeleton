"""Package and project-unit discovery for polyglot repository organization."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from .model import RepositoryModel

_MANIFESTS = {
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "package.json": "node",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "pom.xml": "java-maven",
    "build.gradle": "java-gradle",
    "build.gradle.kts": "java-gradle",
}


@dataclass(frozen=True, slots=True)
class PackageUnit:
    identity: str
    root: str
    ecosystem: str
    manifests: tuple[str, ...]
    zones: tuple[str, ...]
    source_files: int
    test_files: int
    total_files: int

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "root": self.root,
            "ecosystem": self.ecosystem,
            "manifests": list(self.manifests),
            "zones": list(self.zones),
            "source_files": self.source_files,
            "test_files": self.test_files,
            "total_files": self.total_files,
        }


def discover_package_units(model: RepositoryModel) -> tuple[PackageUnit, ...]:
    manifests: dict[tuple[str, str], list[str]] = {}
    for record in model.files:
        name = PurePosixPath(record.path).name
        ecosystem = _MANIFESTS.get(name)
        if ecosystem is None:
            continue
        parent = PurePosixPath(record.path).parent.as_posix()
        root = "" if parent == "." else parent
        manifests.setdefault((root, ecosystem), []).append(record.path)

    units: list[PackageUnit] = []
    for (root, ecosystem), paths in sorted(manifests.items()):
        prefix = root + "/" if root else ""
        members = [
            record
            for record in model.files
            if record.path.startswith(prefix)
        ]
        # Exclude nested package roots from the parent package's direct metrics.
        nested_roots = {
            other_root
            for (other_root, _eco) in manifests
            if other_root and other_root != root
            and (
                (not root and "/" not in other_root)
                or (root and other_root.startswith(root + "/"))
            )
        }
        direct_members = [
            record for record in members
            if not any(
                record.path.startswith(nested + "/")
                for nested in nested_roots
            )
        ]
        identity_root = root.replace("/", ":") or "root"
        units.append(PackageUnit(
            identity=f"{ecosystem}:{identity_root}",
            root=root,
            ecosystem=ecosystem,
            manifests=tuple(sorted(paths)),
            zones=tuple(sorted({item.zone for item in direct_members})),
            source_files=sum(item.kind == "source" for item in direct_members),
            test_files=sum(item.kind == "test" for item in direct_members),
            total_files=len(direct_members),
        ))
    return tuple(units)


def package_ownership_matrix(model: RepositoryModel) -> dict[str, tuple[str, ...]]:
    return {
        unit.identity: unit.zones
        for unit in discover_package_units(model)
    }


def package_findings(model: RepositoryModel) -> tuple[dict[str, object], ...]:
    findings: list[dict[str, object]] = []
    for unit in discover_package_units(model):
        if len(unit.zones) >= 5:
            findings.append({
                "code": "package.crosses-many-zones",
                "package": unit.identity,
                "severity": "medium",
                "zones": list(unit.zones),
            })
        if unit.source_files >= 20 and unit.test_files == 0:
            findings.append({
                "code": "package.missing-tests",
                "package": unit.identity,
                "severity": "high",
                "source_files": unit.source_files,
            })
    return tuple(findings)
