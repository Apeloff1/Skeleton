#!/usr/bin/env python3
"""Versioned fail-closed repository-content identity schema (#960 S022).

Stable identity across path, executable bit, content digest, and
symlink/gitlink semantics. Unknown kind, missing digest, extra fields, and
non-canonical paths fail closed.

This is ``repo.spec.content_identity`` (task ``reserve-S022-content-identity``).
It records identity only and does not classify generated vs vendor source
roots (S021 / ``scripts/check_source_path_inventory.py``). Finding prefix:
``content-identity``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


SCHEMA_VERSION = 1
TASK_ID = "reserve-S022-content-identity"
CONFLICT_DOMAIN = "repo.spec.content_identity"
_FINDING_PREFIX = "content-identity"

KINDS: tuple[str, ...] = ("file", "executable", "symlink", "gitlink")
KIND_SET = frozenset(KINDS)
DIGEST_ALGORITHMS: tuple[str, ...] = ("sha256", "git-sha1")
DIGEST_ALGORITHM_SET = frozenset(DIGEST_ALGORITHMS)
KIND_DIGEST_ALGORITHM: dict[str, str] = {
    "file": "sha256",
    "executable": "sha256",
    "symlink": "sha256",
    "gitlink": "git-sha1",
}
KIND_EXECUTABLE: dict[str, bool] = {
    "file": False,
    "executable": True,
    "symlink": False,
    "gitlink": False,
}
KIND_REQUIRES_TARGET: dict[str, bool] = {
    "file": False,
    "executable": False,
    "symlink": True,
    "gitlink": False,
}
DOCUMENT_FIELDS = frozenset(
    {
        "schema_version",
        "path",
        "kind",
        "executable",
        "digest_algorithm",
        "digest",
        "target",
    }
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


def _error(code: str, message: str) -> str:
    return f"{_FINDING_PREFIX} {code}: {message}"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def canonical_repo_path(path: object) -> str | None:
    """Return a POSIX repository-relative path, or None when non-canonical."""

    if not isinstance(path, str) or not path or "\x00" in path:
        return None
    if "\\" in path:
        return None
    pure = PurePosixPath(path)
    canonical = pure.as_posix()
    if (
        pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
        or canonical != path
    ):
        return None
    return canonical


def symlink_digest(target: str) -> str:
    """Return the sha256 identity of a symlink target payload."""

    return hashlib.sha256(target.encode("utf-8")).hexdigest()


def _check_digest(algorithm: object, digest: object, errors: list[str]) -> None:
    if digest is None or digest == "":
        errors.append(_error("missing_value digest", "digest is required"))
        return
    if not isinstance(digest, str):
        errors.append(_error("unknown digest", "digest must be a lowercase hex string"))
        return
    if algorithm == "sha256":
        if SHA256_RE.fullmatch(digest) is None:
            errors.append(
                _error(
                    "unknown digest",
                    "digest must be exactly 64 lowercase hex characters for sha256",
                )
            )
        return
    if algorithm == "git-sha1":
        if GIT_SHA1_RE.fullmatch(digest) is None:
            errors.append(
                _error(
                    "unknown digest",
                    "digest must be exactly 40 lowercase hex characters for git-sha1",
                )
            )
        return
    errors.append(_error("unknown digest", "digest cannot be checked without a closed algorithm"))


def _check_target(kind: object, target: object, errors: list[str]) -> str | None:
    requires_target = KIND_REQUIRES_TARGET.get(kind) if isinstance(kind, str) else None
    if requires_target is True:
        if not isinstance(target, str) or not target or "\x00" in target or "\\" in target:
            errors.append(
                _error(
                    "unknown target",
                    "symlink target must be a non-empty POSIX string without NUL",
                )
            )
            return None
        return target
    if requires_target is False and target is not None:
        errors.append(_error("unknown target", f"kind {kind!r} requires target to be null"))
        return None
    return None


def validate_content_identity(document: object) -> list[str]:
    """Return fail-closed violations for one repository-content identity."""

    errors: list[str] = []
    if not isinstance(document, Mapping):
        return [_error("unknown root_type", "content identity document must be an object")]

    unknown = set(document) - DOCUMENT_FIELDS
    if unknown:
        errors.append(
            _error(
                "unknown field",
                "document has unknown fields: " + ", ".join(sorted(str(item) for item in unknown)),
            )
        )
    missing = DOCUMENT_FIELDS - set(document)
    if missing:
        errors.append(
            _error(
                "missing_value field",
                "document missing fields: " + ", ".join(sorted(missing)),
            )
        )
        if "digest" in missing:
            errors.append(_error("missing_value digest", "digest is required"))

    version = document.get("schema_version")
    if not _is_int(version) or version != SCHEMA_VERSION:
        errors.append(
            _error(
                "unknown schema_version",
                f"schema_version must be exactly {SCHEMA_VERSION}",
            )
        )

    path = document.get("path")
    if canonical_repo_path(path) is None:
        errors.append(
            _error(
                "unknown path",
                "path must be a canonical repository-relative POSIX path",
            )
        )

    kind = document.get("kind")
    if kind not in KIND_SET:
        errors.append(_error("unknown kind", f"kind {kind!r} is not in the closed set"))

    executable = document.get("executable")
    if not isinstance(executable, bool):
        errors.append(_error("unknown executable", "executable must be a boolean"))
    elif kind in KIND_EXECUTABLE and executable != KIND_EXECUTABLE[kind]:
        errors.append(
            _error(
                "unknown executable",
                f"kind {kind!r} requires executable to be {KIND_EXECUTABLE[kind]}",
            )
        )

    algorithm = document.get("digest_algorithm")
    if algorithm not in DIGEST_ALGORITHM_SET:
        errors.append(
            _error(
                "unknown digest_algorithm",
                f"digest_algorithm {algorithm!r} is not in the closed set",
            )
        )
    elif kind in KIND_DIGEST_ALGORITHM and algorithm != KIND_DIGEST_ALGORITHM[kind]:
        errors.append(
            _error(
                "unknown digest_algorithm",
                f"kind {kind!r} requires digest_algorithm {KIND_DIGEST_ALGORITHM[kind]!r}",
            )
        )

    if "digest" in document:
        _check_digest(algorithm if algorithm in DIGEST_ALGORITHM_SET else None, document.get("digest"), errors)

    target: str | None = None
    if "target" in document:
        target = _check_target(kind, document.get("target"), errors)

    if (
        kind == "symlink"
        and target is not None
        and algorithm == "sha256"
        and isinstance(document.get("digest"), str)
        and SHA256_RE.fullmatch(document.get("digest")) is not None
        and document.get("digest") != symlink_digest(target)
    ):
        errors.append(
            _error(
                "unknown digest",
                "symlink digest must be sha256 of the UTF-8 target payload",
            )
        )
    return errors


def load_document(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(_error("unreadable missing_doc", f"{path} is missing")) from exc
    except OSError as exc:
        raise SystemExit(
            _error("unreadable io_error", f"cannot read {path}: {type(exc).__name__}")
        ) from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(
            _error(
                "unreadable json",
                f"invalid JSON in {path} at line {exc.lineno}, column {exc.colno}",
            )
        ) from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="content-identity JSON document")
    args = parser.parse_args(argv)
    errors = validate_content_identity(load_document(args.path))
    if errors:
        print("Content-identity schema validation failed:", file=sys.stderr)
        for item in errors:
            print(f"  {item}", file=sys.stderr)
        return 1
    print(f"Content-identity schema v{SCHEMA_VERSION} accepted {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
