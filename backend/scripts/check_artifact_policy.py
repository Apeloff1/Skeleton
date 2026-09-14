"""Enforce repository artifact hygiene and required Git LFS declarations."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
ATTRIBUTES = ROOT / ".gitattributes"
MODEL_LFS_PATTERNS = {
    "*.safetensors",
    "*.gguf",
    "*.ckpt",
    "*.pt",
    "*.pth",
    "*.onnx",
    "*.tflite",
}
FORBIDDEN_PARTS = {"node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
FORBIDDEN_SUFFIXES = {".pyc", ".pyo"}
FORBIDDEN_NAMES = {".DS_Store", "Thumbs.db"}


def tracked_files(repo_root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        shell=False,
    )
    return [item for item in result.stdout.decode("utf-8", "strict").split("\0") if item]


def attribute_violations(path: Path = ATTRIBUTES) -> list[str]:
    if not path.exists():
        return [".gitattributes is missing"]
    configured: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) >= 2 and "filter=lfs" in fields[1:]:
            configured.add(fields[0])
    missing = sorted(MODEL_LFS_PATTERNS - configured)
    return [f".gitattributes: missing Git LFS rule for {pattern}" for pattern in missing]


def tracked_path_violations(paths: list[str]) -> list[str]:
    findings: list[str] = []
    for raw in paths:
        path = Path(raw)
        if any(part in FORBIDDEN_PARTS for part in path.parts):
            findings.append(f"tracked generated/cache path is forbidden: {raw}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(f"tracked compiled Python artifact is forbidden: {raw}")
        if path.name in FORBIDDEN_NAMES:
            findings.append(f"tracked OS metadata file is forbidden: {raw}")
    return findings


def main() -> int:
    findings = attribute_violations() + tracked_path_violations(tracked_files())
    if findings:
        print("Repository artifact policy violations detected:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("Artifact policy passed: LFS declarations and tracked-file hygiene verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
