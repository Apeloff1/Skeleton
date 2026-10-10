#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-020 multimodal intelligence boundaries.

The verifier does not import the multimodal runtime. It derives qualification
from canonical source identity, source/AI mirror parity, masterplan bindings,
and fail-closed trust/provenance invariants. Behavioral execution runs in a
separate workflow job.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
PAIRS = (
    (Path("skeleton/multimodal/contracts.py"), Path("skeleton/ai/runtime/multimodal/contracts.py")),
    (Path("skeleton/multimodal/sanitize.py"), Path("skeleton/ai/runtime/multimodal/sanitize.py")),
    (Path("skeleton/multimodal/ingest.py"), Path("skeleton/ai/runtime/multimodal/ingest.py")),
    (Path("skeleton/multimodal/__init__.py"), Path("skeleton/ai/runtime/multimodal/__init__.py")),
)
REQUIRED_PATHS = {
    "skeleton/multimodal/contracts.py",
    "skeleton/multimodal/__init__.py",
    "skeleton/multimodal/sanitize.py",
    "skeleton/multimodal/ingest.py",
}
REQUIRED_TESTS = {
    "backend/tests/test_ai_provider_media.py",
    "skeleton/testing/test_vol020_multimodal_contracts.py",
    "skeleton/testing/test_vol020_multimodal_sanitize.py",
    "skeleton/testing/test_vol020_multimodal_ingest.py",
}
REQUIRED_MODALITIES = {"document", "image", "audio", "speech", "video"}

TOKENS = {
    "contracts.py": (
        'DOCUMENT="document"',
        'IMAGE="image"',
        'AUDIO="audio"',
        'SPEECH="speech"',
        'VIDEO="video"',
        "class MediaProvenance",
        "source_digest",
        "transform_digest",
        "class CrossModalReference",
        "dangling reference",
        'authority_scope:str="untrusted-media-evidence"',
        "media cannot grant policy authority",
        "metadata budget exceeded",
    ),
    "sanitize.py": (
        "MAX_PAYLOAD_BYTES=16_000_000",
        "ignore previous",
        "system prompt",
        "developer message",
        "follow these instructions",
        "embedded-instruction",
        "active-content",
        'authority_scope:str="sanitization-evidence-only"',
        "sanitizer cannot grant authority",
        'safe=b"" if quarantined else payload',
        "source_digest",
    ),
    "ingest.py": (
        "MAX_INPUTS=4096",
        "duplicate input segment",
        "typed MediaInput required",
        "quarantined_segments",
        'authority_scope:str="ingestion-evidence-only"',
        "ingestion cannot grant authority",
        "tuple(sorted(quarantined))",
    ),
}


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    master = _load(root / MASTER)
    rows = master.get("volumes")
    volume = next(
        (
            row for row in rows
            if isinstance(row, dict) and row.get("key") == "VOL-020"
        ),
        None,
    ) if isinstance(rows, list) else None
    if not isinstance(volume, dict):
        errors.append("masterplan missing VOL-020")
        volume = {}

    if volume.get("title") != "Multimodal Intelligence":
        errors.append("VOL-020 title drift")
    if volume.get("scope") != "canonical-plan":
        errors.append("VOL-020 scope drift")
    if volume.get("implementation_status") not in {"implemented", "hardened", "verified"}:
        errors.append("VOL-020 implementation status below implemented")
    if volume.get("completion_checkbox") is True and volume.get("implementation_status") != "verified":
        errors.append("VOL-020 completion cannot precede verified implementation status")

    missing_paths = sorted(REQUIRED_PATHS - set(volume.get("implementation_paths") or []))
    if missing_paths:
        errors.append("VOL-020 implementation binding incomplete: " + ", ".join(missing_paths))
    missing_tests = sorted(REQUIRED_TESTS - set(volume.get("tests") or []))
    if missing_tests:
        errors.append("VOL-020 test binding incomplete: " + ", ".join(missing_tests))

    requirements = tuple(str(item) for item in volume.get("requirements") or [])
    for phrase in (
        "typed modality contracts",
        "cross-modal alignment and source identity",
        "untrusted evidence, not policy",
    ):
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"VOL-020 requirement invariant lost: {phrase}")

    source_digests: dict[str, str] = {}
    mirror_digests: dict[str, str] = {}
    inspected = 0
    for canonical_rel, mirror_rel in PAIRS:
        canonical_path = root / canonical_rel
        mirror_path = root / mirror_rel
        try:
            canonical_bytes = canonical_path.read_bytes()
            mirror_bytes = mirror_path.read_bytes()
        except OSError as exc:
            errors.append(f"cannot read multimodal source pair {canonical_rel.name}: {type(exc).__name__}")
            continue
        source_digests[canonical_rel.as_posix()] = _sha(canonical_bytes)
        mirror_digests[mirror_rel.as_posix()] = _sha(mirror_bytes)
        if canonical_bytes != mirror_bytes:
            errors.append(f"VOL-020 source/AI mirror drift: {canonical_rel.name}")
        tokens = TOKENS.get(canonical_rel.name, ())
        source = canonical_bytes.decode("utf-8")
        for token in tokens:
            inspected += 1
            if token not in source:
                errors.append(f"VOL-020 invariant missing from {canonical_rel.name}: {token}")

    contract_source = (root / "skeleton/multimodal/contracts.py").read_text(encoding="utf-8")
    found_modalities = {
        modality
        for modality in REQUIRED_MODALITIES
        if f'"{modality}"' in contract_source
    }
    if found_modalities != REQUIRED_MODALITIES:
        errors.append(
            "VOL-020 modality coverage drift: "
            + ",".join(sorted(REQUIRED_MODALITIES - found_modalities))
        )

    binding = {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "completion_checkbox_mark": volume.get("completion_checkbox_mark"),
        "gaps": list(volume.get("gaps") or []),
        "implementation_paths": sorted(set(volume.get("implementation_paths") or [])),
        "tests": sorted(set(volume.get("tests") or [])),
    }
    binding["binding_digest"] = _digest_json(binding)

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol020-multimodal-v1",
        "volume": "VOL-020",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "source_digests": source_digests,
        "mirror_digests": mirror_digests,
        "modality_count": len(found_modalities),
        "checked_invariant_count": inspected,
        "volume_binding": binding,
        "errors": errors,
        "valid": not errors,
    }
    receipt["receipt_digest"] = _digest_json(receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except VerificationError as exc:
        receipt = {
            "schema_version": 1,
            "verifier": "independent-vol020-multimodal-v1",
            "volume": "VOL-020",
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "errors": [str(exc)],
            "valid": False,
        }
        receipt["receipt_digest"] = _digest_json(receipt)

    rendered = json.dumps(receipt, sort_keys=True, indent=2)
    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(f"VOL-020 independent multimodal verification: OK ({receipt['receipt_digest']})")
    else:
        print("VOL-020 independent multimodal verification: FAIL")
        for error in receipt["errors"]:
            print(f" - {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
