"""Non-executing, bounded source graph for orphan-recovery campaigns.

The graph deliberately over-approximates possible static reachability.
Conditional imports and literal dynamic imports are not execution proof.
Unresolved and nonliteral dynamic edges remain explicit blind spots.
No candidate is automatically imported, activated, removed or promoted.
"""
from __future__ import annotations

import ast
from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat

from skeleton.app.orphan_cli_audit import AuditError, ScanBudget, _ReadBudget, _metadata


class GraphError(ValueError):
    pass


@dataclass(frozen=True)
class GraphBudget:
    entries: int = 250_000
    modules: int = 65_536
    file_bytes: int = 2 * 1024 * 1024
    total_bytes: int = 256 * 1024 * 1024
    edges: int = 1_000_000
    reported_components: int = 256

    def __post_init__(self):
        for value, maximum in (
            (self.entries, 1_000_000), (self.modules, 200_000),
            (self.file_bytes, 16 * 1024 * 1024),
            (self.total_bytes, 512 * 1024 * 1024),
            (self.edges, 4_000_000), (self.reported_components, 10_000),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise GraphError("invalid graph budget")


@dataclass(frozen=True)
class SourceNode:
    module: str
    path: str
    sha256: str
    size: int
    package: bool
    imports: tuple[str, ...]
    dynamic_unknown: int


def _digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True,
                     separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _module(path, root):
    parts = list(path.relative_to(root).with_suffix("").parts)
    package = parts[-1] == "__init__"
    if package:
        parts.pop()
    if not parts or not all(part.isidentifier() for part in parts):
        return "", package
    return ".".join(parts), package


def _absolute_from(module, package, level, target):
    if not level:
        return target or ""
    base = module.split(".") if package else module.split(".")[:-1]
    if level > len(base):
        return ""
    if level > 1:
        base = base[:-(level - 1)]
    if target:
        base.extend(target.split("."))
    return ".".join(base)


def _references(tree, module, package):
    names = set()
    unknown = 0
    importlib_aliases = {"importlib"}
    dynamic_aliases = {"__import__"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                names.add(item.name)
                if item.name == "importlib":
                    importlib_aliases.add(item.asname or "importlib")
        elif isinstance(node, ast.ImportFrom):
            base = _absolute_from(module, package, node.level, node.module)
            if base:
                names.add(base)
                for item in node.names:
                    if item.name != "*":
                        names.add(base + "." + item.name)
            if node.level == 0 and node.module == "importlib":
                for item in node.names:
                    if item.name == "import_module":
                        dynamic_aliases.add(item.asname or item.name)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name):
            dynamic = function.id in dynamic_aliases
        else:
            dynamic = (isinstance(function, ast.Attribute)
                       and function.attr == "import_module"
                       and isinstance(function.value, ast.Name)
                       and function.value.id in importlib_aliases)
        if not dynamic:
            continue
        arg = node.args[0] if node.args else None
        if isinstance(arg, ast.Constant) and type(arg.value) is str and arg.value:
            target = arg.value
            if not target.startswith("."):
                names.add(target)
                continue
            # A relative literal needs a separately resolved package parameter.
            owner = node.args[1] if len(node.args) > 1 else next(
                (kw.value for kw in node.keywords if kw.arg == "package"), None)
            if isinstance(owner, ast.Constant) and type(owner.value) is str:
                count = len(target) - len(target.lstrip("."))
                absolute = _absolute_from(owner.value, True, count, target[count:])
                if absolute:
                    names.add(absolute)
                    continue
        unknown += 1
    return tuple(sorted(name for name in names
                        if name == "skeleton" or name.startswith("skeleton."))), unknown


def _inventory(root, budget):
    reader = _ReadBudget(ScanBudget(
        max_entries=budget.entries,
        max_candidates=1,
        max_file_bytes=budget.file_bytes,
        max_total_bytes=budget.total_bytes,
    ))
    package = root / "skeleton"
    if not stat.S_ISDIR(package.lstat().st_mode):
        raise GraphError("source package is not a real directory")
    modern, legacy, _ = _metadata(root, reader)
    pending = [package]
    nodes = {}
    issues = []
    observed = 0
    omitted_links = 0
    limit = None
    collisions = set()
    while pending and limit is None:
        directory = pending.pop()
        try:
            if not stat.S_ISDIR(directory.lstat().st_mode):
                raise GraphError("directory identity changed")
            children = []
            with os.scandir(directory) as iterator:
                for child in iterator:
                    if observed >= budget.entries:
                        limit = "entries"
                        break
                    observed += 1
                    children.append(child)
            if limit:
                break
            for child in sorted(children, key=lambda x: x.name):
                path = Path(child.path)
                if child.is_symlink():
                    omitted_links += 1
                    continue
                if child.is_dir(follow_symlinks=False):
                    if child.name not in {"testing", "tests", "__pycache__"} and not child.name.startswith("."):
                        pending.append(path)
                    continue
                if (not child.is_file(follow_symlinks=False)
                        or not child.name.endswith(".py")
                        or child.name.startswith("test_") or child.name.endswith("_test.py")):
                    continue
                if len(nodes) >= budget.modules:
                    limit = "modules"
                    break
                relative = path.relative_to(root).as_posix()
                module, package_node = _module(path, root)
                if not module:
                    issues.append({"path": relative, "reason": "invalid_module"})
                    continue
                if module in nodes or module in collisions:
                    issues.append({"path": relative, "reason": "ambiguous_module_identity"})
                    nodes.pop(module, None)
                    collisions.add(module)
                    continue
                try:
                    raw = reader.read(path)
                    syntax = ast.parse(raw, filename=relative)
                    imports, unknown = _references(syntax, module, package_node)
                except (AuditError, OSError, SyntaxError, UnicodeError, RecursionError) as exc:
                    issues.append({"path": relative, "reason": type(exc).__name__})
                    continue
                nodes[module] = SourceNode(module, relative,
                    hashlib.sha256(raw).hexdigest(), len(raw), package_node, imports, unknown)
        except (OSError, GraphError) as exc:
            issues.append({"path": directory.relative_to(root).as_posix(),
                           "reason": type(exc).__name__})
    seeds = {"skeleton", "skeleton.__main__"}
    seeds.update(target.split(":", 1)[0] for target in modern.values())
    seeds.update(target.split(":", 1)[0] for target in legacy.values())
    drift = sorted(k for k in set(modern) | set(legacy) if modern.get(k) != legacy.get(k))
    return nodes, seeds, {
        "entries_observed": observed, "source_bytes_read": reader.consumed,
        "skipped_symlinks": omitted_links, "limit_reason": limit,
        "issues": sorted(issues, key=lambda x: (x["path"], x["reason"])),
        "metadata_drift": drift,
    }


def _resolve(nodes, budget):
    graph = {}
    all_count = 0
    unresolved = set()
    for module, node in sorted(nodes.items()):
        targets = set()
        # Importing any child executes package initializers, when present.
        references = (*node.imports, module)
        for reference in references:
            candidate = reference
            found = False
            while candidate:
                if candidate in nodes:
                    found = True
                    if candidate != module:
                        targets.add(candidate)
                candidate = candidate.rpartition(".")[0]
            if not found and reference != module:
                unresolved.add(reference)
        all_count += len(targets)
        if all_count > budget.edges:
            raise GraphError("graph edge ceiling")
        graph[module] = tuple(sorted(targets))
    return graph, all_count, sorted(unresolved)


def _reachable(graph, roots):
    found = set()
    queue = deque(sorted(set(roots) & graph.keys()))
    while queue:
        source = queue.popleft()
        if source in found:
            continue
        found.add(source)
        queue.extend(target for target in graph[source] if target not in found)
    return found


def _components(graph, subset):
    """Iterative Kosaraju; dependency cycles remain indivisible work units."""
    order = []
    seen = set()
    reverse = {node: [] for node in subset}
    for source in subset:
        for target in graph[source]:
            if target in subset:
                reverse[target].append(source)
    for root in sorted(subset):
        if root in seen:
            continue
        seen.add(root)
        stack = [(root, iter(graph[root]))]
        while stack:
            node, children = stack[-1]
            target = next(children, None)
            if target is None:
                order.append(node)
                stack.pop()
            elif target in subset and target not in seen:
                seen.add(target)
                stack.append((target, iter(graph[target])))
    seen.clear()
    groups = []
    for root in reversed(order):
        if root in seen:
            continue
        connected = []
        stack = [root]
        seen.add(root)
        while stack:
            node = stack.pop()
            connected.append(node)
            for target in reverse[node]:
                if target not in seen:
                    seen.add(target)
                    stack.append(target)
        groups.append(tuple(sorted(connected)))
    return sorted(groups)


def _plan(graph, nodes, unreachable):
    groups = _components(graph, unreachable)
    index = {module: i for i, group in enumerate(groups) for module in group}
    outgoing = [set() for _ in groups]
    dependents = [set() for _ in groups]
    for module in unreachable:
        src = index[module]
        for target in graph[module]:
            if target in index and index[target] != src:
                dst = index[target]
                outgoing[src].add(dst)
                dependents[dst].add(src)
    remaining = [len(deps) for deps in outgoing]
    wave = [0] * len(groups)
    ready = deque(i for i, count in enumerate(remaining) if count == 0)
    while ready:
        i = ready.popleft()
        for parent in sorted(dependents[i]):
            wave[parent] = max(wave[parent], wave[i] + 1)
            remaining[parent] -= 1
            if not remaining[parent]:
                ready.append(parent)
    if any(remaining):
        raise GraphError("component dependency invariant")
    identities = [_digest([(m, nodes[m].sha256) for m in group]) for group in groups]
    result = []
    for i, group in enumerate(groups):
        result.append({
            "component_id": identities[i],
            "dependency_wave": wave[i],
            "module_count": len(group),
            "modules": list(group),
            "source_paths": [nodes[m].path for m in group],
            "depends_on": sorted(identities[j] for j in outgoing[i]),
            "dependent_component_count": len(dependents[i]),
            "source_bytes": sum(nodes[m].size for m in group),
            "dynamic_unknown_calls": sum(nodes[m].dynamic_unknown for m in group),
            "automatic_activation_authorized": False,
        })
    return sorted(result, key=lambda x: (
        x["dependency_wave"], -x["dependent_component_count"], x["modules"],
    ))


def analyze(root: Path, *, extra_roots=(), budget: GraphBudget = GraphBudget()):
    """Return a static, dependency-ordered candidate graph and evidence digests."""
    if not isinstance(budget, GraphBudget) or type(extra_roots) not in (list, tuple):
        raise GraphError("invalid analysis inputs")
    if len(extra_roots) > 4096 or not all(type(x) is str and
            all(p.isidentifier() for p in x.split(".")) and
            (x == "skeleton" or x.startswith("skeleton.")) for x in extra_roots):
        raise GraphError("invalid explicit root set")
    root = Path(root).resolve(strict=True)
    nodes, seeds, metadata = _inventory(root, budget)
    seeds.update(extra_roots)
    graph, edge_count, unresolved = _resolve(nodes, budget)
    missing_roots = sorted(seeds - nodes.keys())
    reached = _reachable(graph, seeds)
    unreachable = set(nodes) - reached
    plan = _plan(graph, nodes, unreachable)
    by_digest = defaultdict(list)
    for module, node in sorted(nodes.items()):
        by_digest[node.sha256].append(module)
    duplicates = [(key, modules) for key, modules in sorted(by_digest.items())
                  if len(modules) > 1]
    complete = (not metadata["issues"] and not metadata["skipped_symlinks"]
                and not metadata["limit_reason"] and not missing_roots
                and not metadata["metadata_drift"])
    body = {
        "schema": "skeleton.orphan-source-graph.v1",
        "source_inventory_complete": complete,
        "static_only": True,
        "runtime_reachability_verified": False,
        "automatic_activation_authorized": False,
        "module_count": len(nodes),
        "static_edge_count": edge_count,
        "root_count": len(seeds),
        "missing_roots": missing_roots,
        "statically_referenced_modules": len(reached),
        "statically_unreferenced_candidates": len(unreachable),
        "component_count": len(plan),
        "dynamic_unknown_calls": sum(n.dynamic_unknown for n in nodes.values()),
        "unresolved_local_prefix_count": len(unresolved),
        "unresolved_local_prefix_sample": unresolved[:128],
        "source_inventory_digest": _digest([
            (module, node.path, node.sha256) for module, node in sorted(nodes.items())
        ]),
        "graph_digest": _digest(graph),
        "root_digest": _digest(sorted(seeds)),
        "candidate_plan_digest": _digest(plan),
        "duplicate_byte_group_count": len(duplicates),
        "duplicate_byte_groups_sample": [
            {"sha256": key, "modules": modules[:32]}
            for key, modules in duplicates[:64]
        ],
        "components": plan[:budget.reported_components],
        "component_output_truncated": len(plan) > budget.reported_components,
        "scan": metadata,
    }
    return {**body, "report_digest": _digest(body)}
