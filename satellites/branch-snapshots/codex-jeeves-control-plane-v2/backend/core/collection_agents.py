"""
╔════════════════════════════════════════════════════════════════════════╗
║  COLLECTION AGENTS — 1 dedicated agent per existing Mongo collection   ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Complements the 200 Swarm Agents (core/swarm_agents.py) by assigning  ║
║  an agent to every live/frozen Mongo collection so NOTHING is          ║
║  voiceless in discourse. Agents are derived dynamically from the       ║
║  collection names — no static list to maintain.                        ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import re
from dotenv import load_dotenv

load_dotenv()

# ★ 2026-05 refactor (P2): use the shared sync client from core.databases
# instead of instantiating our own MongoClient — this consolidates the
# connection pool across all sync modules in the backend.
from core.databases import get_sync_db  # noqa: E402

_db = get_sync_db()


# ── Heuristic category mapping from collection-name prefix ──────────────
_PREFIX_CATEGORY = [
    ("mechanics_",       "mechanics"),
    ("descriptors_",     "descriptors"),
    ("models_",          "models"),
    ("textures_",        "textures"),
    ("renders_",         "rendering"),
    ("games_",           "games"),
    ("rosetta_",         "rosetta"),
    ("academy_",         "academy"),
    ("bible_",           "bibles"),
    ("bibles_",          "bibles"),
    ("bugfix",           "bugfix"),
    ("coding_",          "coding"),
    ("reading_",         "reading"),
    ("interactive_",     "interactive"),
    ("challenges_",      "challenges"),
    ("algo_",            "algorithms"),
    ("cheatsheet",       "cheatsheets"),
    ("flashcard",        "flashcards"),
    ("interview",        "interview"),
    ("knowledge_",       "knowledge"),
    ("leaderboard",      "leaderboards"),
    ("assessment",       "assessments"),
    ("projects",         "projects"),
    ("project_",         "projects"),
    ("career_",          "career"),
    ("god_tier",         "directives"),
    ("hyperion_",        "hyperion"),
    ("math_",            "math"),
    ("tech_",            "tech"),
    ("complexity_",      "complexity"),
    ("study_",           "study"),
    ("tracks",           "tracks"),
    ("library_",         "libraries"),
    ("languages",        "languages"),
    ("game_code",        "game_code"),
    ("unique_flair",     "unique_flair"),
    ("achievements",     "achievements"),
    ("exercises",        "exercises"),
    ("workaround",       "workarounds"),
    ("swarm_",           "swarm_meta"),
    ("cold_",            "cold_meta"),
    ("galaxy_",          "galaxy_meta"),
    ("jeeves_",          "jeeves_meta"),
]

_TITLE_SUFFIXES = [
    "Keeper", "Curator", "Loremaster", "Archivist", "Scribe", "Warden",
    "Shepherd", "Oracle", "Cartographer", "Synthesist", "Weaver",
    "Alchemist", "Inquisitor", "Sage", "Steward", "Artisan", "Conductor",
]


def _category_for(name: str) -> str:
    for pref, cat in _PREFIX_CATEGORY:
        if name.startswith(pref):
            return cat
    return "general"


def _pretty(name: str) -> str:
    return re.sub(r"[_\-]+", " ", name).title()


def _agent_title(name: str, idx: int) -> str:
    suf = _TITLE_SUFFIXES[idx % len(_TITLE_SUFFIXES)]
    return f"{_pretty(name)} {suf}"


def all_collection_names(include_system: bool = False) -> list[str]:
    names = _db.list_collection_names()
    if not include_system:
        names = [n for n in names if not n.startswith(("coll__", "system."))]
    # Dedup while preserving order
    seen = set(); out = []
    for n in names:
        if n not in seen:
            seen.add(n); out.append(n)
    return sorted(out)


def build_manifest(include_frozen: bool = True) -> list[dict]:
    """Return one agent per live Mongo collection + per frozen cold-shard.

    Every returned agent includes the Jeeves capabilities mirror so the full
    480+ roster shares the same agentic skill floor.
    """
    from core.compressed_vault import list_shards  # local to avoid cycles
    try:
        from core.jeeves_capabilities import mirror_onto as _mirror_caps
    except Exception:  # pragma: no cover
        def _mirror_caps(a: dict) -> dict:
            return a

    # Map category -> synthetic team_id (CT = Collection Team). We allocate 5
    # meta-legions (CL1..CL5) that mirror the swarm legion groupings so
    # collection agents sit alongside the correct swarm legion.
    _COLLECTION_LEGION_OF = {
        "rendering": "CL1", "models": "CL1", "textures": "CL1", "renders": "CL1",
        "mechanics": "CL2", "descriptors": "CL2",
        "games": "CL3", "rosetta": "CL3", "bibles": "CL3", "academy": "CL3",
        "coding": "CL4", "bugfix": "CL4", "workarounds": "CL4", "interview": "CL4",
        "algorithms": "CL4", "complexity": "CL4", "tech": "CL4", "hyperion": "CL4",
        "projects": "CL5", "career": "CL5", "challenges": "CL5", "cheatsheets": "CL5",
        "study": "CL5", "reading": "CL5", "knowledge": "CL5", "assessments": "CL5",
        "flashcards": "CL5", "directives": "CL5", "exercises": "CL5",
    }

    rows: list[dict] = []
    number = 200  # start after swarm agents
    for i, n in enumerate(all_collection_names()):
        number += 1
        cat = _category_for(n)
        legion = _COLLECTION_LEGION_OF.get(cat, "CL0")
        # Synthetic team id: one team per collection-category
        team_id = f"CT_{cat[:6].upper()}"
        rows.append(_mirror_caps({
            "id": f"coll__{n}",
            "collection": n,
            "agent_number": number,
            "agent_code": f"A{number:04d}",
            "domain": _pretty(n),
            "category": cat,
            "agent": _agent_title(n, i),
            "expertise": [tok for tok in re.split(r"[_\s]+", n) if tok and len(tok) > 2],
            "source": "mongo",
            "team_id": team_id,
            "team_name": _pretty(cat) + " Collective",
            "legion_id": legion,
            "legion_name": f"Collection-Legion {legion}",
            "signature": f"A{number:04d} · {team_id} · {legion} · {_agent_title(n, i)}",
        }))
    if include_frozen:
        registry_coll = _db["cold_registry"]
        live = {r["collection"] for r in rows}
        for doc in registry_coll.find({}):
            cname = doc.get("name")
            if not cname or cname in live:
                continue
            number += 1
            cat = _category_for(cname)
            legion = _COLLECTION_LEGION_OF.get(cat, "CL0")
            team_id = f"CT_{cat[:6].upper()}"
            rows.append(_mirror_caps({
                "id": f"coll__{cname}",
                "collection": cname,
                "agent_number": number,
                "agent_code": f"A{number:04d}",
                "domain": _pretty(cname),
                "category": cat,
                "agent": _agent_title(cname, len(rows)),
                "expertise": [tok for tok in re.split(r"[_\s]+", cname) if tok and len(tok) > 2],
                "source": "frozen",
                "team_id": team_id,
                "team_name": _pretty(cat) + " Collective",
                "legion_id": legion,
                "legion_name": f"Collection-Legion {legion}",
                "signature": f"A{number:04d} · {team_id} · {legion} · {_agent_title(cname, len(rows))}",
            }))
    return rows


def find_relevant_collection_agents(keywords: list[str], limit: int = 10) -> list[dict]:
    kw = {k.lower() for k in keywords if isinstance(k, str) and k}
    out: list[tuple[int, dict]] = []
    for a in build_manifest():
        score = 0
        for token in a["expertise"]:
            if token.lower() in kw:
                score += 1
        if a["category"] in kw:
            score += 2
        if score > 0:
            out.append((score, a))
    out.sort(key=lambda t: -t[0])
    return [a for _, a in out[:limit]]


def pick_legion(cat: str, limit: int = 20) -> list[dict]:
    """Return all collection-agents belonging to a given category."""
    return [a for a in build_manifest() if a["category"] == cat][:limit]


def category_histogram() -> dict[str, int]:
    h: dict[str, int] = {}
    for a in build_manifest():
        h[a["category"]] = h.get(a["category"], 0) + 1
    return h


def total_agents() -> int:
    return len(build_manifest())
