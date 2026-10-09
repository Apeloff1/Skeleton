"""Offline plagiarism evidence scanner; never uploads or republishes source text.

Usage:
python -m skeleton.ai.game_builder.plagiarism_cli scan \
  --manifest ./originality_manifest.json --root ./review_workspace \
  --receipt ./originality_receipt.json

Manifest names local UTF-8 candidates/references and includes eight exact
asset-class disclosures. No repository, ROM, image or audio is downloaded.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .plagiarism_guard import (
    AssetDeclaration, AssetDisposition, AttributionStatus, ExpressionSample,
    OriginalityError, UseBasis, audit_game_originality,
)

MAX_MANIFEST_BYTES = 256 * 1024
MAX_TEXT_BYTES = 128 * 1024
MAX_INPUTS = 256


def _parse_json_file(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_MANIFEST_BYTES:
        raise OriginalityError("missing, linked or oversized originality manifest")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, OSError, ValueError) as exc:
        raise OriginalityError("invalid JSON manifest") from exc
    if not isinstance(document, dict) or document.get("schema") != "skeleton.originality_input.v1":
        raise OriginalityError("unrecognized originality manifest schema")
    return document


def _safe_local_text(root: Path, relative_path: object) -> str:
    """Reject symlinks, absolute paths, .. traversal, device and binary files."""
    if not isinstance(relative_path, str) or not relative_path or len(relative_path) > 256:
        raise OriginalityError("invalid local text path")
    relative = Path(relative_path)
    if relative.is_absolute() or any(part in {"..", "."} for part in relative.parts):
        raise OriginalityError("source must be a relative file below review root")
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise OriginalityError("plagiarism input symlinks not authorized")
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root.resolve()):
        raise OriginalityError("plagiarism source not a regular local file")
    if candidate.stat().st_size > MAX_TEXT_BYTES:
        raise OriginalityError("source exceeds bounded scan budget")
    try:
        data = candidate.read_bytes()
        if b"\0" in data or len(data) > MAX_TEXT_BYTES:
            raise OriginalityError("binary or oversized source cannot be text-scanned")
        return data.decode("utf-8")
    except (UnicodeError, OSError) as exc:
        raise OriginalityError("unreadable or non-UTF-8 source") from exc


def scan_manifest(manifest: str | Path, root: str | Path) -> dict[str, object]:
    """Generate a deterministic in-memory originality triage receipt only."""
    rootpath = Path(root)
    if not rootpath.is_dir() or rootpath.is_symlink():
        raise OriginalityError("authorized local review root must be a real directory")
    raw = _parse_json_file(Path(manifest))
    declarations = raw.get("assets")
    if not isinstance(declarations, list) or len(declarations) != 8:
        raise OriginalityError("manifest requires eight explicit asset class declarations")
    assets = []
    try:
        for row in declarations:
            if not isinstance(row, dict):
                raise OriginalityError("invalid asset row")
            status = AssetDisposition(row["disposition"])
            basis = None if row.get("basis") is None else UseBasis(row["basis"])
            assets.append(AssetDeclaration(
                modality=row["modality"], disposition=status, basis=basis,
                provenance_sha256=row.get("provenance_sha256"),
                author_identity=row.get("author_identity"),
                rights_holder=row.get("rights_holder"),
                license_identifier=row.get("license_identifier"),
                proposed_use_licensed=row.get("proposed_use_licensed", False),
                public_domain_independently_checked=row.get("public_domain_independently_checked", False),
                attribution=AttributionStatus(row.get("attribution", "missing")),
                reviewer_evidence_sha256=row.get("reviewer_evidence_sha256"),
                false_authorship_claim=row.get("false_authorship_claim", False),
                comparable_media_screened=row.get("comparable_media_screened", False),
            ))
    except (KeyError, TypeError, ValueError) as exc:
        raise OriginalityError("invalid originality asset disclosure") from exc

    def read_samples(label: str, *, reference: bool) -> tuple[ExpressionSample, ...]:
        rows = raw.get(label)
        if not isinstance(rows, list) or len(rows) > MAX_INPUTS:
            raise OriginalityError("invalid candidate/reference count")
        result = []
        for item in rows:
            if not isinstance(item, dict):
                raise OriginalityError("malformed source record")
            try:
                result.append(ExpressionSample(
                    work_id=item["work_id"],
                    modality=item["modality"],
                    text=_safe_local_text(rootpath, item["relative_path"]),
                    evidence_sha256=item.get("evidence_sha256"),
                    protected_reference=reference,
                ))
            except (KeyError, TypeError, ValueError) as exc:
                raise OriginalityError("invalid local text source") from exc
        return tuple(result)

    report = audit_game_originality(
        raw.get("project_id"),
        assets=tuple(assets),
        candidate_samples=read_samples("candidates", reference=False),
        references=read_samples("references", reference=True),
        artifact_sha256=raw.get("artifact_sha256"),
    )
    return report.public_receipt()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local eight-modality game originality gate")
    parser.add_argument("action", choices=["scan"])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args(argv)
    receipt = scan_manifest(args.manifest, args.root)
    path = Path(args.receipt)
    if path.is_symlink() or path.exists():
        raise FileExistsError("originality receipt must be created, never silently overwritten")
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(receipt, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "receipt_file": str(path),
        "disposition": receipt["disposition"],
        "blockers": len(receipt["blockers"]),
        "review_issues": len(receipt["review_issues"]),
        "release_permitted": False,
    }, sort_keys=True))
    # A report can be useful on a review hold. Return 2 for a blocked design.
    return 2 if receipt["disposition"] != "design_admissible_not_legal_clearance" else 0


if __name__ == "__main__":
    raise SystemExit(main())
