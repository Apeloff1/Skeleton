"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  MULTI-AGENT ORCHESTRATION SYSTEM - April 2026 SOTA                          ║
║  Coordinated AI Agent Swarms for Complex Task Execution                       ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import os
import uuid

router = APIRouter(prefix="/agents", tags=["Multi-Agent Systems"])

# LLM Setup
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    LLM_AVAILABLE = True
except Exception:
    LLM_AVAILABLE = False

EMERGENT_KEY = os.getenv("EMERGENT_LLM_KEY", "")

# ============================================================================
# AGENT DEFINITIONS
# ============================================================================

AGENT_ROLES = {
    # Code Architect System
    "planner": {
        "name": "Planner Agent",
        "role": "Breaks down complex tasks into actionable steps",
        "system": "You are a senior software architect. Break down coding tasks into clear, sequential steps. Output structured plans."
    },
    "coder": {
        "name": "Coder Agent", 
        "role": "Writes clean, efficient code",
        "system": "You are an expert programmer. Write clean, efficient, well-documented code. Follow best practices."
    },
    "reviewer": {
        "name": "Reviewer Agent",
        "role": "Reviews code for bugs, security, and best practices",
        "system": "You are a code reviewer. Find bugs, security issues, and suggest improvements. Be thorough but constructive."
    },
    "optimizer": {
        "name": "Optimizer Agent",
        "role": "Optimizes code for performance and readability",
        "system": "You are a performance engineer. Optimize code for speed, memory, and readability without changing functionality."
    },
    
    # Debug Swarm
    "analyzer": {
        "name": "Analyzer Agent",
        "role": "Analyzes code to identify root causes",
        "system": "You are a debugging expert. Analyze code and error messages to identify root causes. Be systematic."
    },
    "fixer": {
        "name": "Fixer Agent",
        "role": "Generates fixes for identified issues",
        "system": "You are a bug fixer. Generate minimal, targeted fixes that solve issues without side effects."
    },
    "tester": {
        "name": "Tester Agent",
        "role": "Creates test cases to verify fixes",
        "system": "You are a QA engineer. Write comprehensive test cases that verify fixes and prevent regressions."
    },
    "validator": {
        "name": "Validator Agent",
        "role": "Validates that solutions are complete and correct",
        "system": "You are a validation expert. Verify that solutions fully address the problem and don't introduce new issues."
    },
    
    # Teaching Ensemble
    "explainer": {
        "name": "Explainer Agent",
        "role": "Explains concepts clearly at any level",
        "system": "You are a master teacher. Explain concepts clearly with examples. Adapt to the student's level."
    },
    "quizzer": {
        "name": "Quizzer Agent",
        "role": "Creates questions to test understanding",
        "system": "You create educational quizzes. Generate questions that test understanding, not memorization."
    },
    "mentor": {
        "name": "Mentor Agent",
        "role": "Provides guidance and encouragement",
        "system": "You are a supportive mentor. Guide learners, celebrate progress, and help overcome obstacles."
    },
    "evaluator": {
        "name": "Evaluator Agent",
        "role": "Assesses skill level and progress",
        "system": "You evaluate coding skills objectively. Identify strengths, weaknesses, and growth areas."
    },
    
    # Asset Factory
    "designer": {
        "name": "Designer Agent",
        "role": "Creates asset specifications and style guides",
        "system": "You are a game artist. Design assets with clear specifications, style consistency, and game-ready requirements."
    },
    "generator": {
        "name": "Generator Agent",
        "role": "Generates AI prompts for asset creation",
        "system": "You create optimal prompts for AI image/3D generators. Maximize quality and consistency."
    },
    "refiner": {
        "name": "Refiner Agent",
        "role": "Refines and improves generated assets",
        "system": "You refine asset specifications. Improve quality, fix inconsistencies, optimize for game engines."
    },
    "exporter": {
        "name": "Exporter Agent",
        "role": "Prepares assets for export and integration",
        "system": "You prepare assets for game engines. Handle formats, optimization, and integration requirements."
    },
    
    # Game Builder
    "architect": {
        "name": "Game Architect Agent",
        "role": "Designs game systems and architecture",
        "system": "You are a game systems designer. Create scalable, maintainable game architectures."
    },
    "game_coder": {
        "name": "Game Coder Agent",
        "role": "Implements game mechanics and systems",
        "system": "You implement game mechanics. Write performant, clean game code for any engine."
    },
    "artist": {
        "name": "Artist Agent",
        "role": "Coordinates art assets and visual style",
        "system": "You coordinate game art. Ensure visual consistency and optimize for target platforms."
    },
    "game_tester": {
        "name": "Game Tester Agent",
        "role": "Tests gameplay and finds issues",
        "system": "You are a game QA specialist. Find bugs, balance issues, and UX problems."
    }
}

