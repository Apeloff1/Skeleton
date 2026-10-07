#!/usr/bin/env python3
"""Deterministic container-image digest refresh planning and provenance.

The repository intentionally pins deployable and CI container images by sha256.
This tool automates the *review proposal* side of refreshing those pins without
giving a scheduled workflow repository-write authority.

Workflow:
  1. inventory scans approved tracked surfaces and records exact file preimages;
  2. queries emits mutable tag references that a registry resolver may inspect;
  3. resolutions converts a tab-separated resolver result into bounded JSON;
  4. plan binds old pins, resolved pins, source commit, and file preimages;
  5. apply verifies all preimages, updates exact pins, and emits provenance;
  6. verify re-checks the evidence against the modified checkout.

The companion GitHub Actions workflow uploads the plan, provenance, and patch as
an artifact. It never pushes a branch or opens a pull request automatically.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Iterable, Iterator, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ARG_RE = re.compile(r"^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)=(\S+)\s*$")
VARIABLE_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
PIN_RE = re.compile(
    r"(?<![A-Za-z0-9._$\\{\\}:@/-])"
    r"(?P<reference>"
    r"(?:[A-Za-z0-9._-]+(?::[0-9]+)?/)*"
    r"[A-Za-z0-9._$\{\}-]+"
    r"(?::[A-Za-z0-9._$\{\}-]+)?"
    r")@sha256:(?P<digest>[0-9a-f]{64})"
)
DEFAULT_FILES = (
    "Dockerfile",
    "backend/Dockerfile",
    "frontend/Dockerfile",
    "docker-compose.yml",
)
DEFAULT_WORKFLOW_GLOB = ".github/workflows/*.yml"
MAX_FILES = 256
MAX_OCCURRENCES = 1024
MAX_INPUT_BYTES = 4 * 1024 * 1024


class DigestRefreshError(RuntimeError):
    """Fail-closed digest refresh error."""


class DigestRefreshPolicyError(DigestRefreshError, ValueError):
    """Invalid input or ambiguous pinning policy."""


class DigestRefreshStateError(DigestRefreshError):
    """Checkout state no longer matches the evidence being applied."""


@dataclass(frozen=True, slots=True)
class PinOccurrence:
    path: str
    line: int
    raw_reference: str
    query_reference: str
    old_digest: str


@dataclass(frozen=True, slots=True)
class PinRecord:
    query_reference: str
    old_digest: str
    occurrences: tuple[PinOccurrence, ...]


@dataclass(frozen=True, slots=True)
class SourceRecord:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class RefreshEntry:
    query_reference: str
    old_digest: str
    new_digest: str
    occurrences: tuple[PinOccurrence, ...]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _json_digest(payload: object) -> str:
    return _sha256_bytes(_canonical_json(payload))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    _atomic_write(path, data.encode("utf-8"))


def _load_json(path: Path) -> object:
    try:
        info = path.lstat()
    except OSError as exc:
        raise DigestRefreshPolicyError("JSON input is unavailable") from exc
    if path.is_symlink() or not path.is_file():
        raise DigestRefreshPolicyError(
            "JSON input must be a regular non-symlink file"
        )
    if not info.st_size or info.st_size > MAX_INPUT_BYTES:
        raise DigestRefreshPolicyError("JSON input size is outside policy")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DigestRefreshPolicyError("JSON input is invalid") from exc


def _atomic_write(path: Path, payload: bytes) -> None:
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=parent)
    temporary = Path(raw)
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _repo_relative(path: Path) -> str:
    try:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(ROOT.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise DigestRefreshPolicyError("scan path escapes repository") from exc
    return relative.as_posix()


def _approved_files(extra: Sequence[str] = ()) -> tuple[Path, ...]:
    candidates = [ROOT / item for item in DEFAULT_FILES]
    candidates.extend(sorted(ROOT.glob(DEFAULT_WORKFLOW_GLOB)))
    candidates.extend(ROOT / item for item in extra)

    unique: dict[str, Path] = {}
    for path in candidates:
        try:
            relative = _repo_relative(path)
            info = path.lstat()
        except FileNotFoundError:
            raise DigestRefreshPolicyError("required digest surface is missing") from None
        if path.is_symlink() or not path.is_file():
            raise DigestRefreshPolicyError("digest surface must be a regular non-symlink file")
        if info.st_size > MAX_INPUT_BYTES:
            raise DigestRefreshPolicyError("digest surface exceeds scan byte bound")
        unique[relative] = path
    if not unique:
        raise DigestRefreshPolicyError("digest inventory surface is empty")
    if len(unique) > MAX_FILES:
        raise DigestRefreshPolicyError("digest inventory file-count bound exceeded")
    return tuple(unique[key] for key in sorted(unique))


def _dockerfile_args(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = ARG_RE.match(line)
        if not match:
            continue
        key, value = match.groups()
        # ARG values used to resolve registry tags must themselves be literal.
        if "$" not in value and not any(char.isspace() for char in value):
            values[key] = value
    return values


def _expand_reference(reference: str, variables: Mapping[str, str]) -> str:
    unresolved: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = variables.get(name)
        if value is None:
            unresolved.add(name)
            return match.group(0)
        return value

    expanded = VARIABLE_RE.sub(replace, reference)
    if unresolved:
        raise DigestRefreshPolicyError("container reference uses unresolved build variable")
    if "$" in expanded or "{" in expanded or "}" in expanded:
        raise DigestRefreshPolicyError("container reference remains dynamic after expansion")
    _validate_query_reference(expanded)
    return expanded


def _validate_query_reference(reference: str) -> None:
    if (
        not isinstance(reference, str)
        or not reference
        or reference.startswith("-")
        or any(part.startswith("-") for part in reference.split("/"))
        or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in reference)
        or "@" in reference
    ):
        raise DigestRefreshPolicyError("invalid mutable image reference")
    tail = reference.rsplit("/", 1)[-1]
    if ":" not in tail:
        raise DigestRefreshPolicyError("refreshable image reference must include an explicit tag")
    name, tag = tail.rsplit(":", 1)
    if not name or not tag or tag == "latest" and reference.startswith("sha256:"):
        raise DigestRefreshPolicyError("invalid tagged image reference")


def _scan_file(path: Path) -> tuple[SourceRecord, list[PinOccurrence]]:
    relative = _repo_relative(path)
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise DigestRefreshPolicyError("digest surface cannot be read as UTF-8") from exc

    variables = _dockerfile_args(text) if path.name == "Dockerfile" else {}
    occurrences: list[PinOccurrence] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        matches = list(PIN_RE.finditer(line))
        if line.count("@sha256:") != len(matches):
            raise DigestRefreshPolicyError("invalid digest-pinned container reference")
        for match in matches:
            raw_reference = match.group("reference")
            old_digest = match.group("digest")
            query_reference = _expand_reference(raw_reference, variables)
            occurrences.append(
                PinOccurrence(
                    path=relative,
                    line=number,
                    raw_reference=raw_reference,
                    query_reference=query_reference,
                    old_digest=old_digest,
                )
            )
            if len(occurrences) > MAX_OCCURRENCES:
                raise DigestRefreshPolicyError("digest occurrence bound exceeded")

    return (
        SourceRecord(
            path=relative,
            sha256=_sha256_bytes(payload),
            size=len(payload),
        ),
        occurrences,
    )


def build_inventory(extra: Sequence[str] = ()) -> dict[str, object]:
    sources: list[SourceRecord] = []
    occurrences: list[PinOccurrence] = []
    for path in _approved_files(extra):
        source, found = _scan_file(path)
        sources.append(source)
        occurrences.extend(found)

    if not occurrences:
        raise DigestRefreshPolicyError("no digest-pinned container references found")
    if len(occurrences) > MAX_OCCURRENCES:
        raise DigestRefreshPolicyError("digest occurrence bound exceeded")

    grouped: dict[str, list[PinOccurrence]] = {}
    for occurrence in occurrences:
        grouped.setdefault(occurrence.query_reference, []).append(occurrence)

    pins: list[PinRecord] = []
    for query_reference in sorted(grouped):
        rows = grouped[query_reference]
        digests = {row.old_digest for row in rows}
        if len(digests) != 1:
            raise DigestRefreshPolicyError(
                "same mutable image reference has inconsistent repository digests"
            )
        pins.append(
            PinRecord(
                query_reference=query_reference,
                old_digest=next(iter(digests)),
                occurrences=tuple(
                    sorted(rows, key=lambda row: (row.path, row.line, row.raw_reference))
                ),
            )
        )

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "sources": [asdict(row) for row in sorted(sources, key=lambda row: row.path)],
        "pins": [
            {
                "query_reference": pin.query_reference,
                "old_digest": pin.old_digest,
                "occurrences": [asdict(item) for item in pin.occurrences],
            }
            for pin in pins
        ],
    }
    payload["inventory_digest"] = _json_digest(payload)
    return payload


def _require_schema(payload: object, *, kind: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise DigestRefreshPolicyError(f"{kind} must be a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise DigestRefreshPolicyError(f"{kind} schema version is unsupported")
    return payload


def _inventory_pins(payload: object) -> tuple[PinRecord, ...]:
    data = _require_schema(payload, kind="inventory")
    expected_digest = data.get("inventory_digest")
    unsigned = dict(data)
    unsigned.pop("inventory_digest", None)
    if not isinstance(expected_digest, str) or expected_digest != _json_digest(unsigned):
        raise DigestRefreshPolicyError("inventory digest does not match inventory content")

    raw_pins = data.get("pins")
    if not isinstance(raw_pins, list) or not raw_pins:
        raise DigestRefreshPolicyError("inventory contains no pins")

    pins: list[PinRecord] = []
    for raw in raw_pins:
        if not isinstance(raw, dict):
            raise DigestRefreshPolicyError("inventory pin is malformed")
        reference = raw.get("query_reference")
        old_digest = raw.get("old_digest")
        raw_occurrences = raw.get("occurrences")
        if not isinstance(reference, str):
            raise DigestRefreshPolicyError("inventory pin reference is invalid")
        _validate_query_reference(reference)
        if not isinstance(old_digest, str) or not DIGEST_RE.fullmatch(old_digest):
            raise DigestRefreshPolicyError("inventory old digest is invalid")
        if not isinstance(raw_occurrences, list) or not raw_occurrences:
            raise DigestRefreshPolicyError("inventory pin occurrences are missing")
        occurrences: list[PinOccurrence] = []
        for item in raw_occurrences:
            if not isinstance(item, dict):
                raise DigestRefreshPolicyError("inventory occurrence is malformed")
            try:
                occurrence = PinOccurrence(
                    path=str(item["path"]),
                    line=int(item["line"]),
                    raw_reference=str(item["raw_reference"]),
                    query_reference=str(item["query_reference"]),
                    old_digest=str(item["old_digest"]),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise DigestRefreshPolicyError("inventory occurrence is invalid") from exc
            if occurrence.query_reference != reference or occurrence.old_digest != old_digest:
                raise DigestRefreshPolicyError("inventory occurrence disagrees with parent pin")
            occurrences.append(occurrence)
        pins.append(
            PinRecord(
                query_reference=reference,
                old_digest=old_digest,
                occurrences=tuple(occurrences),
            )
        )
    return tuple(pins)


def inventory_queries(payload: object) -> tuple[str, ...]:
    return tuple(pin.query_reference for pin in _inventory_pins(payload))


def resolutions_from_tsv(path: Path, *, resolver: str) -> dict[str, object]:
    if not isinstance(resolver, str) or not resolver.strip():
        raise DigestRefreshPolicyError("resolver name is required")
    try:
        info = path.lstat()
    except OSError as exc:
        raise DigestRefreshPolicyError("resolution TSV is unavailable") from exc
    if path.is_symlink() or not path.is_file():
        raise DigestRefreshPolicyError(
            "resolution TSV must be a regular non-symlink file"
        )
    if info.st_size > MAX_INPUT_BYTES:
        raise DigestRefreshPolicyError("resolution TSV exceeds byte bound")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DigestRefreshPolicyError("resolution TSV cannot be read") from exc

    resolved: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        pieces = line.split("\t")
        if len(pieces) != 2:
            raise DigestRefreshPolicyError("resolution TSV row must contain reference and digest")
        reference, raw_digest = pieces
        _validate_query_reference(reference)
        digest = raw_digest.removeprefix("sha256:")
        if not DIGEST_RE.fullmatch(digest):
            raise DigestRefreshPolicyError("resolver returned invalid sha256 digest")
        if reference in resolved:
            raise DigestRefreshPolicyError("resolver returned duplicate image reference")
        resolved[reference] = digest
        if len(resolved) > MAX_OCCURRENCES:
            raise DigestRefreshPolicyError("resolution count bound exceeded")
    if not resolved:
        raise DigestRefreshPolicyError("resolver returned no image digests")

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "resolver": resolver.strip(),
        "resolved": dict(sorted(resolved.items())),
    }
    payload["resolution_digest"] = _json_digest(payload)
    return payload


def _resolution_map(payload: object) -> tuple[str, dict[str, str]]:
    data = _require_schema(payload, kind="resolution")
    expected = data.get("resolution_digest")
    unsigned = dict(data)
    unsigned.pop("resolution_digest", None)
    if not isinstance(expected, str) or expected != _json_digest(unsigned):
        raise DigestRefreshPolicyError("resolution digest does not match content")
    resolver = data.get("resolver")
    resolved = data.get("resolved")
    if not isinstance(resolver, str) or not resolver:
        raise DigestRefreshPolicyError("resolution resolver is missing")
    if not isinstance(resolved, dict) or not resolved:
        raise DigestRefreshPolicyError("resolution map is missing")
    checked: dict[str, str] = {}
    for raw_ref, raw_digest in resolved.items():
        if not isinstance(raw_ref, str) or not isinstance(raw_digest, str):
            raise DigestRefreshPolicyError("resolution map entry is malformed")
        _validate_query_reference(raw_ref)
        if not DIGEST_RE.fullmatch(raw_digest):
            raise DigestRefreshPolicyError("resolution digest is invalid")
        checked[raw_ref] = raw_digest
    return resolver, checked


def build_plan(
    inventory: object,
    resolutions: object,
    *,
    source_commit: str,
) -> dict[str, object]:
    if not COMMIT_RE.fullmatch(source_commit):
        raise DigestRefreshPolicyError("source commit must be a 40-character hexadecimal SHA")
    inventory_data = _require_schema(inventory, kind="inventory")
    pins = _inventory_pins(inventory)
    resolver, resolved = _resolution_map(resolutions)

    expected_refs = {pin.query_reference for pin in pins}
    actual_refs = set(resolved)
    if actual_refs != expected_refs:
        raise DigestRefreshPolicyError("resolution set must exactly match inventory query set")

    entries: list[RefreshEntry] = []
    for pin in pins:
        new_digest = resolved[pin.query_reference]
        if new_digest == pin.old_digest:
            continue
        entries.append(
            RefreshEntry(
                query_reference=pin.query_reference,
                old_digest=pin.old_digest,
                new_digest=new_digest,
                occurrences=pin.occurrences,
            )
        )

    raw_sources = inventory_data.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise DigestRefreshPolicyError("inventory source records are missing")

    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "source_commit": source_commit,
        "inventory_digest": inventory_data["inventory_digest"],
        "resolution_digest": _require_schema(resolutions, kind="resolution")[
            "resolution_digest"
        ],
        "resolver": resolver,
        "sources": raw_sources,
        "entries": [
            {
                "query_reference": entry.query_reference,
                "old_digest": entry.old_digest,
                "new_digest": entry.new_digest,
                "occurrences": [asdict(item) for item in entry.occurrences],
            }
            for entry in entries
        ],
    }
    payload["plan_digest"] = _json_digest(payload)
    return payload


def _source_map(plan: dict[str, object]) -> dict[str, SourceRecord]:
    raw_sources = plan.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise DigestRefreshPolicyError("plan sources are missing")
    result: dict[str, SourceRecord] = {}
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise DigestRefreshPolicyError("plan source is malformed")
        raw_path = raw.get("path")
        raw_sha256 = raw.get("sha256")
        raw_size = raw.get("size")
        if (
            not isinstance(raw_path, str)
            or not isinstance(raw_sha256, str)
            or isinstance(raw_size, bool)
            or not isinstance(raw_size, int)
        ):
            raise DigestRefreshPolicyError("plan source is invalid")
        source = SourceRecord(
            path=raw_path,
            sha256=raw_sha256,
            size=raw_size,
        )
        _validate_relative_source_path(source.path)
        if (
            not DIGEST_RE.fullmatch(source.sha256)
            or source.size < 0
            or source.size > MAX_INPUT_BYTES
        ):
            raise DigestRefreshPolicyError("plan source hash/size is invalid")
        if source.path in result:
            raise DigestRefreshPolicyError("plan contains duplicate source path")
        result[source.path] = source
    return result


def _plan_entries(plan: dict[str, object]) -> tuple[RefreshEntry, ...]:
    raw_entries = plan.get("entries")
    if not isinstance(raw_entries, list):
        raise DigestRefreshPolicyError("plan entries are malformed")
    result: list[RefreshEntry] = []
    seen_occurrences: set[tuple[str, int, str]] = set()
    total_occurrences = 0
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise DigestRefreshPolicyError("plan entry is malformed")
        reference = raw.get("query_reference")
        old_digest = raw.get("old_digest")
        new_digest = raw.get("new_digest")
        raw_occurrences = raw.get("occurrences")
        if not isinstance(reference, str):
            raise DigestRefreshPolicyError("plan reference is invalid")
        _validate_query_reference(reference)
        if (
            not isinstance(old_digest, str)
            or not DIGEST_RE.fullmatch(old_digest)
            or not isinstance(new_digest, str)
            or not DIGEST_RE.fullmatch(new_digest)
            or old_digest == new_digest
        ):
            raise DigestRefreshPolicyError("plan digest transition is invalid")
        if not isinstance(raw_occurrences, list) or not raw_occurrences:
            raise DigestRefreshPolicyError("plan entry has no occurrences")
        occurrences: list[PinOccurrence] = []
        for item in raw_occurrences:
            if not isinstance(item, dict):
                raise DigestRefreshPolicyError("plan occurrence is malformed")
            raw_line = item.get("line", 0)
            if isinstance(raw_line, bool):
                raise DigestRefreshPolicyError("plan occurrence line is invalid")
            try:
                line = int(raw_line)
            except (TypeError, ValueError) as exc:
                raise DigestRefreshPolicyError("plan occurrence line is invalid") from exc
            occurrence = PinOccurrence(
                path=str(item.get("path", "")),
                line=line,
                raw_reference=str(item.get("raw_reference", "")),
                query_reference=str(item.get("query_reference", "")),
                old_digest=str(item.get("old_digest", "")),
            )
            _validate_relative_source_path(occurrence.path)
            if occurrence.line <= 0:
                raise DigestRefreshPolicyError("plan occurrence line is invalid")
            if (
                not occurrence.raw_reference
                or any(
                    char.isspace() or ord(char) < 32 or ord(char) == 127
                    for char in occurrence.raw_reference
                )
                or "@sha256:" in occurrence.raw_reference
            ):
                raise DigestRefreshPolicyError("plan occurrence reference is invalid")
            if occurrence.query_reference != reference or occurrence.old_digest != old_digest:
                raise DigestRefreshPolicyError("plan occurrence disagrees with entry")
            identity = (
                occurrence.path,
                occurrence.line,
                occurrence.raw_reference,
            )
            if identity in seen_occurrences:
                raise DigestRefreshPolicyError("plan contains duplicate occurrence")
            seen_occurrences.add(identity)
            total_occurrences += 1
            if total_occurrences > MAX_OCCURRENCES:
                raise DigestRefreshPolicyError("plan occurrence bound exceeded")
            occurrences.append(occurrence)
        result.append(
            RefreshEntry(
                query_reference=reference,
                old_digest=old_digest,
                new_digest=new_digest,
                occurrences=tuple(occurrences),
            )
        )
    return tuple(result)


def _validated_plan(payload: object) -> dict[str, object]:
    plan = _require_schema(payload, kind="plan")
    expected = plan.get("plan_digest")
    unsigned = dict(plan)
    unsigned.pop("plan_digest", None)
    if not isinstance(expected, str) or expected != _json_digest(unsigned):
        raise DigestRefreshPolicyError("plan digest does not match content")
    source_commit = plan.get("source_commit")
    if not isinstance(source_commit, str) or not COMMIT_RE.fullmatch(source_commit):
        raise DigestRefreshPolicyError("plan source commit is invalid")
    resolver = plan.get("resolver")
    if (
        not isinstance(resolver, str)
        or not resolver
        or resolver != resolver.strip()
        or len(resolver) > 256
        or any(ord(char) < 32 or ord(char) == 127 for char in resolver)
    ):
        raise DigestRefreshPolicyError("plan resolver is invalid")
    for name in ("inventory_digest", "resolution_digest"):
        value = plan.get(name)
        if not isinstance(value, str) or not DIGEST_RE.fullmatch(value):
            raise DigestRefreshPolicyError(f"plan {name} is invalid")
    sources = _source_map(plan)
    entries = _plan_entries(plan)
    for entry in entries:
        for occurrence in entry.occurrences:
            if occurrence.path not in sources:
                raise DigestRefreshPolicyError(
                    "plan occurrence references source outside plan inventory"
                )
    return plan


def _validate_relative_source_path(relative: str) -> str:
    if (
        not isinstance(relative, str)
        or not relative
        or relative.startswith("/")
        or "\\" in relative
        or any(part in {"", ".", ".."} for part in relative.split("/"))
        or any(ord(char) < 32 or ord(char) == 127 for char in relative)
    ):
        raise DigestRefreshPolicyError("plan source path is unsafe")
    if len(relative.encode("utf-8")) > 4096:
        raise DigestRefreshPolicyError("plan source path exceeds byte bound")
    return relative


def _safe_source_path(relative: str) -> Path:
    relative = _validate_relative_source_path(relative)
    path = ROOT.joinpath(*relative.split("/"))
    try:
        path.resolve(strict=True).relative_to(ROOT.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise DigestRefreshStateError("plan source path is unavailable") from exc
    if path.is_symlink() or not path.is_file():
        raise DigestRefreshStateError("plan source must remain a regular file")
    return path


def apply_plan(
    payload: object,
    *,
    expected_source_commit: str,
) -> dict[str, object]:
    plan = _validated_plan(payload)
    if expected_source_commit != plan["source_commit"]:
        raise DigestRefreshStateError("checkout source commit differs from refresh plan")

    sources = _source_map(plan)
    entries = _plan_entries(plan)
    preimages: dict[str, str] = {}
    texts: dict[str, str] = {}

    for relative, source in sources.items():
        path = _safe_source_path(relative)
        raw = path.read_bytes()
        if len(raw) != source.size or _sha256_bytes(raw) != source.sha256:
            raise DigestRefreshStateError("source file changed after inventory")
        try:
            texts[relative] = raw.decode("utf-8")
        except UnicodeError as exc:
            raise DigestRefreshStateError("source file is no longer UTF-8") from exc
        preimages[relative] = source.sha256

    replacements: list[dict[str, object]] = []
    for entry in entries:
        for occurrence in entry.occurrences:
            text = texts.get(occurrence.path)
            if text is None:
                raise DigestRefreshStateError("plan occurrence references untracked source")
            old_token = f"{occurrence.raw_reference}@sha256:{entry.old_digest}"
            new_token = f"{occurrence.raw_reference}@sha256:{entry.new_digest}"
            lines = text.splitlines(keepends=True)
            if not 1 <= occurrence.line <= len(lines):
                raise DigestRefreshStateError("plan occurrence line moved")
            line = lines[occurrence.line - 1]
            if line.count(old_token) != 1:
                raise DigestRefreshStateError("expected digest token not found exactly once")
            lines[occurrence.line - 1] = line.replace(old_token, new_token, 1)
            texts[occurrence.path] = "".join(lines)
            replacements.append(
                {
                    "path": occurrence.path,
                    "line": occurrence.line,
                    "query_reference": entry.query_reference,
                    "old_digest": entry.old_digest,
                    "new_digest": entry.new_digest,
                }
            )

    postimages: dict[str, str] = {}
    changed_paths = sorted({item["path"] for item in replacements})
    for relative in changed_paths:
        encoded = texts[relative].encode("utf-8")
        _atomic_write(ROOT / relative, encoded)
        postimages[relative] = _sha256_bytes(encoded)

    evidence: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "source_commit": plan["source_commit"],
        "plan_digest": plan["plan_digest"],
        "resolver": plan["resolver"],
        "changed_paths": changed_paths,
        "preimages": dict(sorted(preimages.items())),
        "postimages": dict(sorted(postimages.items())),
        "replacements": replacements,
    }
    evidence["evidence_digest"] = _json_digest(evidence)
    return evidence


def _expected_evidence_bindings(
    plan: dict[str, object],
) -> tuple[dict[str, str], list[dict[str, object]], list[str]]:
    sources = _source_map(plan)
    entries = _plan_entries(plan)
    preimages = {
        relative: source.sha256
        for relative, source in sorted(sources.items())
    }
    replacements: list[dict[str, object]] = []
    for entry in entries:
        for occurrence in entry.occurrences:
            replacements.append(
                {
                    "path": occurrence.path,
                    "line": occurrence.line,
                    "query_reference": entry.query_reference,
                    "old_digest": entry.old_digest,
                    "new_digest": entry.new_digest,
                }
            )
    changed_paths = sorted(
        {str(item["path"]) for item in replacements}
    )
    return preimages, replacements, changed_paths


def verify_evidence(plan_payload: object, evidence_payload: object) -> None:
    plan = _validated_plan(plan_payload)
    evidence = _require_schema(evidence_payload, kind="evidence")
    expected = evidence.get("evidence_digest")
    unsigned = dict(evidence)
    unsigned.pop("evidence_digest", None)
    if not isinstance(expected, str) or expected != _json_digest(unsigned):
        raise DigestRefreshPolicyError("evidence digest does not match content")
    if evidence.get("plan_digest") != plan.get("plan_digest"):
        raise DigestRefreshStateError("evidence is not bound to supplied plan")
    if evidence.get("source_commit") != plan.get("source_commit"):
        raise DigestRefreshStateError("evidence source commit mismatch")
    if evidence.get("resolver") != plan.get("resolver"):
        raise DigestRefreshStateError("evidence resolver differs from plan")

    expected_preimages, expected_replacements, expected_changed_paths = (
        _expected_evidence_bindings(plan)
    )
    raw_preimages = evidence.get("preimages")
    raw_replacements = evidence.get("replacements")
    raw_postimages = evidence.get("postimages")
    changed_paths = evidence.get("changed_paths")

    if not isinstance(raw_preimages, dict):
        raise DigestRefreshPolicyError("evidence preimage records are malformed")
    if raw_preimages != expected_preimages:
        raise DigestRefreshStateError("evidence preimages differ from plan")
    if not isinstance(raw_replacements, list):
        raise DigestRefreshPolicyError("evidence replacements are malformed")
    if raw_replacements != expected_replacements:
        raise DigestRefreshStateError("evidence replacements differ from plan")
    if changed_paths != expected_changed_paths:
        raise DigestRefreshStateError("evidence changed paths differ from plan")
    if not isinstance(raw_postimages, dict):
        raise DigestRefreshPolicyError("evidence postimage records are malformed")
    if set(raw_postimages) != set(expected_changed_paths):
        raise DigestRefreshPolicyError("evidence changed paths and postimages differ")

    for relative, raw_digest in raw_postimages.items():
        if (
            not isinstance(relative, str)
            or not isinstance(raw_digest, str)
            or not DIGEST_RE.fullmatch(raw_digest)
        ):
            raise DigestRefreshPolicyError("evidence postimage is malformed")
        path = _safe_source_path(relative)
        if _sha256_file(path) != raw_digest:
            raise DigestRefreshStateError(
                "modified file does not match evidence postimage"
            )


def command_inventory(args: argparse.Namespace) -> int:
    payload = build_inventory(args.extra_file)
    _write_json(Path(args.output), payload)
    print(
        f"inventory: {len(payload['pins'])} image refs across "
        f"{len(payload['sources'])} tracked surfaces"
    )
    return 0


def command_queries(args: argparse.Namespace) -> int:
    payload = _load_json(Path(args.inventory))
    for reference in inventory_queries(payload):
        print(reference)
    return 0


def command_resolutions(args: argparse.Namespace) -> int:
    payload = resolutions_from_tsv(Path(args.input), resolver=args.resolver)
    _write_json(Path(args.output), payload)
    print(f"resolutions: {len(payload['resolved'])} image refs")
    return 0


def command_plan(args: argparse.Namespace) -> int:
    inventory = _load_json(Path(args.inventory))
    resolutions = _load_json(Path(args.resolutions))
    payload = build_plan(
        inventory,
        resolutions,
        source_commit=args.source_commit,
    )
    _write_json(Path(args.output), payload)
    print(f"plan: {len(payload['entries'])} digest changes")
    return 0


def command_apply(args: argparse.Namespace) -> int:
    plan = _load_json(Path(args.plan))
    evidence = apply_plan(
        plan,
        expected_source_commit=args.source_commit,
    )
    _write_json(Path(args.evidence), evidence)
    print(f"applied: {len(evidence['replacements'])} pin replacements")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    plan = _load_json(Path(args.plan))
    evidence = _load_json(Path(args.evidence))
    verify_evidence(plan, evidence)
    print("container digest refresh evidence verified")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    inventory = sub.add_parser("inventory")
    inventory.add_argument("--output", required=True)
    inventory.add_argument("--extra-file", action="append", default=[])
    inventory.set_defaults(func=command_inventory)

    queries = sub.add_parser("queries")
    queries.add_argument("--inventory", required=True)
    queries.set_defaults(func=command_queries)

    resolutions = sub.add_parser("resolutions")
    resolutions.add_argument("--input", required=True)
    resolutions.add_argument("--output", required=True)
    resolutions.add_argument("--resolver", required=True)
    resolutions.set_defaults(func=command_resolutions)

    plan = sub.add_parser("plan")
    plan.add_argument("--inventory", required=True)
    plan.add_argument("--resolutions", required=True)
    plan.add_argument("--source-commit", required=True)
    plan.add_argument("--output", required=True)
    plan.set_defaults(func=command_plan)

    apply_command = sub.add_parser("apply")
    apply_command.add_argument("--plan", required=True)
    apply_command.add_argument("--source-commit", required=True)
    apply_command.add_argument("--evidence", required=True)
    apply_command.set_defaults(func=command_apply)

    verify = sub.add_parser("verify")
    verify.add_argument("--plan", required=True)
    verify.add_argument("--evidence", required=True)
    verify.set_defaults(func=command_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DigestRefreshError as exc:
        print(f"container digest refresh failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
