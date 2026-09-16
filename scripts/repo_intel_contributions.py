#!/usr/bin/env python3
"""Deterministic contributor, bot, automation, and AI provenance inventory.

This layer reports observable repository evidence. It deliberately separates direct
Git contribution evidence from operational surfaces and user-declared tooling so a
model/tool is never credited for a commit merely because its name appears in prose,
a branch, a model catalog, or an instruction file.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import repo_intel as base

ROOT = base.ROOT
_IDENT_RE = re.compile(r"^\s*(.*?)\s*<([^>]+)>\s*$")
_TRAILER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):\s*(.+?)\s*$")


def _registry() -> dict[str, Any]:
    return base.load_json("contributors.json")


def _norm(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _unknown_id(name: str, email: str) -> str:
    digest = hashlib.sha256(f"{_norm(name)}\0{_norm(email)}".encode("utf-8")).hexdigest()[:12]
    kind = "bot" if _looks_bot(name, email) else "identity"
    return f"unknown-{kind}:{digest}"


def _looks_bot(name: str, email: str) -> bool:
    text = f"{name} {email}".casefold()
    return "[bot]" in text or name.casefold().endswith(" bot") or "github-actions" in text


def _actor_maps(registry: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    actors = {str(actor["id"]): dict(actor) for actor in registry.get("actors", [])}
    exact: dict[str, str] = {}
    for actor_id, actor in actors.items():
        for value in [actor.get("display_name", ""), *actor.get("aliases", []), *actor.get("identity_patterns", [])]:
            if value:
                exact[_norm(str(value))] = actor_id
    return actors, exact


def _match_actor(name: str, email: str, actors: dict[str, dict[str, Any]], exact: dict[str, str]) -> str:
    for value in (email, name, f"{name} <{email}>"):
        actor_id = exact.get(_norm(value))
        if actor_id:
            return actor_id
    return _unknown_id(name, email)


def _parse_identity(value: str) -> tuple[str, str]:
    match = _IDENT_RE.match(value)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return value.strip(), ""


def _parse_log(limit: int) -> list[dict[str, str]]:
    raw = base.git(
        "log",
        "-n",
        str(limit),
        "--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B%x00",
        check=False,
    )
    fields = raw.split("\0")
    records: list[dict[str, str]] = []
    index = 0
    while index + 5 < len(fields):
        sha = fields[index].strip()
        author_name = fields[index + 1].strip()
        author_email = fields[index + 2].strip()
        committer_name = fields[index + 3].strip()
        committer_email = fields[index + 4].strip()
        body = fields[index + 5].strip()
        index += 6
        if not sha:
            continue
        records.append(
            {
                "sha": sha,
                "author_name": author_name,
                "author_email": author_email,
                "committer_name": committer_name,
                "committer_email": committer_email,
                "body": body,
                "subject": body.splitlines()[0] if body else "",
            }
        )
    return records


def _trailers(body: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for line in body.splitlines():
        match = _TRAILER_RE.match(line.strip())
        if match:
            result.append((match.group(1).casefold(), match.group(2).strip()))
    return result


def _surface_evidence(snapshot: dict[str, Any], actors: dict[str, dict[str, Any]], records: list[dict[str, str]]) -> dict[str, Any]:
    paths = [str(row["path"]) for row in snapshot.get("files", [])]
    by_actor: dict[str, dict[str, Any]] = {}
    for actor_id, actor in actors.items():
        instruction_files = [path for path in actor.get("instruction_files", []) if path in paths]
        prefixes = actor.get("surface_prefixes", [])
        surface_paths = sorted(
            path for path in paths if any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)
        )
        terms = [_norm(str(term)) for term in actor.get("surface_terms", []) if term]
        message_commits = []
        if terms:
            for record in records:
                haystack = record["body"].casefold()
                if any(term in haystack for term in terms):
                    message_commits.append({"sha": record["sha"], "subject": record["subject"]})
        by_actor[actor_id] = {
            "instruction_files": instruction_files,
            "surface_paths": surface_paths[:100],
            "surface_path_count": len(surface_paths),
            "message_reference_count": len(message_commits),
            "message_reference_samples": message_commits[:25],
        }
    return by_actor


def build(snapshot: dict[str, Any]) -> dict[str, Any]:
    registry = _registry()
    limit = int(registry.get("history_commit_limit", 3000))
    actors, exact = _actor_maps(registry)
    records = _parse_log(limit)
    direct_keys = {str(key).casefold() for key in registry.get("direct_trailer_keys", [])}
    info_keys = {str(key).casefold() for key in registry.get("informational_trailer_keys", [])}

    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "author_commits": 0,
            "committer_commits": 0,
            "direct_trailer_commits": 0,
            "direct_commit_participation": set(),
            "informational_trailer_mentions": 0,
            "samples": [],
        }
    )
    unknown_meta: dict[str, dict[str, Any]] = {}
    nonhuman_direct_evidence: list[dict[str, Any]] = []

    for record in records:
        sha = record["sha"]
        author_id = _match_actor(record["author_name"], record["author_email"], actors, exact)
        committer_id = _match_actor(record["committer_name"], record["committer_email"], actors, exact)
        for actor_id, name, email in (
            (author_id, record["author_name"], record["author_email"]),
            (committer_id, record["committer_name"], record["committer_email"]),
        ):
            if actor_id.startswith("unknown-"):
                unknown_meta.setdefault(
                    actor_id,
                    {
                        "id": actor_id,
                        "display_name": name or "unknown",
                        "kind": "bot-like" if _looks_bot(name, email) else "unclassified",
                    },
                )
        stats[author_id]["author_commits"] += 1
        stats[author_id]["direct_commit_participation"].add(sha)
        stats[committer_id]["committer_commits"] += 1
        stats[committer_id]["direct_commit_participation"].add(sha)

        direct_trailer_ids: set[str] = set()
        informational: list[dict[str, str]] = []
        for key, value in _trailers(record["body"]):
            name, email = _parse_identity(value)
            actor_id = _match_actor(name, email, actors, exact)
            if actor_id.startswith("unknown-"):
                unknown_meta.setdefault(
                    actor_id,
                    {
                        "id": actor_id,
                        "display_name": name or "unknown",
                        "kind": "bot-like" if _looks_bot(name, email) else "unclassified",
                    },
                )
            if key in direct_keys:
                direct_trailer_ids.add(actor_id)
            elif key in info_keys:
                stats[actor_id]["informational_trailer_mentions"] += 1
                informational.append({"key": key, "actor": actor_id})
        for actor_id in direct_trailer_ids:
            stats[actor_id]["direct_trailer_commits"] += 1
            stats[actor_id]["direct_commit_participation"].add(sha)

        direct_ids = {author_id, committer_id, *direct_trailer_ids}
        for actor_id in direct_ids:
            actor = actors.get(actor_id)
            if actor and actor.get("kind") != "human":
                nonhuman_direct_evidence.append(
                    {
                        "sha": sha,
                        "subject": record["subject"],
                        "actor": actor_id,
                        "roles": sorted(
                            role
                            for role, matched in (
                                ("author", actor_id == author_id),
                                ("committer", actor_id == committer_id),
                                ("direct-trailer", actor_id in direct_trailer_ids),
                            )
                            if matched
                        ),
                    }
                )
        if informational:
            pass

    surfaces = _surface_evidence(snapshot, actors, records)
    actor_rows: list[dict[str, Any]] = []
    for actor_id, actor in sorted(actors.items()):
        data = stats[actor_id]
        samples = [item for item in nonhuman_direct_evidence if item["actor"] == actor_id][:25]
        surface = surfaces.get(actor_id, {})
        actor_rows.append(
            {
                "id": actor_id,
                "display_name": actor.get("display_name", actor_id),
                "kind": actor.get("kind", "unknown"),
                "evidence_class": actor.get("evidence_class", "unknown"),
                "direct_author_commits": data["author_commits"],
                "direct_committer_commits": data["committer_commits"],
                "explicit_direct_trailer_commits": data["direct_trailer_commits"],
                "direct_commit_participation": len(data["direct_commit_participation"]),
                "informational_trailer_mentions": data["informational_trailer_mentions"],
                "instruction_files_present": surface.get("instruction_files", []),
                "operational_surface_path_count": surface.get("surface_path_count", 0),
                "operational_surface_paths": surface.get("surface_paths", []),
                "commit_message_reference_count": surface.get("message_reference_count", 0),
                "commit_message_reference_samples": surface.get("message_reference_samples", []),
                "direct_evidence_samples": samples,
            }
        )

    unknown_rows = []
    for actor_id, meta in sorted(unknown_meta.items()):
        data = stats[actor_id]
        unknown_rows.append(
            {
                **meta,
                "direct_author_commits": data["author_commits"],
                "direct_committer_commits": data["committer_commits"],
                "explicit_direct_trailer_commits": data["direct_trailer_commits"],
                "direct_commit_participation": len(data["direct_commit_participation"]),
            }
        )

    total_text = base.git("rev-list", "--count", "HEAD", check=False).strip()
    try:
        total_commits = int(total_text)
    except ValueError:
        total_commits = len(records)
    workflows = sorted(
        str(row["path"])
        for row in snapshot.get("files", [])
        if str(row["path"]).startswith(".github/workflows/")
    )
    nonhuman_direct_evidence.sort(key=lambda item: (item["sha"], item["actor"], item["roles"]))
    return {
        "schema": 1,
        "coverage": {
            "repository_commit_count": total_commits,
            "scanned_commit_count": len(records),
            "history_commit_limit": limit,
            "history_truncated": total_commits > len(records),
        },
        "actors": actor_rows,
        "unknown_direct_identities": unknown_rows,
        "nonhuman_direct_evidence": nonhuman_direct_evidence[:1500],
        "nonhuman_direct_evidence_count": len(nonhuman_direct_evidence),
        "nonhuman_direct_evidence_truncated": len(nonhuman_direct_evidence) > 1500,
        "automation_surfaces": {
            "workflow_count": len(workflows),
            "workflow_files": workflows,
        },
        "semantics": registry.get("semantics", {}),
    }


def check_contracts() -> None:
    payload = _registry()
    if int(payload.get("schema", 0)) != 1:
        raise RuntimeError("contributors.json schema must be 1")
    if int(payload.get("history_commit_limit", 0)) < 100:
        raise RuntimeError("contributors.json history_commit_limit must be >= 100")
    actor_ids = [str(actor.get("id", "")) for actor in payload.get("actors", [])]
    if not actor_ids or len(actor_ids) != len(set(actor_ids)):
        raise RuntimeError("contributors.json actor IDs must be present and unique")
    if not payload.get("direct_trailer_keys"):
        raise RuntimeError("contributors.json must define direct contribution trailer keys")
    print(f"repo-intel-contributions: contract valid ({len(actor_ids)} canonical actors)")


if __name__ == "__main__":
    raise SystemExit("repo_intel_contributions is a library layer; use scripts/repo_intel_frontier.py")