AGENT_SYSTEMS = {
    "code_architect": {
        "name": "Code Architect System",
        "description": "Multi-agent system for comprehensive code generation",
        "agents": ["planner", "coder", "reviewer", "optimizer"],
        "flow": "sequential"
    },
    "debug_swarm": {
        "name": "Debug Swarm",
        "description": "Coordinated agents for autonomous debugging",
        "agents": ["analyzer", "fixer", "tester", "validator"],
        "flow": "sequential"
    },
    "teaching_ensemble": {
        "name": "Teaching Ensemble",
        "description": "Adaptive learning with multiple teaching agents",
        "agents": ["explainer", "quizzer", "mentor", "evaluator"],
        "flow": "adaptive"
    },
    "asset_factory": {
        "name": "Asset Factory",
        "description": "End-to-end asset creation pipeline",
        "agents": ["designer", "generator", "refiner", "exporter"],
        "flow": "sequential"
    },
    "game_builder": {
        "name": "Game Builder",
        "description": "Full game development agent team",
        "agents": ["architect", "game_coder", "artist", "game_tester"],
        "flow": "parallel"
    }
}

# ============================================================================
# REQUEST MODELS
# ============================================================================

class AgentTask(BaseModel):
    task: str
    context: Optional[str] = None
    language: str = "python"
    preferences: Optional[Dict[str, Any]] = None

class MultiAgentRequest(BaseModel):
    system: str  # code_architect, debug_swarm, etc.
    task: str
    code: Optional[str] = None
    language: str = "python"
    context: Optional[Dict[str, Any]] = None
    max_iterations: int = 3

# ============================================================================
# AGENT EXECUTION
# ============================================================================

# ── Agent role → Model-Router task (2026-06) ──────────────────────────────
# Maps each swarm agent to the model ENSEMBLE best-fit for its specialty, so
# the agent-to-agent system genuinely orchestrates MULTIPLE AIs (coder on
# Claude/GPT-5.4, narrative on Opus, QA/balance on o3, naming on a fast mini),
# each with cross-vendor fallback + shared semantic cache + cost telemetry.
_AGENT_ROUTER_TASK = {
    # planning / reasoning
    "planner": "reasoning", "architect": "reasoning", "validator": "reasoning",
    "analyzer": "reasoning", "evaluator": "reasoning",
    # code
    "coder": "gameplay_code", "game_coder": "gameplay_code",
    "reviewer": "code", "optimizer": "code", "refiner": "code",
    "fixer": "bug_fix",
    # QA
    "tester": "playtest_qa", "game_tester": "playtest_qa",
    # design / content / assets
    "designer": "game_design_doc", "generator": "creative",
    "artist": "procedural_assets", "exporter": "default",
    # teaching personas
    "explainer": "default", "quizzer": "fast", "mentor": "fast",
}


