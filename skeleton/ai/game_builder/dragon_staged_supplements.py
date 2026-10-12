"""Deterministic expansion of Git-pinned catalog *observations* into Dragon leads.

This module accepts an operator-provided, already captured catalog metadata
snapshot. It does not retrieve URLs, attest a license, produce training data,
or instruct the acquisition worker to fetch the referenced destinations.

All emitted batches are verified together against the existing accepted chain
before they may be written to disk. A duplicate by canonical URL is not a new
lead, even when its raw link syntax differs.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import uuid4
import stat
from urllib.parse import urlsplit

from .dragon_discovery_admission import (
    MAX_SUPPLEMENTS, SCHEMA, STATUS_RAW, validate_discovery_chain,
)
from .dragon_source_catalog import canonical_source_url

STAGE_SCHEMA = "skeleton.dragon.raw_catalog_link_observations.v1"
STAGE_STATUS = "staged_raw_catalog_links_not_admitted"
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_BANNED_EXT = re.compile(
    r"\.(?:rom|iso|nds|3ds|cia|gba|gbc|gb|bin|bios|exe|msi|apk|ipa|"
    r"zip|7z|rar|tar|gz|tgz)(?:$|[?#])", re.I,
)
_NOISY_HOSTS = frozenset({
    "img.shields.io", "shields.io", "badgen.net", "api.travis-ci.org",
    "github.com", "raw.githubusercontent.com",
})
_MAX_OBSERVATIONS = 20_000


def read_staged_catalog_snapshot(path: str | Path) -> dict:
    """Load only a regular, bounded repository evidence file with strict JSON.

    The received file has no network or rights authority; SHA identifiers in
    its catalog entries are claims to be checked by a separate acquisition
    control before source content may be fetched.
    """
    file = Path(path)
    root = Path(__file__).resolve().parents[3]
    try:
        resolved = file.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("staged evidence must be inside the repository") from exc
    if not (resolved.startswith("docs/ai/evidence/dragon-new-catalog-metadata-")
            and resolved.endswith(".json")):
        raise ValueError("only staged Dragon catalog evidence is accepted")
    try:
        stat_before = file.lstat()
        if not stat.S_ISREG(stat_before.st_mode) or not 1 <= stat_before.st_size <= 2_000_000:
            raise ValueError("regular bounded staged catalog required")
        fd = os.open(file, os.O_RDONLY |
                     getattr(os, "O_NOFOLLOW", 0) |
                     getattr(os, "O_CLOEXEC", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            raw = stream.read(2_000_001)
            closed = os.fstat(stream.fileno())
        stat_after = file.lstat()
    except OSError as exc:
        raise ValueError("staged catalog changed while reading") from exc
    if (not stat.S_ISREG(opened.st_mode)
            or (stat_before.st_dev, stat_before.st_ino) !=
               (opened.st_dev, opened.st_ino)
            or (stat_after.st_dev, stat_after.st_ino) !=
               (opened.st_dev, opened.st_ino)
            or (opened.st_size, opened.st_mtime_ns) !=
               (closed.st_size, closed.st_mtime_ns)
            or len(raw) != opened.st_size or len(raw) > 2_000_000):
        raise ValueError("staged catalog byte or file identity changed")
    def strict_object(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError("duplicate staged catalog key")
            seen[key] = value
        return seen
    try:
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=strict_object,
                              parse_constant=lambda x: (_ for _ in ()).throw(
                                  ValueError("nonfinite staged catalog constant")))
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ValueError("staged catalog JSON is malformed or ambiguous") from exc
    if (not isinstance(document, dict)
            or document.get("schema") != STAGE_SCHEMA
            or document.get("status") != STAGE_STATUS
            or document.get("training_authorized") is not False
            or document.get("rights_approved") is not False
            or document.get("fetch_authorized") is not False):
        raise ValueError("unapproved staged catalog required")
    return document


def build_catalog_supplements(
    registry: dict, accepted: list[tuple[str, dict]],
    stage: dict, *, first_batch: int, batch_size: int = 600,
    date_slug: str = "20261012",
) -> dict:
    """Compile a validated append-only batch plan, with no file/database writes.

    The caller must explicitly supply the authoritative accepted chain and the
    exact next batch number. The returned pair list is suitable for a separate
    reviewed atomic on-disk materialization and a full chain replay.
    """
    if type(first_batch) is not int or not 1 <= first_batch <= 9999:
        raise ValueError("invalid first batch index")
    if type(batch_size) is not int or not 1 <= batch_size <= 1000:
        raise ValueError("invalid source supplement size")
    if not isinstance(date_slug, str) or not re.fullmatch(r"20[0-9]{6}", date_slug):
        raise ValueError("invalid source batch date")
    earlier = validate_discovery_chain(registry, accepted)
    if (not isinstance(stage, dict) or stage.get("schema") != STAGE_SCHEMA
            or stage.get("status") != STAGE_STATUS
            or stage.get("fetch_authorized") is not False
            or stage.get("rights_approved") is not False
            or stage.get("training_authorized") is not False):
        raise ValueError("only unreviewed staged catalog metadata is admissible")
    catalogs = stage.get("catalogs")
    if not isinstance(catalogs, list) or not 1 <= len(catalogs) <= 64:
        raise ValueError("invalid staged catalog count")
    previous_raw = {
        row["url"] for _, doc in accepted for row in doc["candidates"]
    }
    old_normalized = {row["url"] for row in registry["sources"]}
    old_normalized.update(
        canonical_source_url(raw) for raw in previous_raw
    )
    retained = {}
    seen_catalogs = set()
    skipped = Counter()
    visited = 0
    for catalog in catalogs:
        if not isinstance(catalog, dict):
            raise ValueError("invalid catalog entry")
        repo, commit, blob = (
            catalog.get("repository"), catalog.get("commit_sha"),
            catalog.get("readme_blob_sha"),
        )
        path = catalog.get("readme_path")
        observed = catalog.get("observed")
        if (not isinstance(repo, str) or not _REPO.fullmatch(repo)
                or not isinstance(commit, str) or not _SHA.fullmatch(commit)
                or not isinstance(blob, str) or not _SHA.fullmatch(blob)
                or not isinstance(path, str) or not 1 <= len(path) <= 256
                or path.startswith("/") or ".." in path.split("/")
                or "\\" in path
                or not isinstance(observed, list)
                or len(observed) > 3000):
            raise ValueError("invalid Git-pinned staged README catalog")
        if (repo, commit, blob, path) in seen_catalogs:
            raise ValueError("duplicated staged catalog identity")
        seen_catalogs.add((repo, commit, blob, path))
        for row in observed:
            visited += 1
            if visited > _MAX_OBSERVATIONS or not isinstance(row, dict):
                raise ValueError("staged source observation budget exceeded")
            raw = row.get("url")
            line = row.get("line")
            headers = row.get("headers", [])
            if (not isinstance(raw, str) or not 10 <= len(raw) <= 2048
                    or type(line) is not int or not 1 <= line <= 1_000_000
                    or not isinstance(headers, list) or len(headers) > 12
                    or any(not isinstance(h, str) or not h.strip()
                           or len(h) > 2048 or any(ord(c) < 32 for c in h)
                           for h in headers)):
                raise ValueError("invalid staged link or observed heading")
            # Reject invalid or private URLs rather than silently claiming an
            # unreadable source to be a usable game-engine destination.
            url = canonical_source_url(raw)
            parsed = urlsplit(url)
            if (_BANNED_EXT.search(parsed.path)
                    or parsed.hostname in _NOISY_HOSTS
                    and parsed.path.startswith(("/sindresorhus/awesome", "/badges/"))
                    or "/actions/workflows/" in parsed.path):
                skipped["binary_or_badge"] += 1
                continue
            if raw in previous_raw or url in old_normalized:
                skipped["previously_seen"] += 1
                continue
            origin = {
                "repository": repo, "commit_sha": commit,
                "readme_blob_sha": blob, "exact_url": raw,
                "line": line, "headers": headers,
            }
            if url in retained:
                if len(retained[url]["discoveries"]) >= 32:
                    raise ValueError("excessive catalog provenance for one URL")
                prior = retained[url]
                prior["discoveries"].append(origin)
                if raw < prior["url"]:
                    prior["url"] = raw
                    prior["source_id"] = (
                        "source-" + sha256(raw.encode("utf-8")).hexdigest()
                    )
                skipped["same_canonical_new_link"] += 1
                continue
            retained[url] = {
                "url": raw,
                "source_id": "source-" + sha256(raw.encode("utf-8")).hexdigest(),
                "availability": "not_checked",
                "rights": "not_assessed",
                "independence": "not_assessed",
                "canonical_admission": False,
                "training_authorized": False,
                "discoveries": [origin],
            }
    if stage.get("raw_observation_count") is not None and (
            type(stage["raw_observation_count"]) is not int
            or stage["raw_observation_count"] != visited):
        raise ValueError("staged observation count conflicts with supplied catalogs")
    staged_catalogs = [
        {"repository": c["repository"], "commit_sha": c["commit_sha"],
         "readme_blob_sha": c["readme_blob_sha"], "readme_path": c["readme_path"]}
        for c in catalogs
    ]
    rows = sorted(retained.values(), key=lambda row: (
        canonical_source_url(row["url"]), row["url"]
    ))
    for row in rows:
        row["discoveries"].sort(key=lambda o: (
            o["repository"], o["commit_sha"], o["readme_blob_sha"],
            o["exact_url"], o["line"], tuple(o["headers"])
        ))
    batch_count = (len(rows) + batch_size - 1) // batch_size
    if len(accepted) + batch_count > MAX_SUPPLEMENTS:
        raise ValueError("source campaign exceeds finite evidence-chain budget")
    parents = [path for path, _ in accepted]
    batches = []
    total = earlier["raw_total_discovered"]
    for i in range(batch_count):
        part = rows[i*batch_size:(i+1)*batch_size]
        next_total = total + len(part)
        name = (
            "docs/ai/evidence/dragon-source-expansion-"
            + date_slug + "-batch-" + f"{first_batch+i:04d}.json"
        )
        if name in parents:
            raise ValueError("source batch filename collides with prior evidence")
        document = {
            "schema": SCHEMA,
            "status": STATUS_RAW,
            "recorded_on": date_slug[:4]+"-"+date_slug[4:6]+"-"+date_slug[6:],
            "baseline_registry_digest": registry["catalog_digest"],
            "requested_total_urls": registry["unique_urls"]*10,
            "target_interpretation": "Unreviewed canonical-distinct Git-pinned catalog link leads",
            "parents": parents[:], "catalogs": staged_catalogs,
            "counts": {
                "previous_raw_provisional_urls": total,
                "new_raw_candidate_urls": len(part),
                "raw_provisional_urls": next_total,
            },
            "candidates": part,
            "limitations": [
                "Git identities are catalog metadata claims, not fetched-target proof.",
                "No linked source, game ROM, media, legal right or content has been approved.",
                "No crawler job or model-memory promotion is authorized.",
            ],
        }
        batches.append((name, document))
        parents.append(name)
        total = next_total
    if batches:
        checked = validate_discovery_chain(registry, [*accepted, *batches])
        if checked["raw_total_discovered"] != total:
            raise ValueError("generated discovery evidence chain does not reconcile")
    return {
        "schema": "skeleton.dragon.staged_discovery_compilation.v1",
        "staged_observations": visited,
        "new_canonical_link_leads": len(rows),
        "start_raw_leads": earlier["raw_total_discovered"],
        "end_raw_leads": total,
        "skipped": dict(sorted(skipped.items())),
        "supplements": batches,
        "staged_rights_approved": False,
        "crawler_authorized": False,
        "training_authorized": False,
    }


def materialize_staged_supplements(
    registry: dict, accepted: list[tuple[str, dict]],
    stage: dict, *, first_batch: int, batch_size: int = 600,
    authorized: bool, root: str | Path | None = None,
) -> dict:
    """Write validated evidence to regular new files only, with no overwrite.

    The compiler rechecks all accepted parent receipts before generating a
    complete plan. Files are fully written and fsynced as hidden temporary
    files, then exposed through no-clobber hard links. Any failure removes
    only the files created by this call. No SQLite or crawler state is changed.
    """
    if authorized is not True:
        raise PermissionError("explicit trusted source-evidence writer required")
    prepared = build_catalog_supplements(
        registry, accepted, stage, first_batch=first_batch,
        batch_size=batch_size,
    )
    base = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    evidence_dir = base / "docs/ai/evidence"
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise ValueError("regular in-repository evidence directory required")
    specs = []
    for name, document in prepared["supplements"]:
        if (not name.startswith("docs/ai/evidence/dragon-source-expansion-")
                or not re.fullmatch(
                    r"dragon-source-expansion-20[0-9]{6}-batch-[0-9]{4}\.json",
                    name.rsplit("/", 1)[-1])):
            raise ValueError("noncanonical new source evidence filename")
        destination = base / name
        if destination.parent != evidence_dir or destination.is_symlink() or destination.exists():
            raise FileExistsError("source evidence path already exists")
        payload = (json.dumps(document, ensure_ascii=False, indent=2,
                              sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        if len(payload) > 8_000_000:
            raise ValueError("generated catalog evidence exceeds byte budget")
        specs.append((destination, payload))
    created = []
    temps = []
    dirfd = os.open(evidence_dir, os.O_RDONLY |
                    getattr(os, "O_DIRECTORY", 0) |
                    getattr(os, "O_NOFOLLOW", 0))
    try:
        for destination, payload in specs:
            tempname = ".dragon-staged-" + uuid4().hex + ".tmp"
            tempfd = os.open(
                tempname, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=dirfd)
            temps.append(tempname)
            with os.fdopen(tempfd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        for (destination, payload), tempname in zip(specs, temps):
            # Unlike replace/rename, link() fails if another operator has
            # created the same evidence path during the staging window.
            os.link(tempname, destination.name, src_dir_fd=dirfd,
                    dst_dir_fd=dirfd, follow_symlinks=False)
            created.append((destination.name, payload))
        os.fsync(dirfd)
    except Exception:
        for name, payload in reversed(created):
            # Never remove a file another process replaced or modified.
            try:
                stat_now = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
                if stat_now.st_size != len(payload):
                    continue
                fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                             dir_fd=dirfd)
                with os.fdopen(fd, "rb") as file:
                    if file.read(len(payload) + 1) == payload:
                        os.unlink(name, dir_fd=dirfd)
            except OSError:
                pass
        raise
    finally:
        for tempname in temps:
            try:
                os.unlink(tempname, dir_fd=dirfd)
            except FileNotFoundError:
                pass
        os.close(dirfd)
    return {
        "schema": "skeleton.dragon.materialized_catalog_evidence.v1",
        "new_source_leads": prepared["new_canonical_link_leads"],
        "raw_url_total": prepared["end_raw_leads"],
        "evidence_files_created": [name for name, _ in created],
        "overwrite_performed": False,
        "database_modified": False,
        "crawl_authorized": False,
        "rights_approved": False,
        "training_authorized": False,
    }
