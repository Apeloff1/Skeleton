#!/usr/bin/env python3
"""Deterministic artifact-lineage extraction for repository intelligence.

The initial high-confidence surface is container construction because Dockerfiles
and Compose build contexts provide explicit source -> stage relationships. The
index remains stdlib-only and never infers produced files from arbitrary shell
commands. Directory/glob inputs use selector nodes instead of fan-out to every
matched file, keeping large-repo graph cost bounded.
"""
from __future__ import annotations

from collections import defaultdict, deque
import json
from pathlib import Path, PurePosixPath
import shlex
import sys
from typing import Any, Iterable

import repo_intel as base

ROOT = base.ROOT


def _read_text(path: str) -> str | None:
    try:
        return (ROOT / path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Join Dockerfile continuations while preserving the first source line."""
    result: list[tuple[int, str]] = []
    buffer = ""
    start = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if not buffer:
            start = lineno
        if stripped.endswith("\\"):
            buffer += stripped[:-1].rstrip() + " "
            continue
        buffer += stripped
        if buffer:
            result.append((start, buffer.strip()))
        buffer = ""
    if buffer:
        result.append((start, buffer.strip()))
    return result


def _parse_compose_builds(text: str) -> list[dict[str, str | None]]:
    """Parse the small Compose build-context subset needed for lineage.

    This is intentionally indentation-aware rather than a general YAML parser.
    Unsupported forms remain absent instead of being guessed.
    """
    builds: list[dict[str, str | None]] = []
    in_services = False
    service: str | None = None
    in_build = False
    current: dict[str, str | None] | None = None

    def flush() -> None:
        nonlocal current
        if current and current.get("service") and current.get("context"):
            builds.append(current)
        current = None

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if indent == 0:
            if stripped == "services:":
                in_services = True
                continue
            if in_services:
                flush()
                break
        if not in_services:
            continue
        if indent == 2 and stripped.endswith(":"):
            flush()
            service = stripped[:-1].strip()
            in_build = False
            continue
        if indent == 4 and stripped == "build:":
            flush()
            in_build = True
            current = {"service": service, "context": None, "dockerfile": None, "target": None}
            continue
        if indent <= 4 and in_build:
            flush()
            in_build = False
        if in_build and current is not None and indent >= 6 and ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key in {"context", "dockerfile", "target"}:
                current[key] = value
    flush()
    return builds


def compose_build_contexts(snapshot: dict[str, Any]) -> dict[str, list[dict[str, str | None]]]:
    paths = {str(row["path"]) for row in snapshot.get("files", [])}
    result: dict[str, list[dict[str, str | None]]] = defaultdict(list)
    for compose in sorted(
        path for path in paths if Path(path).name.lower() in {"docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
    ):
        text = _read_text(compose)
        if text is None:
            continue
        for item in _parse_compose_builds(text):
            context = str(item.get("context") or "").rstrip("/") or "."
            dockerfile = item.get("dockerfile")
            if dockerfile:
                df = PurePosixPath(str(dockerfile)).as_posix()
            else:
                df = (PurePosixPath(context) / "Dockerfile").as_posix()
            df = df.removeprefix("./")
            result[df].append({**item, "compose": compose})
    return {key: value for key, value in sorted(result.items())}


def _docker_tokens(rest: str) -> tuple[list[str], str | None, str | None]:
    """Return sources, destination, and optional --from stage."""
    rest = rest.strip()
    if rest.startswith("["):
        try:
            items = json.loads(rest)
        except json.JSONDecodeError:
            return [], None, None
        if not isinstance(items, list) or len(items) < 2 or not all(isinstance(x, str) for x in items):
            return [], None, None
        return list(items[:-1]), str(items[-1]), None

    try:
        tokens = shlex.split(rest, comments=False, posix=True)
    except ValueError:
        return [], None, None
    from_stage: str | None = None
    positional: list[str] = []
    for token in tokens:
        if token.startswith("--from="):
            from_stage = token.split("=", 1)[1]
        elif token.startswith("--"):
            continue
        else:
            positional.append(token)
    if len(positional) < 2:
        return [], None, from_stage
    return positional[:-1], positional[-1], from_stage


def _normalise_context(context: str) -> str:
    value = PurePosixPath(context).as_posix()
    return "" if value in {".", ""} else value.strip("/")


def _resolve_selector(context: str, source: str, tracked: set[str]) -> dict[str, Any]:
    """Resolve an explicit repository input selector without expanding the graph."""
    if "$" in source:
        return {"selector": source, "kind": "dynamic", "matched_count": 0, "samples": []}
    source_norm = source.lstrip("./")
    base = _normalise_context(context)
    joined = PurePosixPath(base, source_norm).as_posix() if base else PurePosixPath(source_norm).as_posix()
    joined = joined.rstrip("/")
    if any(char in joined for char in "*?["):
        # Do not implement shell glob semantics independently; retain selector as
        # unresolved explicit evidence rather than manufacture false matches.
        return {"selector": joined, "kind": "glob", "matched_count": 0, "samples": []}
    if joined in tracked:
        return {"selector": joined, "kind": "file", "matched_count": 1, "samples": [joined]}
    prefix = joined + "/"
    matches = sorted(path for path in tracked if path.startswith(prefix))
    if matches:
        return {
            "selector": joined + "/",
            "kind": "directory",
            "matched_count": len(matches),
            "samples": matches[:20],
        }
    return {"selector": joined, "kind": "missing", "matched_count": 0, "samples": []}


def parse_dockerfile(
    path: str,
    text: str,
    contexts: list[dict[str, str | None]],
    tracked: set[str],
) -> dict[str, Any]:
    default_context = PurePosixPath(path).parent.as_posix()
    if default_context == ".":
        default_context = ""
    context_values = sorted({str(item.get("context") or ".") for item in contexts}) or [default_context or "."]
    context_precision = "compose" if contexts else "dockerfile-parent-default"

    stages: list[dict[str, Any]] = []
    copies: list[dict[str, Any]] = []
    stage_aliases: dict[str, str] = {}
    current_stage: str | None = None

    for lineno, line in _logical_lines(text):
        upper = line.upper()
        if upper.startswith("FROM "):
            try:
                tokens = shlex.split(line)
            except ValueError:
                tokens = line.split()
            alias: str | None = None
            image = tokens[1] if len(tokens) > 1 else "unknown"
            for idx, token in enumerate(tokens[:-1]):
                if token.upper() == "AS":
                    alias = tokens[idx + 1]
                    break
            stage_index = len(stages)
            stage_name = alias or f"stage-{stage_index}"
            stage_id = f"artifact:container-stage:{path}:{stage_name}"
            stages.append(
                {
                    "id": stage_id,
                    "dockerfile": path,
                    "stage": stage_name,
                    "stage_index": stage_index,
                    "base": image,
                    "line": lineno,
                    "final": False,
                }
            )
            current_stage = stage_id
            stage_aliases[stage_name] = stage_id
            continue

        op = None
        if upper.startswith("COPY "):
            op = "COPY"
        elif upper.startswith("ADD "):
            op = "ADD"
        if not op or current_stage is None:
            continue
        sources, destination, from_stage = _docker_tokens(line[len(op):])
        if not sources or destination is None:
            copies.append(
                {
                    "dockerfile": path,
                    "line": lineno,
                    "operation": op,
                    "stage": current_stage,
                    "status": "unparsed",
                    "raw": line,
                }
            )
            continue
        if from_stage:
            source_stage = stage_aliases.get(from_stage)
            for source in sources:
                copies.append(
                    {
                        "dockerfile": path,
                        "line": lineno,
                        "operation": op,
                        "stage": current_stage,
                        "source_kind": "stage",
                        "source_stage": source_stage,
                        "source_stage_name": from_stage,
                        "source": source,
                        "destination": destination,
                        "precision": "dockerfile",
                    }
                )
            continue
        for context in context_values:
            for source in sources:
                copies.append(
                    {
                        "dockerfile": path,
                        "line": lineno,
                        "operation": op,
                        "stage": current_stage,
                        "source_kind": "repository-selector",
                        "context": context,
                        "context_precision": context_precision,
                        "source": source,
                        "destination": destination,
                        "resolved": _resolve_selector(context, source, tracked),
                        "precision": "dockerfile+compose" if contexts else "dockerfile-default-context",
                    }
                )

    if stages:
        stages[-1]["final"] = True
    return {
        "dockerfile": path,
        "contexts": context_values,
        "context_precision": context_precision,
        "stages": stages,
        "copies": copies,
    }


def build(snapshot: dict[str, Any]) -> dict[str, Any]:
    tracked = {str(row["path"]) for row in snapshot.get("files", [])}
    compose = compose_build_contexts(snapshot)
    dockerfiles = sorted(
        path
        for path in tracked
        if Path(path).name.lower() == "dockerfile" or Path(path).name.lower().startswith("dockerfile.")
    )
    records: list[dict[str, Any]] = []
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for path in dockerfiles:
        text = _read_text(path)
        if text is None:
            continue
        record = parse_dockerfile(path, text, compose.get(path, []), tracked)
        records.append(record)
        for stage in record["stages"]:
            nodes[stage["id"]] = {**stage, "type": "artifact"}
            edges.append(
                {
                    "from": f"file:{path}",
                    "to": stage["id"],
                    "type": "declares-artifact",
                    "precision": "dockerfile",
                }
            )
        for item in record["copies"]:
            if item.get("source_kind") == "stage":
                source_stage = item.get("source_stage")
                if source_stage:
                    edges.append(
                        {
                            "from": source_stage,
                            "to": item["stage"],
                            "type": "artifact-input",
                            "precision": "dockerfile-stage-copy",
                            "source": item["source"],
                            "destination": item["destination"],
                        }
                    )
                else:
                    unresolved.append(item)
                continue
            resolved = item.get("resolved") or {}
            kind = resolved.get("kind")
            selector = str(resolved.get("selector", item.get("source", "")))
            if kind == "file":
                edges.append(
                    {
                        "from": f"file:{selector}",
                        "to": item["stage"],
                        "type": "artifact-input",
                        "precision": item.get("precision", "dockerfile"),
                        "destination": item["destination"],
                    }
                )
            elif kind == "directory":
                selector_id = f"artifact-input-selector:{path}:{item['line']}:{selector}"
                nodes[selector_id] = {
                    "id": selector_id,
                    "type": "artifact-input-selector",
                    "selector": selector,
                    "matched_count": resolved["matched_count"],
                    "samples": resolved["samples"],
                    "context": item.get("context"),
                }
                edges.append(
                    {
                        "from": selector_id,
                        "to": item["stage"],
                        "type": "artifact-input",
                        "precision": item.get("precision", "dockerfile"),
                        "destination": item["destination"],
                    }
                )
            else:
                unresolved.append(item)

    # Compose services point to an explicit target when declared, otherwise the
    # final Dockerfile stage. This links deployment/service intent to lineage.
    by_dockerfile = {record["dockerfile"]: record for record in records}
    services: list[dict[str, Any]] = []
    for dockerfile, build_refs in compose.items():
        record = by_dockerfile.get(dockerfile)
        if not record or not record["stages"]:
            continue
        stage_by_name = {stage["stage"]: stage for stage in record["stages"]}
        final = record["stages"][-1]
        for build_ref in build_refs:
            target_name = str(build_ref.get("target") or "")
            stage = stage_by_name.get(target_name, final)
            service = str(build_ref.get("service"))
            service_id = f"artifact:compose-service:{service}"
            nodes[service_id] = {"id": service_id, "type": "artifact", "kind": "compose-service", "service": service}
            edges.append(
                {
                    "from": stage["id"],
                    "to": service_id,
                    "type": "packages-artifact",
                    "precision": "compose",
                    "target": target_name or stage["stage"],
                }
            )
            services.append(
                {
                    "service": service,
                    "dockerfile": dockerfile,
                    "context": build_ref.get("context"),
                    "target": target_name or stage["stage"],
                    "artifact": service_id,
                }
            )

    edge_map = {json.dumps(edge, sort_keys=True, separators=(",", ":")): edge for edge in edges}
    edges = sorted(
        edge_map.values(),
        key=lambda edge: (str(edge.get("from")), str(edge.get("to")), str(edge.get("type")), json.dumps(edge, sort_keys=True)),
    )
    artifact_nodes = [node for node in nodes.values() if node.get("type") == "artifact"]
    return {
        "schema": 1,
        "dockerfiles": records,
        "compose_services": sorted(services, key=lambda item: item["service"]),
        "nodes": [nodes[key] for key in sorted(nodes)],
        "edges": edges,
        "artifact_node_count": len(artifact_nodes),
        "selector_node_count": sum(1 for node in nodes.values() if node.get("type") == "artifact-input-selector"),
        "lineage_edge_count": len(edges),
        "unresolved": unresolved,
        "unresolved_count": len(unresolved),
        "semantics": (
            "Lineage is explicit Dockerfile/Compose build evidence. Directory selectors are bounded nodes, dynamic/glob/missing "
            "sources stay unresolved, and arbitrary shell command outputs are never inferred."
        ),
    }


def affected_artifacts(impact: dict[str, Any], lineage: dict[str, Any]) -> list[dict[str, Any]]:
    """Return artifacts reachable forward from affected files/selectors/stages."""
    starts = {f"file:{path}" for path in impact.get("affected_files", [])}
    # A changed file can be covered by a directory selector without a direct edge.
    for node in lineage.get("nodes", []):
        if node.get("type") != "artifact-input-selector":
            continue
        selector = str(node.get("selector", "")).rstrip("/") + "/"
        if any(path.startswith(selector) for path in impact.get("affected_files", [])):
            starts.add(str(node["id"]))

    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    allowed = {"artifact-input", "packages-artifact"}
    for edge in lineage.get("edges", []):
        if edge.get("type") in allowed:
            adjacency[str(edge["from"])].append(edge)
    queue = deque((node, 0) for node in sorted(starts))
    seen = set(starts)
    found: dict[str, dict[str, Any]] = {}
    nodes = {str(node["id"]): node for node in lineage.get("nodes", [])}
    while queue:
        current, depth = queue.popleft()
        for edge in adjacency.get(current, []):
            nxt = str(edge["to"])
            if nxt in seen:
                continue
            seen.add(nxt)
            queue.append((nxt, depth + 1))
            node = nodes.get(nxt)
            if node and node.get("type") == "artifact":
                found[nxt] = {"artifact": nxt, "depth": depth + 1, "kind": node.get("kind", "container-stage"), "metadata": node}
    return [found[key] for key in sorted(found, key=lambda key: (found[key]["depth"], key))]


def check_contracts() -> None:
    path = base.CONFIG_DIR / "artifact-lineage-contract.json"
    if not path.is_file():
        raise RuntimeError("missing artifact-lineage-contract.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("shell_output_policy") != "never infer arbitrary command outputs":
        raise RuntimeError("artifact lineage shell-output policy drifted")
    if payload.get("directory_selector_policy") != "bounded selector nodes":
        raise RuntimeError("artifact lineage directory selector policy drifted")
    print("repo-intel-artifacts: contract valid")


if __name__ == "__main__":
    print("repo_intel_artifacts is a library layer; use scripts/repo_intel_frontier.py", file=sys.stderr)
    raise SystemExit(2)
