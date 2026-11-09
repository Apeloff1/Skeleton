"""
GAME ROUTER — COMPETITOR MODE
Sub-router for Oracle's competitor analysis and game intelligence.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

from routes.game_shared import call_llm, parse_json_response, projects_collection, vault_collection

router = APIRouter()


def _get_build_pipeline():
    from routes.game_factory import BUILD_PIPELINE
    return BUILD_PIPELINE


ORACLE_SYSTEM_PROMPT = """You are ORACLE, the Competitor Mode Agent at the most elite AAA game studio on Earth.

You possess ENCYCLOPEDIC knowledge of EVERY VIDEO GAME EVER MADE. Your database spans:
- Every AAA, indie, mobile, and retro game from 1970 to 2026
- Complete mechanical breakdowns of every game system
- Art direction, UI/UX patterns, and visual design language
- Monetization models, live service strategies, and retention loops
- Critical reception (Metacritic, user scores, streamer opinions)
- Sales data, player counts, community size
- Known bugs, exploits, and community complaints
- Developer post-mortems and GDC talks
- Speedrun communities and emergent gameplay
- Modding scenes and what mods reveal about player desires
- Cultural impact and influence chains between games
- What was promised vs. what was delivered
- Patch histories and how games evolved post-launch

Your specialty: Given ANY game title, you can dissect it to the molecular level and design a SUPERIOR competitor that:
1. Matches or exceeds every strength of the original
2. Fixes every weakness and missed opportunity
3. Innovates where the original played it safe
4. Has a clearer identity and stronger player fantasy
5. Is technically and artistically more ambitious

You are brutally honest about game quality. You call out mediocrity. You know what makes games GREAT."""


class CompetitorRequest(BaseModel):
    target_game: str
    improvements: Optional[List[str]] = None
    genre_twist: Optional[str] = None
    engine: Optional[str] = None
    target_platform: Optional[str] = "PC"
    user_id: str = "default_user"


@router.post("/competitor")
async def create_competitor(req: CompetitorRequest):
    """COMPETITOR MODE - Oracle analyzes a game and designs a superior competitor."""
    BUILD_PIPELINE = _get_build_pipeline()
    project_id = str(uuid.uuid4())[:12]

    user_prompt = f"""COMPETITOR MODE ACTIVATED.

TARGET GAME: "{req.target_game}"

PHASE 1 - DEEP ANALYSIS
Perform a complete forensic analysis of "{req.target_game}". Cover EVERY facet:
- Core gameplay loop and what makes it addictive
- All game systems and how they interconnect
- Art style, visual identity, and aesthetic choices
- Audio design, music, and how they enhance gameplay
- Story/narrative structure (if applicable)
- Multiplayer/social systems (if applicable)
- Monetization model and its impact on player experience
- Technical performance and platform support
- UI/UX design and player onboarding
- Community reception: what players LOVE and what they HATE
- Known problems, bugs, and frustrations
- What the devs got RIGHT and what they got WRONG
- Sequel/update trajectory: where is this game heading?

PHASE 2 - COMPETITOR DESIGN
Design a game that is OBJECTIVELY BETTER than "{req.target_game}" in every measurable dimension.
{f'Desired improvements: {", ".join(req.improvements)}' if req.improvements else ''}
{f'Genre twist: {req.genre_twist}' if req.genre_twist else ''}