async def run_agent(agent_id: str, task: str, context: str = "") -> Dict[str, Any]:
    """Run a single agent — now backed by Jeeves consult + vault patterns."""
    if not LLM_AVAILABLE or not EMERGENT_KEY:
        return {"agent": agent_id, "error": "LLM not available", "output": ""}
    
    agent = AGENT_ROLES.get(agent_id)
    if not agent:
        return {"agent": agent_id, "error": "Unknown agent", "output": ""}
    
    # ─────────────────────────────────────────────────────────────────
    # 2026 wiring — every agent step now:
    #   1. Consults Jeeves for context-appropriate guidance + mannerism
    #   2. Pulls 2-3 relevant patterns from the compressed vault
    #   3. Injects both into the prompt so the LLM speaks with both
    #      Jeeves' tone AND domain authority.
    # ─────────────────────────────────────────────────────────────────
    jeeves_block = ""
    vault_block = ""
    try:
        from services import jeeves_consultant
        # Map agent_id → Jeeves catchphrase BUCKET name (these match the
        # actual DB keys: greeting, encouragement, gentle_correction, alert,
        # debug, joke, sign_off, quiz_nudge, lesson_intro, celebration,
        # code_walkthrough, story_time, thinking, frustration_relief,
        # transition, definition, warning_clarification).
        role_to_ctx = {
            "architect": "lesson_intro",      "planner":   "lesson_intro",
            "debugger":  "debug",             "coder":     "code_walkthrough",
            "reviewer":  "gentle_correction", "tester":    "warning_clarification",
            "designer":  "story_time",        "writer":    "story_time",
            "optimizer": "celebration",       "teacher":   "lesson_intro",
            "tutor":     "encouragement",     "security":  "alert",
            "qa":        "warning_clarification", "marketer": "celebration",
            "researcher":"definition",        "asset_artist":"story_time",
            "audio":     "transition",        "physics":   "definition",
            "ecology":   "definition",        "ai_designer":"thinking",
            "director":  "lesson_intro",      "legal":     "warning_clarification",
            "academic":  "definition",
        }
        ctx = role_to_ctx.get(agent_id.lower(), "lesson_intro")
        topic_seed = task[:80]
        consult = await jeeves_consultant.consult(ctx, topic=topic_seed)
        if consult.get("catchphrase") or consult.get("knowledge"):
            jeeves_block = f"\n\n--- JEEVES GUIDANCE ({ctx}) ---\n"
            if consult.get("catchphrase"):
                jeeves_block += f"Mannerism: \"{consult['catchphrase']}\"\n"
            if consult.get("knowledge"):
                jeeves_block += f"Domain note: {consult['knowledge']}\n"
            if consult.get("citation"):
                jeeves_block += f"Source: {consult['citation']}\n"
    except Exception as _je:
        # Fail-soft — agent still runs without Jeeves context.
        pass

    try:
        from services import vault_loader
        # Derive a vault topic from the agent's role / task keywords.
        first_word = (task.split() or [""])[0].lower()
        candidates = [agent_id.lower(), first_word]
        for cand in candidates:
            if not cand: continue
            samples = vault_loader.query_topic(cand, limit=2)
            if samples:
                vault_block = "\n--- VAULT PATTERNS ---\n"
                for coll, rows in list(samples.items())[:2]:
                    vault_block += f"[{coll}]\n"
                    for row in rows[:2]:
                        # Keep it tight — agents don't need full payloads.
                        snippet = str(row)[:200].replace("\n", " ")
                        vault_block += f"  • {snippet}\n"
                break
    except Exception as _ve:
        pass

    # NEW (Feb 2026) — pull role-specific knowledge from Mongo collections
    # (game_design, build_recipes, qa_oracles, etc.) so each agent reasons
    # from authoritative DB rows, not just LLM priors.
    knowledge_block = ""
    matched_collections: list[str] = []
    try:
        from services import agent_knowledge_bridge as akb
        bridge = await akb.fetch_for_role(agent_id, topic=task[:80])
        matched_collections = bridge.get("matched_collections", [])
        knowledge_block = akb.format_for_prompt(bridge)
    except Exception:
        pass

    # Optionally — a famous Jeeves quote to sign off with (sprinkled rarely).
    quote_block = ""
    try:
        import random
        if random.random() < 0.25:
            from services import jeeves_consultant
            q = await jeeves_consultant.famous_quote()
            if q:
                quote_text = q.get("quote") or q.get("text") or ""
                attr = q.get("attribution") or q.get("by") or ""
                if quote_text:
                    quote_block = f"\n--- JEEVES QUOTES THE GREATS ---\n  \"{quote_text}\" — {attr}\n"
    except Exception:
        pass

    try:
        # System message now blends agent persona + Jeeves voice.
        system_msg = agent["system"]
        if jeeves_block:
            system_msg += "\n\n[You are advised by Jeeves — channel his measured, British, slightly witty tone in any user-facing prose, but keep technical answers precise.]"

        chat = None
        full_context = (context or "") + jeeves_block + vault_block + knowledge_block + quote_block
        prompt = f"{task}\n\nContext:\n{full_context}" if full_context else task
        # ── Agent-to-agent × Model Router ──────────────────────────────────
        # Dispatch through the central router on the agent's specialty task →
        # best-fit model ensemble, cross-vendor fallback, semantic cache, cost
        # telemetry. The agent reports WHICH AI powered it (multi-AI visibility).
        from routes.llm_router import route_complete
        router_task = _AGENT_ROUTER_TASK.get(agent_id.lower(), "default")
        routed = await route_complete(
            task=router_task, prompt=prompt, system=system_msg,
            session_id=f"agent_{agent_id}",
        )
        if routed.get("error"):
            return {"agent": agent_id, "error": routed["error"], "output": ""}
        output = routed.get("content", "")
        
        return {
            "agent": agent_id,
            "name": agent["name"],
            "role": agent["role"],
            "output": output,
            "timestamp": datetime.utcnow().isoformat(),
            "model":                 routed.get("model"),
            "provider":              routed.get("provider"),
            "router_task":           router_task,
            "cached":                routed.get("cached", False),
            "jeeves_consulted":      bool(jeeves_block),
            "vault_used":            bool(vault_block),
            "knowledge_collections": matched_collections,
            "knowledge_used":        bool(knowledge_block),
            "quote_included":        bool(quote_block),
        }
    except Exception as e:
        return {"agent": agent_id, "error": str(e), "output": ""}

