"""
core/autonomous_orchestrator.py — AUTONOMOUS ORCHESTRATOR (Segment 3).

Replaces the static stage-ladder with a persistent, versioned BuildPlan graph.
A directive (natural-language OR explicit JSON/YAML-ish steps) is materialised
into a DAG of PlanNodes; the orchestrator executes them in dependency order,
each node driving a real forge / gate / churn invocation. Any node can be
re-planned, which cascades a reset to its downstream dependents.

PlanNode.status ∈ {planned, running, done, manual_review, skipped, error}

Doctrine: execution runs in a worker thread (kick + poll) so the ingress proxy
is never blocked. Deterministic forges by default; LLM only when a model is set.
"""
from __future__ import annotations

from collections import deque
import re
import threading
import time
import uuid

# ── node kinds the orchestrator can execute ──────────────────────────────────
NODE_KINDS = ("forge", "gate", "churn", "review")

# verbs that select a node kind from a natural-language clause
_KIND_VERBS = {
    "gate": ("gate", "pipeline", "refine", "run gates", "14-gate", "qc", "quality control"),
    "churn": ("churn", "alternatives", "variety", "improve", "polish weak"),
    "review": ("review", "manual", "approve", "sign off", "sign-off"),
}


def _gen_index():
    """Map keyword → generator key for NL clause matching (built from labels/types)."""
    from core import text_gamefile as tg
    idx = {}
    for g in tg.GENERATORS:
        for token in (g["key"].split("_") + g["label"].lower().split() + [g["type"]]):
            t = re.sub(r"[^a-z0-9]", "", token.lower())
            if len(t) >= 3:
                idx.setdefault(t, g["key"])
    return idx


_STOPWORDS = {"forge", "build", "make", "create", "run", "then", "the", "and",
              "for", "with", "into", "from", "add", "new", "this", "that",
              "gamefile", "file", "system", "pass", "stage"}


def _match_generator(clause: str, idx: dict) -> str | None:
    words = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in clause.split()]
    for w in words:
        if w in _STOPWORDS:
            continue
        if w in idx:
            return idx[w]
    # fuzzy: any generator type/label present (longest match wins)
    cl = clause.lower()
    from core import text_gamefile as tg
    best = None
    for g in tg.GENERATORS:
        if (g["type"] in cl or g["label"].lower() in cl):
            if not best or len(g["type"]) > len(best[1]):
                best = (g["key"], g["type"])
    return best[0] if best else None


def _kind_for(clause: str) -> str:
    cl = clause.lower()
    for kind, verbs in _KIND_VERBS.items():
        if any(v in cl for v in verbs):
            return kind
    return "forge"


def plan_from_directive(build_id: str, directive: str,
                        steps: list[dict] | None = None) -> dict:
    """Materialise a directive into a BuildPlan DAG.

    `steps` (explicit JSON/YAML-parsed list) wins; otherwise the natural-language
    `directive` is split into clauses and each is mapped to a node. Nodes are
    chained linearly by default (each depends on the previous) so later gate/churn
    steps consume earlier forge outputs — the user can edit depends_on later.
    """
    idx = _gen_index()
    nodes: list[dict] = []
    raw_steps: list[dict] = []
    if steps:
        raw_steps = steps
    else:
        clauses = [c.strip() for c in re.split(r"[\n;]|(?:\bthen\b)|(?:->)|(?:→)", directive or "") if c and c.strip()]
        for c in clauses:
            kind = _kind_for(c)
            target = _match_generator(c, idx) if kind in ("forge", "churn") else None
            raw_steps.append({"kind": kind, "target": target, "text": c})

    prev_id = None
    for i, st in enumerate(raw_steps):
        kind = st.get("kind", "forge")
        if kind not in NODE_KINDS:
            kind = "forge"
        nid = f"n{i + 1}"
        node = {
            "id": nid, "kind": kind,
            "target": st.get("target"),
            "text": st.get("text") or st.get("prompt") or directive[:200],
            "tier": st.get("tier"),
            "model": st.get("model"),
            "depends_on": st.get("depends_on") or ([prev_id] if prev_id else []),
            "status": "planned", "result": None, "produced_gid": None,
        }
        nodes.append(node)
        prev_id = nid

    plan = {
        "plan_id": uuid.uuid4().hex[:12], "build_id": build_id,
        "directive": (directive or "")[:1000], "version": 1,
        "nodes": nodes, "node_count": len(nodes),
        "status": "planned", "created": time.time(),
    }
    _save_plan(plan)
    return plan


