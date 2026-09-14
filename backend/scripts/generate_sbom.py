"""Generate a deterministic CycloneDX JSON inventory for repository dependencies.

The generator has no third-party runtime dependency. It records direct Python
and frontend declarations plus cryptographic hashes of lock/manifests so CI and
release jobs can attach a stable dependency inventory to build evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

REPO_ROOT = Path(__file__).resolve().parents[2]
_REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[([^\]]+)\])?\s*(.*)$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_property(path: Path) -> dict[str, str] | None:
    if not path.exists():
        return None
    return {
        "name": f"skeleton:manifest-sha256:{path.relative_to(REPO_ROOT).as_posix()}",
        "value": _sha256(path),
    }


def python_components(path: Path) -> list[dict]:
    components: list[dict] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith(("-r", "--")):
            continue
        match = _REQUIREMENT_RE.match(line)
        if not match:
            continue
        name, extras, constraint = match.groups()
        component: dict = {
            "type": "library",
            "group": "pypi",
            "name": name,
            "bom-ref": f"pkg:pypi/{name.lower().replace('_', '-')}@declared",
            "properties": [
                {"name": "skeleton:declared-constraint", "value": constraint.strip() or "*"},
                {"name": "skeleton:manifest", "value": "backend/requirements.txt"},
            ],
        }
        exact = re.fullmatch(r"==\s*([^;\s]+)", constraint.strip())
        if exact:
            version = exact.group(1)
            component["version"] = version
            component["purl"] = f"pkg:pypi/{name.lower().replace('_', '-')}@{version}"
            component["bom-ref"] = component["purl"]
        if extras:
            component["properties"].append({"name": "skeleton:extras", "value": extras})
        components.append(component)
    return components


def frontend_components(path: Path) -> list[dict]:
    package = json.loads(path.read_text(encoding="utf-8"))
    components: list[dict] = []
    for section in ("dependencies", "devDependencies"):
        for name, declared in sorted(package.get(section, {}).items()):
            scope = "dev" if section == "devDependencies" else "runtime"
            encoded_name = name.replace("@", "%40", 1) if name.startswith("@") else name
            components.append(
                {
                    "type": "library",
                    "group": "npm",
                    "name": name,
                    "bom-ref": f"pkg:npm/{encoded_name}@declared",
                    "properties": [
                        {"name": "skeleton:declared-constraint", "value": str(declared)},
                        {"name": "skeleton:dependency-scope", "value": scope},
                        {"name": "skeleton:manifest", "value": "frontend/package.json"},
                    ],
                }
            )
    return components


def build_sbom(repo_root: Path = REPO_ROOT) -> dict:
    requirements = repo_root / "backend" / "requirements.txt"
    package_json = repo_root / "frontend" / "package.json"
    components = python_components(requirements) + frontend_components(package_json)
    components.sort(key=lambda item: (item.get("group", ""), item["name"].lower(), item["bom-ref"]))

    manifest_paths = [
        requirements,
        package_json,
        repo_root / "frontend" / "yarn.lock",
        repo_root / "pyproject.toml",
    ]
    properties = [item for item in (_manifest_property(path) for path in manifest_paths) if item]
    source_sha = os.environ.get("GITHUB_SHA", "").strip()
    if source_sha:
        properties.append({"name": "skeleton:source-commit", "value": source_sha})

    fingerprint_material = json.dumps(
        {"components": components, "properties": properties},
        sort_keys=True,
        separators=(",", ":"),
    )
    serial = uuid.uuid5(uuid.NAMESPACE_URL, hashlib.sha256(fingerprint_material.encode()).hexdigest())

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "Skeleton",
                "bom-ref": "pkg:generic/skeleton@source",
            },
            "properties": properties,
        },
        "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(REPO_ROOT / "artifacts" / "sbom.cdx.json"))
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = Path.cwd() / output
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_sbom(REPO_ROOT)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SBOM written: {output} ({len(payload['components'])} components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