async def run_agent_system(system_id: str, task: str, code: str = "", language: str = "python", max_iterations: int = 3) -> Dict[str, Any]:
    """Run a complete multi-agent system"""
    
    system = AGENT_SYSTEMS.get(system_id)
    if not system:
        raise HTTPException(status_code=404, detail="Agent system not found")
    
    execution_id = str(uuid.uuid4())[:8]
    results = {
        "execution_id": execution_id,
        "system": system["name"],
        "task": task,
        "started_at": datetime.utcnow().isoformat(),
        "agents": [],
        "final_output": None
    }
    
    context = f"Language: {language}\nCode:\n```{language}\n{code}\n```" if code else f"Language: {language}"
    current_output = ""
    
    for agent_id in system["agents"]:
        agent_task = f"{task}\n\nPrevious agent output:\n{current_output}" if current_output else task
        agent_result = await run_agent(agent_id, agent_task, context)
        results["agents"].append(agent_result)
        current_output = agent_result.get("output", "")
    
    results["final_output"] = current_output
    results["completed_at"] = datetime.utcnow().isoformat()
    results["total_agents"] = len(system["agents"])
    
    return results

# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.get("/info")
async def get_agents_info():
    """Get multi-agent systems information"""
    return {
        "name": "CodeDock Multi-Agent Orchestration",
        "version": "11.3.0",
        "description": "April 2026 SOTA - Coordinated AI agent swarms",
        "total_agents": len(AGENT_ROLES),
        "agent_systems": list(AGENT_SYSTEMS.keys()),
        "systems": {
            k: {
                "name": v["name"],
                "description": v["description"],
                "agent_count": len(v["agents"]),
                "flow": v["flow"]
            } for k, v in AGENT_SYSTEMS.items()
        },
        "capabilities": [
            "Multi-agent task coordination",
            "Sequential and parallel execution",
            "Context passing between agents",
            "Iterative refinement",
            "Specialized agent roles"
        ]
    }

@router.get("/roles")
async def get_agent_roles():
    """Get all available agent roles"""
    return {
        "roles": {
            k: {"name": v["name"], "role": v["role"]}
            for k, v in AGENT_ROLES.items()
        }
    }

@router.get("/systems")
async def get_agent_systems():
    """Get all agent systems"""
    return {"systems": AGENT_SYSTEMS}

@router.post("/run/{system_id}")
async def run_system(system_id: str, request: MultiAgentRequest):
    """Run a multi-agent system"""
    if system_id not in AGENT_SYSTEMS:
        raise HTTPException(status_code=404, detail="System not found")
    
    result = await run_agent_system(
        system_id,
        request.task,
        request.code or "",
        request.language,
        request.max_iterations
    )
    
    return result

@router.post("/code-architect")
async def code_architect(request: AgentTask):
    """Run the Code Architect multi-agent system"""
    return await run_agent_system("code_architect", request.task, request.context or "", request.language)

@router.post("/debug-swarm")
async def debug_swarm(request: AgentTask):
    """Run the Debug Swarm multi-agent system"""
    return await run_agent_system("debug_swarm", request.task, request.context or "", request.language)

@router.post("/teaching-ensemble")
async def teaching_ensemble(request: AgentTask):
    """Run the Teaching Ensemble multi-agent system"""
    return await run_agent_system("teaching_ensemble", request.task, request.context or "", request.language)

@router.post("/asset-factory")
async def asset_factory(request: AgentTask):
    """Run the Asset Factory multi-agent system"""
    return await run_agent_system("asset_factory", request.task, request.context or "", request.language)

@router.post("/game-builder")
async def game_builder(request: AgentTask):
    """Run the Game Builder multi-agent system"""
    return await run_agent_system("game_builder", request.task, request.context or "", request.language)

@router.post("/single/{agent_id}")
async def run_single_agent(agent_id: str, request: AgentTask):
    """Run a single agent"""
    if agent_id not in AGENT_ROLES:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return await run_agent(agent_id, request.task, request.context or "")