# ── execution ────────────────────────────────────────────────────────────────
def _ready(node: dict, by_id: dict) -> bool:
    for dep in node.get("depends_on", []):
        d = by_id.get(dep)
        if not d or d["status"] not in ("done", "skipped"):
            return False
    return True


def _dependency_index(nodes: list[dict]) -> tuple[dict[str, dict], dict[str, list[str]]]:
    """Build direct lookup plus reverse dependency edges in linear time."""
    by_id = {node["id"]: node for node in nodes}
    dependents: dict[str, list[str]] = {node_id: [] for node_id in by_id}
    for node in nodes:
        for dep_id in node.get("depends_on", []):
            if dep_id in dependents:
                dependents[dep_id].append(node["id"])
    return by_id, dependents


def _exec_node(build_id: str, node: dict, by_id: dict) -> dict:
    """Run a single node. Returns the node's result dict."""
    from core import text_gamefile as tg
    kind = node["kind"]
    up_gid = None
    for dep in node.get("depends_on", []):
        d = by_id.get(dep) or {}
        if d.get("produced_gid"):
            up_gid = d["produced_gid"]
    try:
        if kind == "forge":
            key = node.get("target")
            if not key or not tg.get_generator(key):
                node["status"] = "manual_review"
                return {"error": "no_generator_matched", "hint": node.get("text")}
            gf = tg.generate(key, build_id, node.get("text") or key,
                             enrich=bool(node.get("model")), tier=node.get("tier"), store=True)
            node["produced_gid"] = gf.get("id")
            node["status"] = "done"
            return {"gid": gf.get("id"), "label": gf.get("label"), "type": gf.get("type")}
        if kind == "gate":
            gid = node.get("target") or up_gid
            if not gid:
                node["status"] = "manual_review"
                return {"error": "no_target_gamefile"}
            from core import gamefile_pipeline as gp
            r = gp.run_pipeline(build_id, gid, persist=True)
            node["produced_gid"] = gid
            node["status"] = "done"
            return {"gid": gid, "overall_score": r.get("overall_score"),
                    "aaa_passed": r.get("aaa_passed"), "pages": r.get("pages")}
        if kind == "churn":
            gid = node.get("target") or up_gid
            from core import churn_2_service as ch
            if gid:
                r = ch.run_churn(build_id, gid, model=node.get("model"))
                node["produced_gid"] = gid
                node["status"] = "done"
                return {"gid": gid, "deficit": r.get("deficit"),
                        "alternatives": r.get("alternatives_count"),
                        "recommended": r.get("recommended_variant")}
            r = ch.run_churn_build(build_id, model=node.get("model"))
            node["status"] = "done"
            return {"churned": r.get("churned"), "health": r.get("aggregate_health")}
        if kind == "review":
            node["status"] = "manual_review"
            return {"awaiting": "human sign-off", "note": node.get("text")}
    except Exception:
        node["status"] = "error"
        return {"error": "node_failed"}
    node["status"] = "manual_review"
    return {"error": "unknown_kind"}


def execute_plan(plan_id: str, on_progress=None) -> dict:
    plan = get_plan(plan_id)
    if not plan:
        return {"error": "plan_not_found"}
    nodes = plan["nodes"]
    by_id, dependents = _dependency_index(nodes)
    plan["status"] = "running"

    # Prior errors remain retryable, but each node gets at most one attempt in a
    # single execute_plan call. This prevents persistent failures from spinning
    # repeatedly inside one worker invocation.
    attemptable = {
        node["id"] for node in nodes
        if node["status"] in ("planned", "error")
    }
    pending_dependencies: dict[str, int] = {}
    for node in nodes:
        pending_dependencies[node["id"]] = sum(
            1
            for dep_id in node.get("depends_on", [])
            if not (by_id.get(dep_id) and by_id[dep_id]["status"] in ("done", "skipped"))
        )

    ready = deque(
        node["id"] for node in nodes
        if node["id"] in attemptable and pending_dependencies[node["id"]] == 0
    )
    attempted: set[str] = set()

    while ready:
        node_id = ready.popleft()
        if node_id in attempted or node_id not in attemptable:
            continue
        attempted.add(node_id)
        node = by_id[node_id]
        node["status"] = "running"
        if on_progress:
            on_progress(node, plan)
        node["result"] = _exec_node(plan["build_id"], node, by_id)

        if node["status"] not in ("done", "skipped"):
            continue
        for child_id in dependents.get(node_id, ()):
            if child_id not in attemptable or child_id in attempted:
                continue
            pending_dependencies[child_id] -= 1
            if pending_dependencies[child_id] == 0:
                ready.append(child_id)

    done = sum(1 for n in nodes if n["status"] == "done")
    review = sum(1 for n in nodes if n["status"] == "manual_review")
    err = sum(1 for n in nodes if n["status"] == "error")
    plan["status"] = ("done" if done == len(nodes)
                      else "needs_review" if review else "partial")
    _save_plan(plan)
    try:
        from core import provenance_ledger as pl
        pl.append(plan["build_id"], "orchestrator_execute",
                  {"plan_id": plan_id, "done": done, "review": review, "error": err})
    except Exception:
        pass
    return {"plan_id": plan_id, "status": plan["status"], "done": done,
            "manual_review": review, "error": err, "nodes": nodes}


