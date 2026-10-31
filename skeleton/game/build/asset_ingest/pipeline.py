"""Batch import: read files, collect broken/missing assets, build the manifest."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable

from .importers import _EXT, MAX_ASSET_BYTES, AssetImportError, import_bytes
from .manifest import AssetManifest


@dataclass(frozen=True)
class ImportIssue:
    path: str
    code: str  # "missing" | "broken" | "unsupported" | "unsafe" | "missing_reference"
    detail: str


@dataclass
class ImportReport:
    manifest: AssetManifest
    imported: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


def import_files(root: str | Path, paths: Iterable[str]) -> ImportReport:
    """Import ``paths`` (relative to ``root``); never raises for a bad asset.

    Mesh references (mtllib, glTF buffer/image URIs) must exist under ``root``.
    """
    base = Path(root).resolve()
    report = ImportReport(AssetManifest())
    for rel in sorted(set(paths)):
        pp = PurePosixPath(rel)
        if pp.is_absolute() or ".." in pp.parts or "\\" in rel:
            report.issues.append(ImportIssue(rel, "unsafe", "path escapes asset root"))
            continue
        target = base / pp
        if target.is_symlink() or (target.exists() and base not in target.resolve().parents):
            report.issues.append(ImportIssue(rel, "unsafe", "symlink or outside asset root"))
            continue
        if not target.is_file():
            report.issues.append(ImportIssue(rel, "missing", "file not found"))
            continue
        if pp.suffix.lower() not in _EXT:
            report.issues.append(ImportIssue(rel, "unsupported", f"extension {pp.suffix or '(none)'}"))
            continue
        if target.stat().st_size > MAX_ASSET_BYTES:
            report.issues.append(ImportIssue(rel, "broken", "asset exceeds size limit"))
            continue
        try:
            asset = import_bytes(rel, target.read_bytes())
            new = report.manifest.add(asset)
        except AssetImportError as exc:
            report.issues.append(ImportIssue(rel, "broken", str(exc)))
            continue
        (report.imported if new else report.duplicates).append(rel)
    _check_references(base, report)
    return report


def _check_references(base: Path, report: ImportReport) -> None:
    """Flag mesh external refs (mtllib, glTF buffers/images) that don't resolve to a file."""
    for entry in report.manifest.entries:
        for ref in entry.metadata.get("external_refs", []):
            ref_path = PurePosixPath(entry.path).parent / ref
            target = base / ref_path
            if ".." in ref_path.parts or ref_path.is_absolute() or not target.is_file() \
                    or base not in target.resolve().parents:
                report.issues.append(ImportIssue(entry.path, "missing_reference", ref_path.as_posix()))


def import_directory(root: str | Path) -> ImportReport:
    """Import every supported asset under ``root`` (symlinks skipped)."""
    base = Path(root).resolve()
    return import_files(base, [_rel(base, p) for p in base.rglob("*")
                               if p.is_file() and not p.is_symlink() and p.suffix.lower() in _EXT])
