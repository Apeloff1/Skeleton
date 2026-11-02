"""Assemble a release candidate: next version, changelog and manifest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from skeleton.build.delivery._util import DeliveryError, require_sha1
from skeleton.build.delivery.artifact_manifest import ArtifactEntry, ArtifactManifest, build_manifest
from skeleton.build.delivery.changelog import Change, next_version, parse_commit, render

MAX_RELEASE_COMMITS = 8192
MAX_COMMIT_MESSAGE_CHARS = 10000


@dataclass(frozen=True)
class ReleaseCandidate:
    version: str
    changelog: str
    manifest: ArtifactManifest
    changes: tuple[Change, ...]


def release_id_for(product: str, version: str) -> str:
    return f"{product}-{version}".replace("+", "_")


def prepare(
    *,
    product: str,
    current_version: str,
    source_commit: str,
    commits: Iterable[tuple[str, str]],
    artifacts: Iterable[ArtifactEntry],
    date: str,
    metadata: Mapping[str, str] | None = None,
    allow_empty: bool = False,
) -> ReleaseCandidate:
    require_sha1(source_commit, field="source_commit")
    # Commit evidence is not an arbitrary stream: bound it and reject
    # duplicate or malformed identities before generating release provenance.
    parsed: list[Change] = []
    seen: set[str] = set()
    for count, item in enumerate(commits, 1):
        if count > MAX_RELEASE_COMMITS:
            raise DeliveryError("release commit inventory exceeds bound")
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise DeliveryError("release commit entry must contain sha and message")
        sha, msg = item
        require_sha1(sha, field="release commit sha")
        if sha in seen:
            raise DeliveryError("duplicate release commit identity")
        seen.add(sha)
        if type(msg) is not str or len(msg) > MAX_COMMIT_MESSAGE_CHARS:
            raise DeliveryError("release commit message exceeds bound")
        change = parse_commit(sha, msg)
        if change is not None:
            parsed.append(change)
    changes = tuple(parsed)
    version = next_version(current_version, changes)
    if str(version) == current_version and not allow_empty:
        raise DeliveryError("no releasable changes since current version")
    manifest = build_manifest(
        release_id=release_id_for(product, str(version)),
        version=str(version),
        source_commit=source_commit,
        artifacts=artifacts,
        metadata={"product": product, **(metadata or {})},
    )
    return ReleaseCandidate(str(version), render(version, changes, date=date), manifest, changes)
