"""
GAME ROUTER — BUILD PIPELINE
Sub-router for project creation, build steps, compilation, and project management.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
import json
import uuid

from routes.game_shared import (
    call_llm, parse_json_response, _extract_code_blocks,
    projects_collection, vault_collection,
    CreateGameRequest, BuildStepRequest, CompileRequest,
)
from routes.game_command_agents import generate_holodeck_render

router = APIRouter()


def _get_build_pipeline():
    """Import BUILD_PIPELINE from game_factory (avoids circular import at module level)."""
    from routes.game_factory import BUILD_PIPELINE
    return BUILD_PIPELINE


def _get_game_genres():
    """Import GAME_GENRES from game_factory (avoids circular import at module level)."""
    from routes.game_factory import GAME_GENRES
    return GAME_GENRES


def _get_agent_prompt(*args, **kwargs):
    """Import get_agent_prompt from game_factory."""
    from routes.game_factory import get_agent_prompt
    return get_agent_prompt(*args, **kwargs)


@router.post("/create")
async def create_game_project(req: CreateGameRequest):
    """Create a new game project. Jeeves generates the initial GDD."""
    BUILD_PIPELINE = _get_build_pipeline()
    GAME_GENRES = _get_game_genres()
    get_agent_prompt = _get_agent_prompt

    project_id = str(uuid.uuid4())[:12]

    genre_info = next((g for g in GAME_GENRES if g["id"] == req.genre), None)
    if not genre_info and req.genre:
        genre_info = {"id": req.genre, "name": req.genre.replace("_", " ").title(), "complexity": "medium"}

    engine = req.engine or (genre_info or {}).get("engines", ["Pygame"])[0] if genre_info else "Pygame"

    project = {
        "project_id": project_id,
        "description": req.description,
        "genre": req.genre or "custom",
        "genre_info": genre_info,
        "engine": engine,
        "features": req.features or [],
        "art_style": req.art_style,
        "target_platform": req.target_platform,
        "user_id": req.user_id,
        "status": "designing",
        "current_step": 0,
        "total_steps": len(BUILD_PIPELINE),
        "steps_completed": [],
        "steps_data": {},
        "gdd": None,
        "compiled_output": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }

    sys_prompt, user_prompt = get_agent_prompt("gdd", req.description, req.genre or "custom", engine)
    if req.features:
        user_prompt += f"\n\nRequired features: {', '.join(req.features)}"
    if req.art_style:
        user_prompt += f"\nArt style: {req.art_style}"

    llm_result = await call_llm(sys_prompt, user_prompt, f"gdd_{project_id}")

    if llm_result["success"]:
        gdd = parse_json_response(llm_result["response"])
        project["gdd"] = gdd
        project["current_step"] = 1
        project["steps_completed"] = [1]
        project["steps_data"]["gdd"] = {
            "raw": llm_result["response"], "parsed": gdd,
            "agent": "jeeves", "completed_at": datetime.utcnow().isoformat(),
        }
        project["status"] = "in_progress"

        await vault_collection.insert_one({
            "agent_id": "jeeves", "agent_name": "Jeeves",
            "content": llm_result["response"], "content_type": "gdd",
            "code_blocks": [], "metadata": {"project_id": project_id, "step": "gdd"},
            "stored_at": datetime.utcnow().isoformat(),
            "parsed_by_jeeves": True, "learned_by_jeeves": False, "system_blurbs_enforced": True,
        })
    else:
        project["gdd"] = {
            "title": f"Game Project {project_id}", "genre": req.genre or "custom",
            "overview": req.description, "status": "llm_fallback", "error": llm_result.get("error"),
        }
        project["current_step"] = 1
        project["steps_completed"] = [1]
        project["status"] = "in_progress"

    await projects_collection.insert_one(project.copy())
    project.pop("_id", None)

    return {
        "project_id": project_id, "status": project["status"], "gdd": project["gdd"],
        "current_step": project["current_step"], "total_steps": len(BUILD_PIPELINE),
        "next_step": BUILD_PIPELINE[1] if len(BUILD_PIPELINE) > 1 else None, "pipeline": BUILD_PIPELINE,
    }


@router.post("/build-step")
async def execute_build_step(req: BuildStepRequest):
    """Execute the next build step for a project."""
    BUILD_PIPELINE = _get_build_pipeline()
    get_agent_prompt = _get_agent_prompt

    project = await projects_collection.find_one({"project_id": req.project_id})
    if not project:
        raise HTTPException(404, "Project not found")

    completed = project.get("steps_completed", [])
    next_step_num = req.step_number or (max(completed) + 1 if completed else 1)

    if next_step_num > len(BUILD_PIPELINE):
        raise HTTPException(400, "All steps completed. Use /compile to assemble.")

    if next_step_num in completed:
        raise HTTPException(400, f"Step {next_step_num} already completed")

    step_def = BUILD_PIPELINE[next_step_num - 1]
    prompt_key = step_def["prompt_key"]

    gdd_context = ""
    if project.get("gdd"):
        gdd = project["gdd"]
        gdd_context = json.dumps(gdd, indent=2)[:2000] if isinstance(gdd, dict) else str(gdd)[:2000]

    prev_outputs = []
    for sc in sorted(completed):
        step_key = BUILD_PIPELINE[sc - 1]["prompt_key"]
        step_data = project.get("steps_data", {}).get(step_key, {})
        if step_data.get("raw"):
            prev_outputs.append(f"[{BUILD_PIPELINE[sc-1]['name']}]: {str(step_data['raw'])[:500]}")

    full_context = gdd_context
    if prev_outputs:
        full_context += "\n\nPrevious outputs:\n" + "\n".join(prev_outputs[-3:])

    sys_prompt, user_prompt = get_agent_prompt(
        prompt_key, project.get("description", ""),
        project.get("genre", "custom"), project.get("engine", "Pygame"), full_context
    )

    llm_result = await call_llm(sys_prompt, user_prompt, f"{prompt_key}_{req.project_id}")

    step_result = {
        "raw": llm_result.get("response", ""),
        "parsed": parse_json_response(llm_result.get("response", "")) if llm_result["success"] else {},
        "agent": step_def["agent"], "agent_name": step_def["name"],
        "success": llm_result["success"], "completed_at": datetime.utcnow().isoformat(),
    }

    if not llm_result["success"]:
        step_result["error"] = llm_result.get("error", "LLM call failed")
        step_result["parsed"] = {"status": "fallback", "note": f"Agent {step_def['agent']} output pending LLM availability"}

    holodeck_render_result = None
    if llm_result["success"]:
        try:
            render_output = llm_result.get("response", "")[:600]
            game_desc = project.get("description", "Unknown game")
            holodeck_render_result = await generate_holodeck_render(
                team_name=f"Step {next_step_num}: {step_def['name']} ({step_def['agent']})",
                team_output=render_output,
                game_context=f"{game_desc} | Phase: {step_def['phase']}",
            )
            step_result["holodeck_render"] = holodeck_render_result
        except Exception:
            holodeck_render_result = {"success": False, "error": "Holodeck render skipped"}
            step_result["holodeck_render"] = holodeck_render_result

    completed.append(next_step_num)
    update_data = {
        f"steps_data.{prompt_key}": step_result, "steps_completed": completed,
        "current_step": next_step_num, "updated_at": datetime.utcnow().isoformat(),
    }
    update_data["status"] = "ready_to_compile" if next_step_num >= len(BUILD_PIPELINE) else "in_progress"

    await projects_collection.update_one({"project_id": req.project_id}, {"$set": update_data})

    if llm_result["success"]:
        await vault_collection.insert_one({
            "agent_id": step_def["agent"], "agent_name": step_def["name"],
            "content": llm_result.get("response", ""), "content_type": prompt_key,
            "code_blocks": _extract_code_blocks(llm_result.get("response", "")),
            "metadata": {"project_id": req.project_id, "step": next_step_num,
                         "holodeck_render": holodeck_render_result.get("image_url") if holodeck_render_result else None},
            "stored_at": datetime.utcnow().isoformat(),
            "parsed_by_jeeves": False, "learned_by_jeeves": False, "system_blurbs_enforced": True,
        })

    next_step = BUILD_PIPELINE[next_step_num] if next_step_num < len(BUILD_PIPELINE) else None

    return {
        "project_id": req.project_id, "step_completed": next_step_num,
        "step_name": step_def["name"], "agent": step_def["agent"], "phase": step_def["phase"],
        "result": step_result, "holodeck_render": holodeck_render_result,
        "progress": f"{len(completed)}/{len(BUILD_PIPELINE)}", "next_step": next_step,
        "status": update_data.get("status", "in_progress"),
    }


@router.post("/compile")
async def compile_game(req: CompileRequest):
    """FULL COMPILE MODE — Jeeves assembles all agent outputs into a complete game."""
    BUILD_PIPELINE = _get_build_pipeline()
    get_agent_prompt = _get_agent_prompt

    project = await projects_collection.find_one({"project_id": req.project_id})
    if not project:
        raise HTTPException(404, "Project not found")

    steps_data = project.get("steps_data", {})
    all_outputs = []
    for step in BUILD_PIPELINE:
        key = step["prompt_key"]
        if key in steps_data and key != "compile":
            data = steps_data[key]
            raw = data.get("raw", "")
            if raw:
                all_outputs.append(f"=== {step['name']} (by {step['agent']}) ===\n{raw[:1500]}")

    if not all_outputs:
        raise HTTPException(400, "No build steps completed yet. Run /build-step first.")

    compile_context = "\n\n".join(all_outputs)
    sys_prompt, user_prompt = get_agent_prompt(
        "compile", project.get("description", ""),
        project.get("genre", "custom"), project.get("engine", "Pygame"), compile_context
    )

    llm_result = await call_llm(sys_prompt, user_prompt, f"compile_{req.project_id}")

    compile_output = {}
    if llm_result["success"]:
        compile_output = parse_json_response(llm_result.get("response", ""))
        compile_output["_raw"] = llm_result["response"]
        compile_output["compilation_status"] = "SUCCESS"
    else:
        compile_output = {
            "compilation_status": "FALLBACK", "error": llm_result.get("error"),
            "note": "Compile used fallback - check LLM availability",
            "partial_assembly": {"steps_available": list(steps_data.keys()),
                                 "total_content": sum(len(str(v.get("raw", ""))) for v in steps_data.values())},
        }

    compile_holodeck = None
    try:
        game_title = compile_output.get("title", project.get("description", ""))[:200]
        compile_holodeck = await generate_holodeck_render(
            team_name="FINAL COMPILE — Full Game",
            team_output=f"Compiled AAA game: {game_title}. {llm_result.get('response', '')[:400]}",
            game_context=f"{project.get('description', '')} | Genre: {project.get('genre', 'custom')} | Engine: {project.get('engine', 'Pygame')}",
        )
        compile_output["holodeck_hero_render"] = compile_holodeck
    except Exception:
        compile_holodeck = {"success": False, "error": "Holodeck compile render skipped"}

    await projects_collection.update_one(
        {"project_id": req.project_id},
        {"$set": {"compiled_output": compile_output, "status": "compiled",
                  "compiled_at": datetime.utcnow().isoformat(), "updated_at": datetime.utcnow().isoformat()}}
    )

    await vault_collection.insert_one({
        "agent_id": "jeeves", "agent_name": "Jeeves (Compile Mode)",
        "content": llm_result.get("response", json.dumps(compile_output)),
        "content_type": "compiled_game",
        "code_blocks": _extract_code_blocks(llm_result.get("response", "")),
        "metadata": {"project_id": req.project_id, "step": "compile"},
        "stored_at": datetime.utcnow().isoformat(),
        "parsed_by_jeeves": True, "learned_by_jeeves": False, "system_blurbs_enforced": True,
    })

    return {
        "project_id": req.project_id, "status": "compiled",
        "compilation": compile_output, "holodeck_hero_render": compile_holodeck,
        "steps_used": len(steps_data), "total_steps": len(BUILD_PIPELINE),
    }


@router.get("/project/{project_id}")
async def get_project(project_id: str):
    """Get full project details."""
    project = await projects_collection.find_one({"project_id": project_id})
    if not project:
        raise HTTPException(404, "Project not found")
    project.pop("_id", None)
    return project


@router.get("/projects")
async def list_projects(user_id: str = "default_user", limit: int = 20):
    """List all game projects."""
    projects = await projects_collection.find({"user_id": user_id}).sort("created_at", -1).limit(limit).to_list(limit)
    for p in projects:
        p.pop("_id", None)
    return {"projects": projects, "total": len(projects)}


@router.delete("/project/{project_id}")
async def delete_project(project_id: str):
    """Delete a game project."""
    result = await projects_collection.delete_one({"project_id": project_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Project not found")
    return {"status": "deleted", "project_id": project_id}


@router.post("/build-all")
async def build_all_steps(req: BuildStepRequest):
    """Execute ALL remaining build steps in sequence (auto-build)."""
    BUILD_PIPELINE = _get_build_pipeline()

    project = await projects_collection.find_one({"project_id": req.project_id})
    if not project:
        raise HTTPException(404, "Project not found")

    completed = project.get("steps_completed", [])
    results = []

    for step in BUILD_PIPELINE:
        step_num = step["step"]
        if step_num in completed:
            results.append({"step": step_num, "name": step["name"], "status": "already_completed"})
            continue
        try:
            step_req = BuildStepRequest(project_id=req.project_id, step_number=step_num, user_id=req.user_id)
            result = await execute_build_step(step_req)
            results.append({
                "step": step_num, "name": step["name"],
                "status": "completed" if result.get("result", {}).get("success") else "fallback",
                "agent": step["agent"],
            })
        except HTTPException:
            results.append({"step": step_num, "name": step["name"], "status": "skipped"})

    compile_result = None
    try:
        compile_req = CompileRequest(project_id=req.project_id, user_id=req.user_id)
        compile_result = await compile_game(compile_req)
    except HTTPException:
        pass

    return {"project_id": req.project_id, "build_results": results, "compile_result": compile_result, "status": "build_complete"}
