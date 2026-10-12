"""Reproducible new-source discovery from locally acquired, Git-pinned catalog text.

Never downloads sources. A trusted acquisition operator must provide read-only
README bytes acquired under its own network/rights policy. Git object IDs and
SHA-256 bind the bytes; all links remain unreviewed, unfetched candidates.
"""
from __future__ import annotations

import argparse
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import re

from .contracts import canonical_json
from .dragon_almanacs import read_source_registry
from .dragon_discovery_admission import _supplement, validate_discovery_chain
from .dragon_source_catalog import extract_catalog

ROOT = Path(__file__).resolve().parents[3]
_SHA40 = re.compile(r"[0-9a-f]{40}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
MAX_README = 2_000_000


def _load_catalog_manifest(path: str | Path) -> list[dict]:
    raw = Path(path).read_bytes()
    if len(raw) > 131_072:
        raise ValueError("catalog manifest byte budget exceeded")
    manifest = json.loads(raw)
    entries = manifest.get("catalogs")
    if (manifest.get("schema") != "skeleton.dragon.pinned_catalog_sources.v1"
            or manifest.get("crawling_authorized") is not False
            or manifest.get("training_authorized") is not False
            or manifest.get("rights_review") != "not_assessed"
            or not isinstance(entries, list) or not 1 <= len(entries) <= 128):
        raise ValueError("unreviewed pinned source manifest required")
    seen = set()
    for entry in entries:
        if (not isinstance(entry, dict)
                or not _REPO.fullmatch(entry.get("repository", ""))
                or not _SHA40.fullmatch(entry.get("commit_sha", ""))
                or not _SHA40.fullmatch(entry.get("readme_blob_sha", ""))):
            raise ValueError("invalid pinned source identity")
        if entry["repository"] in seen:
            raise ValueError("duplicate catalog repository")
        seen.add(entry["repository"])
    return entries


def _local_catalog(cache: str | Path, entry: dict, observed_at: str) -> dict:
    """Recompute Git's SHA-1 blob ID; do not trust a user-supplied file name."""
    root = Path(cache).resolve()
    repo = entry["repository"]
    target = (root / repo / "README.md").resolve()
    if not target.is_relative_to(root):
        raise ValueError("catalog file escapes source cache")
    with target.open("rb") as stream:
        raw = stream.read(MAX_README + 1)
    if len(raw) > MAX_README:
        raise ValueError("catalog exceeds bounded text size")
    identifier = sha1(b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw).hexdigest()
    if identifier != entry["readme_blob_sha"]:
        raise ValueError("catalog bytes differ from pinned Git blob")
    content = raw.decode("utf-8", errors="strict")
    url = "https://github.com/" + repo + "/blob/" + entry["commit_sha"] + "/README.md"
    return extract_catalog(content, catalog_url=url,
                           blob_sha=entry["readme_blob_sha"], observed_at=observed_at)


def build_expansion(registry: dict, previous: list[tuple[str, dict]],
                    pinned: list[dict], cache: str | Path, *, observed_at: str) -> dict:
    """Construct a new non-authoritative supplement and validate the whole chain."""
    if not previous:
        raise ValueError("previous discovery lineage required")
    verified = validate_discovery_chain(registry, previous)
    prior_urls = set(row["url"] for row in registry["sources"])
    for _, old in previous:
        prior_urls.update(row["url"] for row in old["candidates"])
    if len(prior_urls) != verified["total_discovered"]:
        raise ValueError("previous discovered URL count mismatch")
    claims = {}
    catalogs = []
    for entry in pinned:
        result = _local_catalog(cache, entry, observed_at)
        catalogs.append({"repository": entry["repository"],
                         "commit_sha": entry["commit_sha"],
                         "readme_blob_sha": entry["readme_blob_sha"],
                         "content_sha256": result["manifest"]["content_sha256"]})
        for item in result["sources"]:
            if item["url"] in prior_urls:
                continue
            row = claims.setdefault(item["url"], {
                "source_id": item["source_id"], "url": item["url"],
                "availability": "not_checked", "rights": "not_assessed",
                "independence": "not_assessed", "training_authorized": False,
                "canonical_admission": False, "discoveries": []})
            if row["source_id"] != item["source_id"]:
                raise ValueError("source digest conflict")
            for origin in item["discoveries"]:
                receipt = {"repository": entry["repository"],
                           "commit_sha": entry["commit_sha"],
                           "readme_blob_sha": entry["readme_blob_sha"],
                           "exact_url": item["url"],
                           "line": origin["line"],
                           "headers": origin["headers"]}
                if receipt not in row["discoveries"]:
                    row["discoveries"].append(receipt)
            if len(row["discoveries"]) > 128:
                raise ValueError("individual URL provenance capacity exceeded")
    candidates = sorted(claims.values(), key=lambda x: x["url"])
    for item in candidates:
        item["discoveries"].sort(key=lambda x: (x["repository"], x["line"]))
    total = len(prior_urls) + len(candidates)
    doc = {
        "schema": "skeleton.dragon.source_discovery_supplement.v1",
        "recorded_at": observed_at,
        "baseline_registry_digest": registry["catalog_digest"],
        "requested_total_urls": registry["unique_urls"] * 10,
        "target_interpretation": "ten times pinned discovery baseline; candidates are not grants",
        "status": "partial_discovery_only_not_ingested_into_canonical_queue",
        "parents": [p for p, _ in previous],
        "catalogs": catalogs,
        "counts": {
            "previous_provisional_total_urls": len(prior_urls),
            "new_candidate_urls": len(candidates),
            "provisional_total_urls": total,
            "requested_total_urls": registry["unique_urls"] * 10,
        },
        "candidates": candidates,
        "limitations": {
            "network_fetches": 0, "training_authorized": False,
            "source_approval": "not_assessed",
            "rights": "not_assessed",
            "git_revision": "bound to local README blob; remote ownership not independently reviewed"
        },
    }
    validate_discovery_chain(registry, [*previous, ("__pending__", doc)])
    return doc


def main():
    parser = argparse.ArgumentParser(description="Produce a pinned discovery-only Dragon expansion")
    parser.add_argument("--registry", default=str(ROOT / "skeleton/ai/game_builder/catalogs/dragon_sources_20261010"))
    parser.add_argument("--catalog-manifest", default=str(ROOT / "machine/dragon_pinned_crawl_catalogs_20261012.json"))
    parser.add_argument("--cache", required=True, help="Offline Git-pinned README cache; never fetched by this command")
    parser.add_argument("--supplement", action="append", required=True, help="Prior evidence, chronological order")
    parser.add_argument("--observed-at", required=True, help="UTC timestamp of approved catalog snapshot retrieval")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args()
    if not args.trusted_local_operator:
        parser.error("authenticated local acquisition operator acknowledgement required")
    registry = read_source_registry(args.registry)
    prior = [_supplement(path) for path in args.supplement]
    pinned = _load_catalog_manifest(args.catalog_manifest)
    doc = build_expansion(registry, prior, pinned, args.cache, observed_at=args.observed_at)
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "docs/ai/evidence") or not output.name.startswith("dragon-source-expansion-"):
        parser.error("new evidence must live under repository docs/ai/evidence")
    data = canonical_json(doc).encode("utf-8") + b"\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(output, flags, 0o644)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    print(canonical_json({"output": str(output), "new_candidate_urls": doc["counts"]["new_candidate_urls"],
                          "provisional_total_urls": doc["counts"]["provisional_total_urls"],
                          "approved": 0, "training_authorized": False}))


if __name__ == "__main__":
    main()