def replan_from(plan_id: str, node_id: str) -> dict:
    """Reset a node + everything downstream of it to 'planned' (re-plan)."""
    plan = get_plan(plan_id)
    if not plan:
        return {"error": "plan_not_found"}
    by_id, dependents = _dependency_index(plan["nodes"])
    if node_id not in by_id:
        return {"error": "node_not_found"}

    to_reset = {node_id}
    queue = deque([node_id])
    while queue:
        current = queue.popleft()
        for child_id in dependents.get(current, ()):
            if child_id in to_reset:
                continue
            to_reset.add(child_id)
            queue.append(child_id)

    for n in plan["nodes"]:
        if n["id"] in to_reset:
            n["status"] = "planned"
            n["result"] = None
            n["produced_gid"] = None
    plan["version"] += 1
    plan["status"] = "planned"
    _save_plan(plan)
    return {"plan_id": plan_id, "replanned": sorted(to_reset),
            "version": plan["version"], "nodes": plan["nodes"]}


# ── persistence ──────────────────────────────────────────────────────────────
def _save_plan(plan: dict) -> None:
    try:
        from core.databases import get_sync_db
        get_sync_db()["galaxy_build_plans"].replace_one(
            {"_id": plan["plan_id"]}, {"_id": plan["plan_id"], **plan}, upsert=True)
    except Exception:
        pass


def get_plan(plan_id: str) -> dict | None:
    try:
        from core.databases import get_sync_db
        doc = get_sync_db()["galaxy_build_plans"].find_one({"_id": plan_id}, {"_id": 0})
        return doc
    except Exception:
        return None


def list_plans(build_id: str, limit: int = 20) -> dict:
    rows = []
    try:
        from core.databases import get_sync_db
        rows = list(get_sync_db()["galaxy_build_plans"]
                    .find({"build_id": build_id}, {"_id": 0, "nodes": 0})
                    .sort("created", -1).limit(limit))
    except Exception:
        pass
    return {"build_id": build_id, "count": len(rows), "plans": rows}


# ── async jobs ───────────────────────────────────────────────────────────────
_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()


def _put(jid: str, patch: dict):
    with _LOCK:
        _JOBS.setdefault(jid, {}).update(patch)
        if len(_JOBS) > 64:
            oldest = min(_JOBS, key=lambda key: _JOBS[key].get("started", 0))
            _JOBS.pop(oldest, None)


def get_job(jid: str) -> dict:
    with _LOCK:
        return dict(_JOBS.get(jid) or {"status": "unknown", "job_id": jid})


def start_execute_job(plan_id: str) -> str:
    jid = uuid.uuid4().hex[:12]
    _put(jid, {"job_id": jid, "status": "running", "plan_id": plan_id,
               "started": time.time(), "current": None, "result": None})

    def _worker():
        try:
            def _prog(node, plan):
                _put(jid, {"current": f"{node['kind']}:{node.get('target') or node['id']}"})
            res = execute_plan(plan_id, on_progress=_prog)
            _put(jid, {"status": "error" if res.get("error") else "done", "result": res})
        except Exception:
            _put(jid, {"status": "error", "error": "execute_failed"})

    threading.Thread(target=_worker, daemon=True, name=f"orch-{jid}").start()
    return jid
