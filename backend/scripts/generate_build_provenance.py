"""Generate deterministic build provenance for security/release evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(path: Path, repo_root: Path) -> dict[str, str] | None:
    if not path.exists() or not path.is_file():
        return None
    return {
        "path": path.relative_to(repo_root).as_posix(),
        "sha256": sha256_file(path),
    }


def build_provenance(repo_root: Path = REPO_ROOT, *, sbom_path: Path | None = None) -> dict:
    sbom = sbom_path or repo_root / "artifacts" / "sbom.cdx.json"
    inputs = [
        repo_root / "backend" / "requirements.txt",
        repo_root / "frontend" / "package.json",
        repo_root / "frontend" / "yarn.lock",
        repo_root / ".github" / "workflows" / "backend-quality.yml",
        sbom,
    ]
    materials = [record for record in (_record(path, repo_root) for path in inputs) if record]
    materials.sort(key=lambda item: item["path"])

    source_sha = os.environ.get("GITHUB_SHA", "").strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "Apeloff1/Skeleton").strip() or "Apeloff1/Skeleton"
    run_id = os.environ.get("GITHUB_RUN_ID", "").strip()

    payload: dict = {
        "schema": "skeleton.build-provenance/v1",
        "repository": repository,
        "source": {"commit": source_sha or "local"},
        "materials": materials,
        "builder": {
            "kind": "github-actions" if run_id else "local",
            "workflow": ".github/workflows/backend-quality.yml",
        },
    }
    if run_id:
        payload["builder"]["run_id"] = run_id
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(REPO_ROOT / "artifacts" / "build-provenance.json"))
    parser.add_argument("--sbom", default=str(REPO_ROOT / "artifacts" / "sbom.cdx.json"))
    args = parser.parse_args()

    output = Path(args.output)
    if not output.is_absolute():
        output = Path.cwd() / output
    sbom = Path(args.sbom)
    if not sbom.is_absolute():
        sbom = Path.cwd() / sbom

    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_provenance(REPO_ROOT, sbom_path=sbom)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Build provenance written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
