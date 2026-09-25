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

async def run_agent(agent_id: str, task: str, context: str = "") -> Dict[str, Any]:
    """Run a single agent"""
    if not LLM_AVAILABLE or not EMERGENT_KEY:
        return {"agent": agent_id, "error": "LLM not available", "output": ""}
    
    agent = AGENT_ROLES.get(agent_id)
    if not agent:
        return {"agent": agent_id, "error": "Unknown agent", "output": ""}
    
    try:
        chat = LlmChat(
            api_key=EMERGENT_KEY,
            system_message=agent["system"]
        ).with_model("openai", "gpt-4o")
        
        prompt = f"{task}\n\nContext:\n{context}" if context else task
        response = await chat.send_message(UserMessage(text=prompt))
        output = response.content if hasattr(response, 'content') else str(response)
        
        return {
            "agent": agent_id,
            "name": agent["name"],
            "role": agent["role"],
            "output": output,
            "timestamp": datetime.utcnow().isoformat()
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