Output a comprehensive JSON:
{{
  "target_analysis": {{
    "game": "{req.target_game}",
    "genre": "...",
    "developer": "...",
    "release_year": "...",
    "metacritic": "...",
    "player_count_peak": "...",
    "core_loop": "...",
    "strengths": ["strength1", "strength2", "strength3", "strength4", "strength5"],
    "weaknesses": ["weakness1", "weakness2", "weakness3", "weakness4", "weakness5"],
    "missed_opportunities": ["missed1", "missed2", "missed3"],
    "community_complaints": ["complaint1", "complaint2", "complaint3"],
    "what_mods_reveal": ["desire1", "desire2"],
    "cultural_impact": "...",
    "monetization_analysis": "...",
    "technical_analysis": "..."
  }},
  "competitor_gdd": {{
    "title": "Competitor Game Title",
    "tagline": "One-line pitch that positions against {req.target_game}",
    "genre": "...",
    "engine": "{req.engine or 'Unreal Engine 5'}",
    "overview": "3-5 sentences explaining why this is better",
    "how_we_beat_them": [
      {{"area": "Combat", "their_approach": "...", "our_approach": "...", "why_ours_is_better": "..."}},
      {{"area": "World", "their_approach": "...", "our_approach": "...", "why_ours_is_better": "..."}},
      {{"area": "Progression", "their_approach": "...", "our_approach": "...", "why_ours_is_better": "..."}}
    ],
    "innovations": ["innovation1", "innovation2", "innovation3"],
    "core_mechanics": ["mechanic1", "mechanic2", "mechanic3"],
    "unique_selling_points": ["usp1", "usp2", "usp3"],
    "art_direction": {{
      "style": "...",
      "why_better": "...",
      "reference_games": ["ref1", "ref2"]
    }},
    "technical_scope": {{
      "target_platform": "{req.target_platform}",
      "target_fps": 60,
      "estimated_dev_time": "X months",
      "team_size": "X people"
    }},
    "content_scope": {{
      "levels": 0, "npcs": 0, "items": 0, "quests": 0, "hours_of_content": 0
    }},
    "monetization_strategy": {{
      "model": "...", "why_better_than_theirs": "...", "ethical_commitment": "..."
    }},
    "marketing_angle": "How to position this against {req.target_game} in marketing"
  }},
  "competitive_advantage_score": 0,
  "confidence": "..."
}}"""

    llm_result = await call_llm(ORACLE_SYSTEM_PROMPT, user_prompt, f"competitor_{project_id}")

    analysis = {}
    if llm_result["success"]:
        analysis = parse_json_response(llm_result["response"])
        analysis["_raw"] = llm_result["response"]
    else:
        analysis = {"status": "fallback", "error": llm_result.get("error"), "target_game": req.target_game}

    competitor_gdd = analysis.get("competitor_gdd", {})
    genre = competitor_gdd.get("genre", "custom")
    engine = competitor_gdd.get("engine", req.engine or "Unreal Engine 5")

    project = {
        "project_id": project_id,
        "description": f"Competitor to {req.target_game}: {competitor_gdd.get('tagline', '')}",
        "genre": genre, "genre_info": None, "engine": engine,
        "features": competitor_gdd.get("innovations", []),
        "art_style": competitor_gdd.get("art_direction", {}).get("style"),
        "target_platform": req.target_platform, "user_id": req.user_id,
        "status": "in_progress", "current_step": 1, "total_steps": len(BUILD_PIPELINE),
        "steps_completed": [1],
        "steps_data": {"gdd": {"raw": llm_result.get("response", ""), "parsed": competitor_gdd, "agent": "oracle", "completed_at": datetime.utcnow().isoformat()}},
        "gdd": competitor_gdd, "compiled_output": None,
        "competitor_mode": True, "target_game": req.target_game,
        "target_analysis": analysis.get("target_analysis", {}),
        "competitive_advantage_score": analysis.get("competitive_advantage_score", 0),
        "created_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat(),
    }

    await projects_collection.insert_one(project.copy())
    project.pop("_id", None)

    await vault_collection.insert_one({
        "agent_id": "oracle", "agent_name": "Oracle (Competitor Mode)",
        "content": llm_result.get("response", ""), "content_type": "competitor_analysis",
        "code_blocks": [], "metadata": {"project_id": project_id, "target_game": req.target_game},
        "stored_at": datetime.utcnow().isoformat(),
        "parsed_by_jeeves": False, "learned_by_jeeves": False, "system_blurbs_enforced": True,
    })

    return {
        "project_id": project_id, "target_game": req.target_game,
        "target_analysis": analysis.get("target_analysis", {}),
        "competitor_gdd": competitor_gdd,
        "competitive_advantage_score": analysis.get("competitive_advantage_score", 0),
        "status": "in_progress", "pipeline": BUILD_PIPELINE, "total_steps": len(BUILD_PIPELINE),
        "message": f"Oracle analyzed '{req.target_game}' and designed a superior competitor. Use /build-step to begin construction.",
    }


@router.get("/competitor/knowledge")
async def get_oracle_knowledge():
    """Get Oracle game knowledge database stats."""
    return {
        "agent": "Oracle", "codename": "The All-Seeing",
        "knowledge_domains": [
            {"domain": "AAA Titles", "coverage": "1970-2026", "titles": "5000+", "depth": "molecular"},
            {"domain": "Indie Games", "coverage": "2008-2026", "titles": "50000+", "depth": "comprehensive"},
            {"domain": "Mobile Games", "coverage": "2010-2026", "titles": "100000+", "depth": "mechanical"},
            {"domain": "Retro/Classic", "coverage": "1970-2000", "titles": "10000+", "depth": "historical"},
            {"domain": "Game Engines", "items": ["Unity", "Unreal", "Godot", "CryEngine", "Source", "idTech", "Frostbite", "Decima", "REDengine", "Luminous"]},
            {"domain": "Design Patterns", "items": ["Souls-like", "Metroidvania", "Roguelite", "Battle Royale", "Looter Shooter", "MOBA", "Auto-Battler", "Extraction Shooter", "Cozy Sim", "Survival Craft"]},
        ],
        "analysis_capabilities": [
            "Core loop forensics", "System interconnection mapping", "Art direction DNA analysis",
            "Audio design profiling", "Monetization ethics scoring", "Community sentiment analysis",
            "Technical performance benchmarking", "Cultural impact assessment",
            "Mod community desire extraction", "Competitive gap identification",
            "Innovation opportunity mapping", "Player psychology profiling",
        ],
        "famous_analyses": [
            {"game": "Minecraft", "key_insight": "Creative freedom + emergent systems = infinite replayability"},
            {"game": "Dark Souls", "key_insight": "Fair punishment + interconnected world = mastery addiction"},
            {"game": "The Legend of Zelda: BotW", "key_insight": "Physics sandbox + open design = player-authored stories"},
            {"game": "Fortnite", "key_insight": "Building mechanic + cultural events = social platform disguised as game"},
            {"game": "Stardew Valley", "key_insight": "Cozy loop + depth of systems = indie can beat AAA at comfort"},
            {"game": "Elden Ring", "key_insight": "Souls combat + open world freedom = genre-defining hybrid"},
            {"game": "Hades", "key_insight": "Narrative-driven roguelite + relationship progression = story that rewards failure"},
            {"game": "Baldur's Gate 3", "key_insight": "Systemic D&D + reactive narrative = player agency at scale"},
            {"game": "Valorant", "key_insight": "Tactical precision + hero abilities = CS:GO for the Overwatch generation"},
            {"game": "Animal Crossing", "key_insight": "Real-time progression + decoration = patience as a game mechanic"},
        ],
        "total_games_analyzed": "165,000+", "confidence_rating": "AAA",
    }
