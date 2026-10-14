#!/usr/bin/env python3
"""Independent exact-head evidence generator for VOL-001."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    ("skeleton/research/source_lineage.py", "skeleton/ai/research/source_lineage.py"),
    ("skeleton/eval/research_acceptance.py", "skeleton/ai/evaluation/research_acceptance.py"),
)
TESTS = (
    "skeleton/testing/test_research_lineage.py",
    "skeleton/testing/test_research_system_acceptance.py",
)

def digest(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()

def repository_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.strip()

def build_receipt(head_sha: str, *, actual_head_sha: str | None = None) -> dict[str, object]:
    errors: list[str] = []
    if len(head_sha) != 40 or any(ch not in "0123456789abcdef" for ch in head_sha):
        errors.append("head_sha must be a lowercase 40-character git sha")
    actual = actual_head_sha if actual_head_sha is not None else repository_head()
    if head_sha != actual:
        errors.append("declared head_sha does not match checked-out repository HEAD")
    mirrors: dict[str, object] = {}
    for canonical, mirror in PAIRS:
        canonical_digest, mirror_digest = digest(canonical), digest(mirror)
        mirrors[canonical] = {"canonical_digest": canonical_digest, "mirror_digest": mirror_digest}
        if canonical_digest != mirror_digest:
            errors.append(f"governed mirror mismatch: {canonical}")
    payload: dict[str, object] = {
        "kind": "vol001-independent-research-verification-v1",
        "head_sha": head_sha,
        "repository_head_sha": actual,
        "verifier": "independent-vol001-research-v1",
        "authority_scope": "verification-evidence-only",
        "production_authority": False,
        "completion_authority": False,
        "mirror_digests": mirrors,
        "test_digests": {path: digest(path) for path in TESTS},
        "valid": not errors,
        "errors": errors,
    }
    payload["evidence_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return payload

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-out", required=True)
    args = parser.parse_args()
    receipt = build_receipt(os.environ.get("EVIDENCE_HEAD_SHA", "").strip())
    Path(args.evidence_out).write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["valid"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
