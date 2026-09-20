"""Path and naming quality analysis for machine navigation."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re

from .model import RepositoryModel

_AMBIGUOUS = {
    "misc",
    "stuff",
    "things",
    "util",
    "utils",
    "helper",
    "helpers",
    "common",
    "shared",
    "temp",
    "tmp",
    "old",
    "new",
    "final",
    "backup",
    "copy",
    "other",
}
_VERSIONED = re.compile(r"(?:^|[_-])v?\d+(?:[_-]|$)", re.IGNORECASE)
_COPY = re.compile(r"(?:copy|final|new|old|backup)(?:[_-]?\d+)?", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class NamingFinding:
    code: str
    severity: str
    path: str
    component: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "severity": self.severity,
            "path": self.path,
            "component": self.component,
            "detail": self.detail,
        }


def analyze_naming(model: RepositoryModel) -> tuple[NamingFinding, ...]:
    findings: list[NamingFinding] = []
    stems: dict[tuple[str, str], list[str]] = {}
    for record in model.files:
        pure = PurePosixPath(record.path)
        stem = pure.stem.casefold()
        stems.setdefault((record.zone, stem), []).append(record.path)

        for part in pure.parts[:-1]:
            lowered = part.casefold()
            if lowered in _AMBIGUOUS:
                findings.append(NamingFinding(
                    code="naming.ambiguous-directory",
                    severity="low",
                    path=record.path,
                    component=part,
                    detail="directory name is weak for deterministic machine navigation",
                ))
        if stem in _AMBIGUOUS:
            findings.append(NamingFinding(
                code="naming.ambiguous-file",
                severity="low",
                path=record.path,
                component=pure.name,
                detail="file basename is semantically weak",
            ))
        if _COPY.search(stem):
            findings.append(NamingFinding(
                code="naming.copy-suffix",
                severity="medium",
                path=record.path,
                component=pure.name,
                detail="copy/final/old/new naming suggests duplicate lineage",
            ))
        if _VERSIONED.search(stem) and record.kind == "source":
            findings.append(NamingFinding(
                code="naming.versioned-source",
                severity="low",
                path=record.path,
                component=pure.name,
                detail="version-like source filename may hide replacement lineage",
            ))
        if len(pure.parts) >= 12:
            findings.append(NamingFinding(
                code="naming.deep-path",
                severity="low",
                path=record.path,
                component=str(len(pure.parts)),
                detail="deep path increases machine navigation cost",
            ))

    for (zone, stem), paths in stems.items():
        if not stem or len(paths) < 4:
            continue
        findings.append(NamingFinding(
            code="naming.repeated-basename",
            severity="low",
            path=paths[0],
            component=f"{zone}:{stem}",
            detail=f"{len(paths)} files in the same zone share this basename",
        ))

    dedup = {
        (item.code, item.path, item.component): item
        for item in findings
    }
    return tuple(sorted(
        dedup.values(),
        key=lambda item: (item.severity, item.code, item.path),
    ))
