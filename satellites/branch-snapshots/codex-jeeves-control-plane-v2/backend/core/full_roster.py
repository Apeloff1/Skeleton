"""
╔════════════════════════════════════════════════════════════════════════╗
║  FULL ROSTER — every single agent in the Galaxy Studio constellation   ║
║  ────────────────────────────────────────────────────────────────────  ║
║  1,473,844 agents across 8 cohorts, each with integer ID + code.       ║
║  Materialised dicts are kept ONLY for the 482 swarm+collection agents; ║
║  the remaining 1,473,362 are virtual and addressed procedurally via    ║
║  deterministic (cohort, team, seat) arithmetic.                        ║
║                                                                        ║
║  This is the source of truth used by `core.agent_mesh` (the spider     ║
║  web) so every agent — every last one of 1.47 million — participates   ║
║  in the mesh with O(1) memory per query.                               ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import bisect
from typing import Optional

# ── Cohort manifest ────────────────────────────────────────────────────
# (id, label, size, code_prefix, team_size, teams_per_legion, desc)
COHORT_DEFS = [
    # NOTE: swarm is 482 (200 swarm domains + 282 collection agents).
    ("swarm",   "Swarm + Collection",    482,      "A", 10,  4,  "200 swarm domains + 282 collection-agents (materialised)"),
    ("hexa",    "Hexa-Layer Factory",    1_299_700,"H", 100, 50, "6 layers × genre matrix — Originals, Shadows, Ghosts, Angels, Seraphim, Cherubim"),
    ("hyper",   "Hyperscale Domains",    120_000,  "Y", 50,  20, "300 domains × 400 specialists"),
    ("jeeves",  "Jeeves Master Build",   28_662,   "J", 50,  48, "12-phase code generation legion"),
    ("mega",    "Mega Domains",          11_600,   "M", 50,  8,  "29 core domains × 400 specialists"),
    ("aaa",     "AAA Pipeline",          10_000,   "P", 50,  10, "200-step AAA pipeline × 50 agents/step"),
    ("quantum", "Quantum Factory",       2_800,    "Q", 50,  8,  "7 ultra-deep domains × 400 specialists"),
    ("deploy",  "Deploy Forge",          600,      "D", 50,  12, "12-platform deployment armada"),
]

# Build runtime cohort dicts with computed start offsets
COHORTS: list[dict] = []
_BY_ID: dict[str, dict] = {}
_BY_PREFIX: dict[str, dict] = {}

_cursor = 0
for _cid, _lbl, _sz, _pre, _ts, _tpl, _desc in COHORT_DEFS:
    _c = {
        "id": _cid,
        "label": _lbl,
        "size": _sz,
        "prefix": _pre,
        "team_size": _ts,
        "teams_per_legion": _tpl,
        "legion_size": _ts * _tpl,
        "start": _cursor,
        "end": _cursor + _sz,
        "desc": _desc,
    }
    COHORTS.append(_c)
    _BY_ID[_cid] = _c
    _BY_PREFIX[_pre] = _c
    _cursor += _sz

TOTAL_AGENTS: int = _cursor  # 1,473,844

# Sorted list of cohort starts for O(log N) binary search
_COHORT_STARTS = [c["start"] for c in COHORTS]


# ── Cohort lookup ──────────────────────────────────────────────────────
def cohort_of(agent_id: int) -> dict:
    """Return the cohort dict that owns the given integer agent id."""
    if agent_id < 0 or agent_id >= TOTAL_AGENTS:
        raise IndexError(f"agent_id {agent_id} out of range 0..{TOTAL_AGENTS-1}")
    # rightmost cohort whose start <= agent_id
    idx = bisect.bisect_right(_COHORT_STARTS, agent_id) - 1
    return COHORTS[idx]


def cohort_by_id(cid: str) -> Optional[dict]:
    return _BY_ID.get(cid)


# ── Code <-> integer id ────────────────────────────────────────────────
def agent_code(agent_id: int) -> str:
    """Deterministic string code for any integer id in [0, TOTAL_AGENTS)."""
    c = cohort_of(agent_id)
    offset = agent_id - c["start"]
    if c["id"] == "swarm":
        # Preserve legacy "A0001" format used by SWARM_DOMAINS + collection_agents.
        return f"A{offset + 1:04d}"
    # Width = number of digits in (size-1). Always ≥ 4 for nice alignment.
    width = max(4, len(str(c["size"] - 1)))
    return f"{c['prefix']}{offset:0{width}d}"


def id_of_code(code: str) -> int:
    """Inverse of agent_code(). Raises ValueError on bad code."""
    if not code or not isinstance(code, str):
        raise ValueError("code must be a non-empty string")
    pre = code[0]
    c = _BY_PREFIX.get(pre)
    if not c:
        raise ValueError(f"unknown cohort prefix '{pre}'")
    try:
        num_part = code[1:]
        num = int(num_part)
    except Exception:
        raise ValueError(f"cannot parse number from code '{code}'")
    if c["id"] == "swarm":
        offset = num - 1  # legacy A0001 → offset 0
    else:
        offset = num
    if offset < 0 or offset >= c["size"]:
        raise ValueError(f"code '{code}' out of range for cohort '{c['id']}' (size {c['size']})")
    return c["start"] + offset


def safe_id_of_code(code: str) -> Optional[int]:
    try:
        return id_of_code(code)
    except Exception:
        return None


# ── Team / Legion identity ─────────────────────────────────────────────
def locate(agent_id: int) -> dict:
    """Return {cohort, offset, team, team_seat, legion, team_in_legion} for any id."""
    c = cohort_of(agent_id)
    offset = agent_id - c["start"]
    ts = c["team_size"]
    tpl = c["teams_per_legion"]
    team = offset // ts
    seat = offset % ts
    legion = team // tpl
    team_in_legion = team % tpl
    return {
        "cohort": c,
        "offset": offset,
        "team": team,
        "team_seat": seat,
        "legion": legion,
        "team_in_legion": team_in_legion,
    }


def team_id_str(agent_id: int) -> str:
    loc = locate(agent_id)
    c = loc["cohort"]
    if c["id"] == "swarm":
        # Defer to swarm_agents.py canonical "T01".."T20" + "CT_*" formats.
        # Best-effort from the dict: callers should prefer the materialized dict.
        return f"{c['prefix']}T{loc['team']:02d}"
    return f"{c['prefix']}T{loc['team']:05d}"


def legion_id_str(agent_id: int) -> str:
    loc = locate(agent_id)
    c = loc["cohort"]
    if c["id"] == "swarm":
        return f"{c['prefix']}L{loc['legion']+1}"
    return f"{c['prefix']}L{loc['legion']:04d}"


# ── Cohort roster summary ──────────────────────────────────────────────
def cohort_summary() -> list[dict]:
    out = []
    for c in COHORTS:
        legions = (c["size"] + c["legion_size"] - 1) // c["legion_size"]
        teams = (c["size"] + c["team_size"] - 1) // c["team_size"]
        out.append({
            "id": c["id"],
            "label": c["label"],
            "size": c["size"],
            "prefix": c["prefix"],
            "start_id": c["start"],
            "end_id": c["end"] - 1,
            "teams": teams,
            "legions": legions,
            "team_size": c["team_size"],
            "teams_per_legion": c["teams_per_legion"],
            "first_code": agent_code(c["start"]),
            "last_code": agent_code(c["end"] - 1),
            "desc": c["desc"],
        })
    return out


def manifest() -> dict:
    return {
        "total_agents": TOTAL_AGENTS,
        "cohorts": cohort_summary(),
    }


# ── Parliament: the 8 cohort roots form a fully-connected clique ──────
# Every cohort's offset-0 agent is its "root"; the 8 roots are inter-linked
# so any agent reaches any other in ≤ 5 hops (tree-to-root ≤ 2, root ↔
# root = 1, root-to-leaf ≤ 2).
PARLIAMENT_IDS: list[int] = [c["start"] for c in COHORTS]


# ── Adaptive k-ary tree within each cohort ────────────────────────────
# Arity ≈ ⌈√size⌉, floored at 32, ceilinged at 4096. With k ≈ √size the
# tree has depth ≤ 2 for every cohort, so the whole mesh has diameter ≤ 5.
def _tree_arity(c: dict) -> int:
    import math
    k = int(math.isqrt(c["size"])) + 1
    if k < 32:
        k = 32
    if k > 4096:
        k = 4096
    return k


def tree_arity(cohort_or_id) -> int:
    c = cohort_or_id if isinstance(cohort_or_id, dict) else cohort_of(cohort_or_id)
    return _tree_arity(c)


def tree_parent_id(agent_id: int) -> Optional[int]:
    """Parent of agent_id in its cohort's k-ary tree. Root returns None."""
    c = cohort_of(agent_id)
    offset = agent_id - c["start"]
    if offset == 0:
        return None
    k = _tree_arity(c)
    parent_offset = (offset - 1) // k
    return c["start"] + parent_offset


def tree_children_ids(agent_id: int, cap: Optional[int] = None) -> list[int]:
    """Children of agent_id in its cohort's k-ary tree."""
    c = cohort_of(agent_id)
    offset = agent_id - c["start"]
    k = _tree_arity(c)
    start_child = offset * k + 1
    if start_child >= c["size"]:
        return []
    end_child = min(start_child + k, c["size"])
    ids = [c["start"] + o for o in range(start_child, end_child)]
    if cap is not None and cap > 0:
        ids = ids[:cap]
    return ids


def is_parliament(agent_id: int) -> bool:
    return agent_id in PARLIAMENT_IDS


def is_cohort_root(agent_id: int) -> bool:
    c = cohort_of(agent_id)
    return agent_id == c["start"]


def cohort_hub_ids(cohort: dict, k: int = 4) -> list[int]:
    """Top-k hub seats for a cohort (tree root + its first children)."""
    root = cohort["start"]
    hubs = [root]
    if k > 1:
        hubs.extend(tree_children_ids(root, cap=k - 1))
    return hubs


def all_cohort_hub_ids(k_per_cohort: int = 3) -> list[int]:
    out: list[int] = []
    for c in COHORTS:
        out.extend(cohort_hub_ids(c, k_per_cohort))
    return out
