"""Pinned multi-cohort replay qualification using canonical batch owners.

Each cohort is verified through its original replay implementation. The
portfolio retains a compact digest-bound witness per cohort and does not
claim native engine execution, licensing, release, or atomic snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import re
import stat

from .contracts import canonical_digest
from .dual_runtime_verify import (
    DualRuntimeVerificationError, _assert_original_root, _bounded_names,
    _canonical_bytes, _child_fd, _json, _read, _root_fd,
)
from .offline_export_batch import (
    MAX_INDEX_BYTES, MAX_PACKAGES, MAX_TOTAL_VERIFIED_BYTES,
    SCHEMA as BATCH_SCHEMA, OfflineBatchVerificationError,
    _entry, verify_export_batch,
)

SCHEMA = "skeleton.game_builder.offline_portfolio.v1"
RECEIPT_SCHEMA = "skeleton.game_builder.offline_portfolio_receipt.v1"
MAX_COHORTS = 128
MAX_PORTFOLIO_INDEX = 128 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
IDENTIFIER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}\Z")


class PortfolioError(ValueError):
    """Portfolio admission or replay rejected."""


@dataclass(frozen=True)
class PortfolioBudget:
    cohorts: int = 64
    packages: int = 2048
    verified_bytes: int = 64 * MAX_TOTAL_VERIFIED_BYTES

    def __post_init__(self):
        for value, maximum in (
            (self.cohorts, MAX_COHORTS),
            (self.packages, MAX_COHORTS * MAX_PACKAGES),
            (self.verified_bytes, MAX_COHORTS * MAX_TOTAL_VERIFIED_BYTES),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise PortfolioError("invalid portfolio budget")


@dataclass(frozen=True)
class Cohort:
    cohort_id: str
    directory: str
    index_sha256: str

    @classmethod
    def parse(cls, row):
        if type(row) is not dict or set(row) != {
            "cohort_id", "directory", "index_sha256",
        }:
            raise PortfolioError("malformed cohort")
        key, directory, pin = (row[k] for k in ("cohort_id", "directory", "index_sha256"))
        if (type(key) is not str or not IDENTIFIER.fullmatch(key)
                or type(directory) is not str or not IDENTIFIER.fullmatch(directory)
                or directory in (".", "..", "portfolio.json")
                or type(pin) is not str or not HEX.fullmatch(pin)):
            raise PortfolioError("invalid cohort identity or pin")
        return cls(key, directory, pin)


def _identity(fd: int):
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        raise PortfolioError("cohort not a directory")
    return info.st_dev, info.st_ino


def _pinned_document(fd, name, pin, ceiling):
    raw = _read(fd, name, ceiling)
    if sha256(raw).hexdigest() != pin:
        raise PortfolioError("independently pinned document changed")
    value = _json(raw, ceiling)
    if _canonical_bytes(value) != raw:
        raise PortfolioError("noncanonical pinned document")
    return raw, value


def _declared_projects(fd, cohort):
    raw, index = _pinned_document(
        fd, "batch.json", cohort.index_sha256, MAX_INDEX_BYTES,
    )
    if set(index) != {"schema", "packages"} or index["schema"] != BATCH_SCHEMA:
        raise PortfolioError("invalid cohort index schema")
    rows = index["packages"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_PACKAGES:
        raise PortfolioError("invalid cohort package count")
    declared = tuple(_entry(row) for row in rows)
    directories = tuple(row[1] for row in declared)
    if directories != tuple(sorted(set(directories))):
        raise PortfolioError("duplicate or unordered package directories")
    if set(_bounded_names(fd, MAX_PACKAGES + 1)) != set(directories) | {"batch.json"}:
        raise PortfolioError("cohort inventory mismatch")
    return raw, declared


def verify_portfolio(root: str | Path, *, expected_index_sha256: str,
                     authorized: bool, budget: PortfolioBudget = PortfolioBudget()):
    if authorized is not True:
        raise PermissionError("explicit local operator required")
    if type(expected_index_sha256) is not str or not HEX.fullmatch(expected_index_sha256):
        raise PortfolioError("independent portfolio SHA-256 pin required")
    if not isinstance(budget, PortfolioBudget):
        raise PortfolioError("invalid budget type")
    root_fd = None
    try:
        root_fd = _root_fd(root)
        raw, index = _pinned_document(
            root_fd, "portfolio.json", expected_index_sha256, MAX_PORTFOLIO_INDEX,
        )
        if set(index) != {"schema", "cohorts"} or index["schema"] != SCHEMA:
            raise PortfolioError("unsupported portfolio schema")
        rows = index["cohorts"]
        if type(rows) is not list or not 1 <= len(rows) <= budget.cohorts:
            raise PortfolioError("cohort ceiling exceeded")
        cohorts = tuple(Cohort.parse(row) for row in rows)
        directories = tuple(c.directory for c in cohorts)
        if directories != tuple(sorted(set(directories))):
            raise PortfolioError("duplicate or unordered cohort directories")
        if len({c.cohort_id for c in cohorts}) != len(cohorts):
            raise PortfolioError("duplicate cohort identity")
        expected_names = set(directories) | {"portfolio.json"}
        if set(_bounded_names(root_fd, budget.cohorts + 1)) != expected_names:
            raise PortfolioError("portfolio inventory mismatch")
        # Admit each owner's worst-case logical byte budget before replay.
        # No partial work is represented as a successful portfolio.
        if len(cohorts) * MAX_TOTAL_VERIFIED_BYTES > budget.verified_bytes:
            raise PortfolioError("worst-case replay byte ceiling exceeded")
        declarations = {}
        project_ids = set()
        identities = set()
        for cohort in cohorts:
            fd = _child_fd(root_fd, (cohort.directory,), directory=True)
            try:
                identity = _identity(fd)
                if identity in identities:
                    raise PortfolioError("duplicate cohort directory identity")
                identities.add(identity)
                source, projects = _declared_projects(fd, cohort)
                for project, directory, pin in projects:
                    if project in project_ids:
                        raise PortfolioError("duplicate project across cohorts")
                    project_ids.add(project)
                    if len(project_ids) > budget.packages:
                        raise PortfolioError("aggregate package ceiling exceeded")
                declarations[cohort.directory] = (identity, source, projects)
            finally:
                os.close(fd)
        receipts = []
        total_bytes = total_actions = total_files = 0
        for cohort in cohorts:
            identity, source, projects = declarations[cohort.directory]
            fd = _child_fd(root_fd, (cohort.directory,), directory=True)
            try:
                if _identity(fd) != identity or _read(fd, "batch.json", MAX_INDEX_BYTES) != source:
                    raise PortfolioError("cohort changed before replay")
                receipt = verify_export_batch(
                    fd, expected_index_sha256=cohort.index_sha256, authorized=True,
                )
                if _read(fd, "batch.json", MAX_INDEX_BYTES) != source:
                    raise PortfolioError("cohort changed after replay")
            finally:
                os.close(fd)
            observed = tuple((p["project_id"], p["package_dir"], p["manifest_sha256"])
                             for p in receipt["packages"])
            if observed != projects or receipt["verified_packages"] != len(projects):
                raise PortfolioError("canonical batch evidence differs from declaration")
            total_bytes += receipt["verified_bytes"]
            total_actions += receipt["replayed_actions"]
            total_files += sum(p["verified_files"] for p in receipt["packages"])
            if total_bytes > budget.verified_bytes:
                raise PortfolioError("aggregate replay byte ceiling exceeded")
            receipts.append({
                "cohort_id": cohort.cohort_id,
                "directory": cohort.directory,
                "index_sha256": cohort.index_sha256,
                "receipt_digest": receipt["receipt_digest"],
                "verified_packages": len(projects),
                "verified_bytes": receipt["verified_bytes"],
                "replayed_actions": receipt["replayed_actions"],
                "project_manifest_digest": canonical_digest([
                    {"project_id": p, "package_dir": d, "manifest_sha256": h}
                    for p, d, h in projects
                ]),
            })
        for cohort in cohorts:
            identity, source, _ = declarations[cohort.directory]
            fd = _child_fd(root_fd, (cohort.directory,), directory=True)
            try:
                if _identity(fd) != identity or _read(fd, "batch.json", MAX_INDEX_BYTES) != source:
                    raise PortfolioError("cohort changed before final publication")
            finally:
                os.close(fd)
        if set(_bounded_names(root_fd, budget.cohorts + 1)) != expected_names:
            raise PortfolioError("portfolio inventory changed")
        if _read(root_fd, "portfolio.json", MAX_PORTFOLIO_INDEX) != raw:
            raise PortfolioError("portfolio index changed")
        _assert_original_root(root, root_fd)
        body = {
            "schema": RECEIPT_SCHEMA,
            "index_sha256": expected_index_sha256,
            "verified_cohorts": len(receipts),
            "verified_packages": len(project_ids),
            "verified_files": total_files,
            "verified_bytes": total_bytes,
            "replayed_actions": total_actions,
            "cohorts": receipts,
            "project_set_digest": canonical_digest(sorted(project_ids)),
            "offline_gameplay_reexecuted": True,
            "atomic_source_snapshot": False,
            "godot_executed": False,
            "rights_certified": False,
            "release_certified": False,
        }
        return {**body, "receipt_digest": canonical_digest(body)}
    except PortfolioError:
        raise
    except (OfflineBatchVerificationError, DualRuntimeVerificationError,
            OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise PortfolioError("portfolio verification rejected") from exc
    finally:
        if root_fd is not None:
            os.close(root_fd)
