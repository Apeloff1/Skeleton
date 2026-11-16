"""Deterministic bounded graph compilation for physical Hyperdispatcher jobs.

A graph is an atomic inbox submission, not an atomic physical transaction.
Each node still obtains its own canonical owner lease, independently
verified receipt, and success/rejection. No graph can grant new operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from heapq import heapify, heappop, heappush
import json

from skeleton.automation.agents.swarm_dispatch_bindings import BindingError, parse_bindings
from skeleton.automation.agents.swarm_durable import DurableSwarmError, _wait_bytes, _wait_identifier

MAX_WORKFLOW_JOBS = 32
MAX_WORKFLOW_BYTES = 512 * 1024
MAX_WORKFLOW_PREDECESSORS = 32


class WorkflowError(ValueError):
    """Invalid graph or incompatible durable workflow identity."""


def _id(value: object) -> str:
    try:
        return _wait_identifier(value)
    except DurableSwarmError as exc:
        raise WorkflowError("invalid workflow identity") from exc


def _copy(value: object) -> object:
    try:
        raw = _wait_bytes(value)
        if len(raw) > MAX_WORKFLOW_BYTES:
            raise WorkflowError("workflow graph exceeds byte ceiling")
        return json.loads(raw)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise WorkflowError("invalid or oversized workflow JSON") from exc


@dataclass(frozen=True, slots=True)
class WorkflowCommand:
    request_id: str
    body_json: bytes

    @property
    def body(self) -> dict:
        return json.loads(self.body_json)

    @property
    def digest(self) -> str:
        return sha256(self.body_json).hexdigest()


@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    workflow_id: str
    tenant: str
    deadline_ms: int
    commands: tuple[WorkflowCommand, ...]

    @property
    def manifest(self) -> bytes:
        return _wait_bytes({
            "version": 1, "workflow_id": self.workflow_id, "tenant": self.tenant,
            "deadline_ms": self.deadline_ms,
            "commands": [{"request_id": item.request_id, "body": item.body}
                         for item in self.commands],
        })

    @property
    def digest(self) -> str:
        return sha256(self.manifest).hexdigest()


def compile_workflow(workflow_id: str, tenant: str, spec: dict, *,
                     operations: frozenset[str]) -> WorkflowPlan:
    workflow_id, tenant = _id(workflow_id), _id(tenant)
    if type(spec) is not dict or set(spec) != {"deadline_ms", "jobs"}:
        raise WorkflowError("workflow requires exact deadline and job inventory")
    spec = _copy(spec)
    deadline = spec["deadline_ms"]
    if type(deadline) is not int or not 1 <= deadline <= 10**15:
        raise WorkflowError("invalid workflow admission deadline")
    jobs = spec["jobs"]
    if type(jobs) is not list or not 1 <= len(jobs) <= MAX_WORKFLOW_JOBS:
        raise WorkflowError("invalid workflow job count")
    required = {"request_id", "task_id", "operation", "input"}
    optional = {"priority", "dependencies", "singleton", "timer_ms", "event", "bindings"}
    by_task, requests, descendants = {}, set(), {}
    for node in jobs:
        if type(node) is not dict or not required.issubset(node) or not set(node).issubset(required | optional):
            raise WorkflowError("invalid workflow node fields")
        task_id, request_id = _id(node["task_id"]), _id(node["request_id"])
        if task_id in by_task or request_id in requests:
            raise WorkflowError("duplicate workflow task or request identity")
        if type(node["operation"]) is not str or node["operation"] not in operations:
            raise WorkflowError("workflow operation outside provisioned policy")
        priority = node.get("priority", 100)
        if type(priority) is not int or not 0 <= priority <= 1000:
            raise WorkflowError("invalid workflow priority")
        if len(_wait_bytes(node["input"])) > 32768:
            raise WorkflowError("workflow input template exceeds bound")
        if "singleton" in node:
            _id(node["singleton"])
        if "timer_ms" in node and "event" in node:
            raise WorkflowError("one deferred gate permitted per job")
        if "timer_ms" in node and (
                type(node["timer_ms"]) is not int or not 0 <= node["timer_ms"] <= 10**15):
            raise WorkflowError("invalid workflow timer")
        if "event" in node:
            event = node["event"]
            if (type(event) is not dict or "selector" not in event
                    or not set(event).issubset({"selector", "not_before_ms", "expires_ms"})):
                raise WorkflowError("invalid workflow event gate")
            _id(event["selector"])
            for field in ("not_before_ms", "expires_ms"):
                if field in event and (
                        type(event[field]) is not int or not 0 <= event[field] <= 10**15):
                    raise WorkflowError("invalid workflow event timestamp")
            if event.get("expires_ms", 10**15) < event.get("not_before_ms", 0):
                raise WorkflowError("workflow event window inverted")
        deps = node.get("dependencies", [])
        if (type(deps) is not list or len(deps) > MAX_WORKFLOW_PREDECESSORS
                or any(type(dep) is not str for dep in deps)
                or len(set(deps)) != len(deps)):
            raise WorkflowError("invalid workflow dependency set")
        for parent in deps:
            _id(parent)
        by_task[task_id] = node
        requests.add(request_id)
        descendants[task_id] = []
    indegree, prerequisites = {}, {}
    for task_id, node in by_task.items():
        parents = set(node.get("dependencies", []))
        try:
            bindings = (() if "bindings" not in node else
                        parse_bindings(node["bindings"], node["input"], task_id=task_id))
        except BindingError as exc:
            raise WorkflowError("invalid workflow result binding") from exc
        for binding in bindings:
            parent = by_task.get(binding.source_task_id)
            if parent is None or parent["request_id"] != binding.source_request_id:
                raise WorkflowError("binding source must be an exact internal graph node")
            parents.add(binding.source_task_id)
        if task_id in parents or not parents.issubset(by_task) or len(parents) > MAX_WORKFLOW_PREDECESSORS:
            raise WorkflowError("unknown or self workflow dependency")
        indegree[task_id] = len(parents)
        for parent in parents:
            descendants[parent].append(task_id)
        # Binding edges already prove successful source execution. Preserve
        # only additional ordering edges as receipt-bound prerequisites.
        prerequisites[task_id] = sorted(parents - {b.source_task_id for b in bindings})
    ready = [task_id for task_id, count in indegree.items() if not count]
    heapify(ready)
    order = []
    while ready:
        current = heappop(ready)
        order.append(current)
        for dependent in sorted(descendants[current]):
            indegree[dependent] -= 1
            if not indegree[dependent]:
                heappush(ready, dependent)
    if len(order) != len(by_task):
        raise WorkflowError("cyclic workflow graph")
    commands = []
    for task_id in order:
        node = by_task[task_id]
        body = {key: value for key, value in node.items() if key not in {"request_id", "dependencies"}}
        body.update({"kind": "submit", "tenant": tenant})
        # Ordering nodes wait before admission, not on a resident dependency
        # that would prevent compacting a settled predecessor.
        if prerequisites[task_id]:
            body["prerequisites"] = [
                {"source_request_id": by_task[parent]["request_id"], "source_task_id": parent}
                for parent in prerequisites[task_id]
            ]
        if "bindings" in body or "prerequisites" in body:
            body["binding_deadline_ms"] = deadline
        body_json = _wait_bytes(body)
        if len(body_json) > 65536:
            raise WorkflowError("compiled workflow command exceeds byte ceiling")
        commands.append(WorkflowCommand(node["request_id"], body_json))
    plan = WorkflowPlan(workflow_id, tenant, deadline, tuple(commands))
    if len(plan.manifest) > MAX_WORKFLOW_BYTES:
        raise WorkflowError("compiled workflow manifest exceeds byte ceiling")
    return plan


def parse_prerequisites(value: object, *, task_id: str) -> tuple[tuple[str, str], ...]:
    if type(value) is not list or not 1 <= len(value) <= MAX_WORKFLOW_PREDECESSORS:
        raise BindingError("invalid prerequisite count")
    result = []
    for item in value:
        if type(item) is not dict or set(item) != {"source_request_id", "source_task_id"}:
            raise BindingError("invalid exact prerequisite")
        try:
            pair = (_wait_identifier(item["source_request_id"]), _wait_identifier(item["source_task_id"]))
        except DurableSwarmError as exc:
            raise BindingError("invalid prerequisite identity") from exc
        if pair[1] == task_id:
            raise BindingError("self prerequisite")
        result.append(pair)
    if len({item[0] for item in result}) != len(result) or len({item[1] for item in result}) != len(result):
        raise BindingError("duplicate prerequisite identity")
    return tuple(result)
