"""Jeeves deathmarch execution packets grounded in canonical application evidence.

This is the canonical Jeeves appwide read adapter, not a new execution plane.
Packets include real source excerpts, dependencies, owner-coordinated workwaves,
exact snapshot identities, and source changes' declared downstream blast radius.
They never start jobs, grant authorization, apply diffs, run programs or claim
completion without separately admitted execution and independent verification.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from typing import Any

from .jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideError, PRIVATE, _relative, digest,
)
from .jeeves_evidence_graph import JeevesEvidenceGraph
from .jeeves_milestone_planner import JeevesMilestonePlanner, _task_ref

SCHEMA = "skeleton.ai.jeeves_deathmarch_workpacks.v1"
MAX_TASKS = 24
MAX_TASK_RESULTS = 400
MAX_SOURCES = 40
MAX_SOURCE_BYTES = 24_000
MAX_TOTAL_BYTES = 96_000
MAX_CHANGED_PATHS = 32
MAX_AFFECTED = 300
MAX_WAVES = 4096

# The canonical registry contains different task IDs for the same source
# authorities. These are *references* into the existing graph, not a new
# capability authority or a hard-coded statement that a service is live.
def _graph_ref(task: dict[str, Any]) -> str | None:
    kind, key = task["kind"], task["id"]
    if kind == "runtime_service" and key.startswith("APP-SERVICE-"):
        return "service:" + key[len("APP-SERVICE-"):]
    if kind == "end_user_ai" and key.startswith("AI-CAP-"):
        return "cap:" + key[len("AI-CAP-"):]
    if kind == "enterprise_workstream" and key.startswith("WORK-"):
        return "work:" + key[len("WORK-"):]
    if kind == "enterprise_journey" and key.startswith("JOURNEY-"):
        return "journey:" + key[len("JOURNEY-"):]
    return None


def _integer(name: str, value: Any, lowest: int, highest: int) -> int:
    if type(value) is not int or not lowest <= value <= highest:
        raise JeevesAppwideError("invalid bounded " + name)
    return value


def _graph_edges(graph: dict[tuple[str, str, str], dict]
                 ) -> tuple[dict[str, list[tuple[str, str]]],
                            dict[str, list[tuple[str, str]]]]:
    outbound: dict[str, list[tuple[str, str]]] = defaultdict(list)
    inbound: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for src, relation, dst in sorted(graph):
        outbound[src].append((relation, dst))
        inbound[dst].append((relation, src))
    return outbound, inbound


def _limited_excerpt(text: str, budget: int) -> tuple[str, bool, int]:
    """Return UTF-8 line-aligned context and exact observed source size.

    A very long single source line is still bounded without cutting a code
    point. The complete file's digest is separate from this context excerpt.
    """
    encoded = text.encode("utf-8")
    if len(encoded) <= budget:
        return text, False, len(encoded)
    clipped = encoded[:budget].decode("utf-8", errors="ignore")
    line_end = clipped.rfind("\n")
    if line_end > max(128, budget // 3):
        clipped = clipped[:line_end + 1]
    return clipped, True, len(encoded)


class JeevesWorkpackDirector:
    """Deterministic operator-facing work decomposition over one source checkout."""

    def __init__(self, inventory: AppwideInventory):
        if not isinstance(inventory, AppwideInventory):
            raise JeevesAppwideError("canonical Jeeves inventory required")
        inventory._require_scanned()
        self.inventory = inventory

    def _authorities(self, *, expected_snapshot=None,
                     expected_plan_digest=None, expected_graph_digest=None):
        plan = JeevesMilestonePlanner(self.inventory)._plan(
            expected_snapshot=expected_snapshot)
        if (expected_plan_digest is not None and
                expected_plan_digest != plan["digest"]):
            raise JeevesAppwideError("stale milestone plan for workpack")
        nodes, edges, graph = JeevesEvidenceGraph(self.inventory)._build(
            expected_snapshot=expected_snapshot)
        if (expected_graph_digest is not None and
                expected_graph_digest != graph["digest"]):
            raise JeevesAppwideError("stale application evidence graph")
        if plan["inventory_snapshot"] != graph["inventory_snapshot"]:
            raise JeevesAppwideError("plan and graph use different source snapshots")
        return plan, nodes, edges, graph

    def waves(self, *, offset=0, limit=20, max_parallel=8,
              expected_snapshot=None, expected_plan_digest=None,
              expected_graph_digest=None):
        """Pack topological milestones into deterministic owner-isolated waves.

        Every prerequisite is assigned an earlier wave. No single wave mixes
        two changes under the same canonical owner. No work is dispatched.
        """
        _integer("wave offset", offset, 0, MAX_WAVES)
        _integer("wave limit", limit, 1, 80)
        _integer("parallel work limit", max_parallel, 1, MAX_TASKS)
        plan, _, _, graph = self._authorities(
            expected_snapshot=expected_snapshot,
            expected_plan_digest=expected_plan_digest,
            expected_graph_digest=expected_graph_digest)
        rows = {task["id"]: task for task in plan["tasks"]}
        remaining = set(rows)
        finished: set[str] = set()
        result: list[dict] = []
        while remaining:
            if len(result) >= MAX_WAVES:
                raise JeevesAppwideError("workwave limit exceeded")
            ready = [
                rows[task_id] for task_id in remaining
                if set(rows[task_id]["dependencies"]) <= finished
            ]
            if not ready:
                raise JeevesAppwideError("unresolvable milestone dependency state")
            ready.sort(key=lambda t: (t["priority_sort"], t["stage"], t["id"]))
            selected = []
            selected_owners = set()
            for task in ready:
                owner = task["owner"]
                if type(owner) is not str or not owner:
                    raise JeevesAppwideError("undeclared work ownership")
                if owner in selected_owners:
                    continue
                selected_owners.add(owner)
                selected.append(task)
                if len(selected) >= max_parallel:
                    break
            if not selected:
                raise JeevesAppwideError("cannot assign source-owned workwave")
            wave_no = len(result)
            result.append({
                "wave": wave_no,
                "task_ids": [t["id"] for t in selected],
                "owners": sorted(selected_owners),
                "max_parallel": max_parallel,
                "topological_stage_max": max(t["stage"] for t in selected),
                "priority_counts": dict(sorted(Counter(
                    t["priority"] for t in selected).items())),
                "independent_tasks_only": True,
                "executor_leases_acquired": False,
                "runtime_tasks_started": False,
            })
            for task in selected:
                remaining.remove(task["id"])
                finished.add(task["id"])
        page = result[offset:offset + limit]
        body = {
            "schema": SCHEMA + ".waves",
            "plan_digest": plan["digest"],
            "graph_digest": graph["digest"],
            "inventory_snapshot": plan["inventory_snapshot"],
            "max_parallel": max_parallel,
            "total_waves": len(result),
            "total_tasks": len(rows),
            "offset": offset, "limit": limit,
            "next_offset": offset + len(page) if offset + len(page) < len(result) else None,
            "waves": page,
            "cross_wave_dependencies_respected": True,
            "same_owner_not_scheduled_in_parallel": True,
            "all_waves_require_execution_authority": True,
            "completed_tasks": 0,
        }
        return {**body, "digest": digest(body)}

    def _source_paths(self, root_id, nodes, outgoing, *,
                      depth=3, max_sources=MAX_SOURCES):
        """Traverse only verified declared graph links, never arbitrary imports."""
        if root_id not in nodes:
            return []
        pending = [(root_id, 0)]
        seen = set()
        paths: dict[str, tuple[int, str]] = {}
        while pending:
            current, step = pending.pop(0)
            if current in seen or step > depth:
                continue
            seen.add(current)
            for relation, dest in outgoing.get(current, []):
                record = nodes[dest]
                if record["kind"] == "source_path":
                    path = dest[len("path:"):]
                    source = self.inventory._files.get(path)
                    if source is not None and source.readable and source.kind in ("source", "text"):
                        old = paths.get(path)
                        if old is None or step < old[0]:
                            paths[path] = (step, relation)
                elif relation in (
                    "owned_by_plane", "requires_plane", "covers_plane",
                    "requires_volume_evidence",
                ):
                    pending.append((dest, step + 1))
        return [
            {"path": path, "graph_hops": distance + 1,
             "declared_relation": relation}
            for path, (distance, relation) in
            sorted(paths.items(), key=lambda item: (item[1][0], item[0]))
        ][:max_sources]

    def workpack(self, *, task_ids, source_bytes=4096, total_bytes=32768,
                 max_sources=16, expected_snapshot=None,
                 expected_plan_digest=None, expected_graph_digest=None):
        """Read executable source *as context*, without executing any of it.

        A packet is meant for a finite Jeeves implementation turn. It includes
        actual bytes from the selected checked-out sources rather than synthetic
        code summaries, and refuses optimistic identity drift.
        """
        if (type(task_ids) is not list or
                not 1 <= len(task_ids) <= MAX_TASKS):
            raise JeevesAppwideError("one to 24 canonical milestone IDs required")
        ids = [_task_ref(key) for key in task_ids]
        if len(set(ids)) != len(ids):
            raise JeevesAppwideError("duplicate milestone IDs")
        _integer("source context bytes", source_bytes, 512, MAX_SOURCE_BYTES)
        _integer("total context bytes", total_bytes, 512, MAX_TOTAL_BYTES)
        _integer("context source count", max_sources, 1, MAX_SOURCES)
        plan, nodes, edges, graph = self._authorities(
            expected_snapshot=expected_snapshot,
            expected_plan_digest=expected_plan_digest,
            expected_graph_digest=expected_graph_digest)
        tasks = {row["id"]: row for row in plan["tasks"]}
        missing = sorted(set(ids) - tasks.keys())
        if missing:
            raise JeevesAppwideError("unknown milestone identity: " + missing[0])
        outgoing, _ = _graph_edges(edges)
        sources: dict[str, dict] = {}
        packets = []
        remaining_bytes = total_bytes
        for key in ids:
            task = tasks[key]
            canonical = _graph_ref(task)
            discovered = self._source_paths(
                canonical, nodes, outgoing, max_sources=max_sources
            ) if canonical else []
            available = []
            for source in discovered:
                path = source["path"]
                if path in sources:
                    available.append(path)
                    continue
                if len(sources) >= max_sources or remaining_bytes < 512:
                    continue
                try:
                    content = self.inventory._safe_file(path)
                except JeevesAppwideError:
                    # A recorded graph path may be too large or may have
                    # disappeared after its metadata inventory was captured.
                    # Treat loss of source as an explicit incomplete packet.
                    continue
                excerpt, truncated, full_bytes = _limited_excerpt(
                    content, min(source_bytes, remaining_bytes))
                consumed = len(excerpt.encode("utf-8"))
                sources[path] = {
                    **source, "sha256": sha256(content.encode("utf-8")).hexdigest(),
                    "full_source_bytes": full_bytes,
                    "excerpt_bytes": consumed,
                    "excerpt": excerpt,
                    "excerpt_truncated": truncated,
                    "code_was_not_executed": True,
                }
                remaining_bytes -= consumed
                available.append(path)
            packets.append({
                "id": key,
                "owner": task["owner"],
                "priority": task["priority"],
                "prerequisites": task["dependencies"],
                "topological_stage": task["stage"],
                "evidence_required": task["evidence_required"],
                "evidence_graph_node": canonical if canonical in nodes else None,
                "linked_source_paths": available,
                "source_context_found": bool(available),
                "unlinked_or_missing_context_requires_human_selection": not bool(available),
                "implementation_verified": False,
                "ready_to_modify_source": False,
            })
        body = {
            "schema": SCHEMA + ".packet",
            "inventory_snapshot": plan["inventory_snapshot"],
            "plan_digest": plan["digest"],
            "graph_digest": graph["digest"],
            "census_digest": plan["census_digest"],
            "task_ids": ids,
            "tasks": packets,
            "sources": [sources[path] for path in sorted(sources)],
            "source_count": len(sources),
            "context_bytes": total_bytes - remaining_bytes,
            "source_budget_bytes": total_bytes,
            "source_truncated_or_missing": any(
                row["excerpt_truncated"] for row in sources.values()
            ) or any(not t["source_context_found"] for t in packets),
            "operator_must_approve_source_changes": True,
            "code_executed": False,
            "source_mutated": False,
            "tests_executed": False,
            "automatic_completion_claims": 0,
        }
        return {**body, "digest": digest(body)}

    def change_frontier(self, *, paths, limit=80, expected_snapshot=None,
                        expected_plan_digest=None, expected_graph_digest=None):
        """Estimate declared impact of changed source files, not real runtime proof.

        This is deliberately conservative: no evidence graph match means
        *unmapped*, never "safe" or "no downstream impact".
        """
        if type(paths) is not list or not 1 <= len(paths) <= MAX_CHANGED_PATHS:
            raise JeevesAppwideError("one to 32 modified source paths required")
        _integer("affected node limit", limit, 1, MAX_AFFECTED)
        normalized = []
        for raw in paths:
            path = _relative(raw)
            if PRIVATE.search(path):
                raise JeevesAppwideError("private source cannot enter change frontier")
            if path not in self.inventory._files:
                raise JeevesAppwideError("unscanned changed path: " + path)
            if not self.inventory._files[path].readable:
                raise JeevesAppwideError("restricted changed source")
            normalized.append(path)
        if len(set(normalized)) != len(normalized):
            raise JeevesAppwideError("duplicate changed source paths")
        plan, nodes, edges, graph = self._authorities(
            expected_snapshot=expected_snapshot,
            expected_plan_digest=expected_plan_digest,
            expected_graph_digest=expected_graph_digest)
        _, incoming = _graph_edges(edges)
        affected: dict[str, set[str]] = defaultdict(set)
        unmapped = []
        source_meta = []
        for path in sorted(normalized):
            file = self.inventory._files[path]
            sha = None
            if file.kind in ("source", "text"):
                try:
                    content = self.inventory._safe_file(path)
                    sha = sha256(content.encode("utf-8")).hexdigest()
                except JeevesAppwideError:
                    # Size and source swaps are reported, not silently trusted.
                    pass
            source_meta.append({
                "path": path, "bytes_at_scan": file.bytes,
                "content_sha256": sha,
                "source_bytes_verified": sha is not None,
            })
            start = "path:" + path
            if start not in nodes:
                unmapped.append(path)
                continue
            frontier = [(start, 0)]
            visited = {start}
            while frontier:
                current, hops = frontier.pop(0)
                if hops >= 3:
                    continue
                for relation, parent in incoming.get(current, []):
                    if parent in visited:
                        continue
                    visited.add(parent)
                    kind = nodes[parent]["kind"]
                    if kind not in ("source_path", "required_app_file"):
                        affected[parent].add(path)
                    frontier.append((parent, hops + 1))
            if not any(path in owners for owners in affected.values()):
                unmapped.append(path)
        ordered = sorted(affected)
        body = {
            "schema": SCHEMA + ".change_frontier",
            "inventory_snapshot": plan["inventory_snapshot"],
            "plan_digest": plan["digest"],
            "graph_digest": graph["digest"],
            "changed_paths": source_meta,
            "affected_total": len(ordered),
            "affected": [{
                "node": node, "kind": nodes[node]["kind"],
                "title": nodes[node]["title"],
                "declared_source_paths": sorted(affected[node]),
                "live_runtime_impact_verified": False,
            } for node in ordered[:limit]],
            "result_truncated": len(ordered) > limit,
            "unmapped_paths": sorted(unmapped),
            "unmapped_means_unassessed_not_safe": True,
            "release_quality_not_inferred": True,
            "source_files_mutated": False,
        }
        return {**body, "digest": digest(body)}
