#!/usr/bin/env python3
"""Exercise guided Jeeves through actual Expo, HTTP owners and disposable Mongo.

Fixtures are explicit: bearer account lookup, initial device Workbench/chat
cache, scripted model reply text and storage-admission receipts. No model is
called. Workflow validation, Studio project/goal HTTP, Mongo persistence and
browser interactions execute their canonical implementations.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]


async def qualify(args):
    import httpx
    from fastapi import FastAPI, Header
    from fastapi.middleware.cors import CORSMiddleware
    from motor.motor_asyncio import AsyncIOMotorClient
    from playwright.async_api import async_playwright, expect
    import uvicorn
    from core import game_studio_agent as studio
    from core.conversations import MongoConversationAuthority
    from core.game_learning import GameLearningWorkspace
    from routes import ai, conversations, game_learning, game_studio_agent, gameforge_auth, health, skeleton_gameforge
    from skeleton.contracts.ai_workflows import prepare_workflow_draft

    output = Path(args.output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Evidence must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads(Path(args.mongo_config).read_text())
    database_name = config["database_prefix"][:16] + "_journeys_" + uuid4().hex[:20]
    mongo = AsyncIOMotorClient(config["uri"], serverSelectionTimeoutMS=5000)
    db = mongo[database_name]
    await db.command("ping")
    account = {"email": "journey-browser@example.test", "tenant_id": "journey-browser", "role": "editor"}
    token = secrets.token_urlsafe(32)
    workspace = GameLearningWorkspace(db)
    counts = {"catalogs": 0, "drafts": 0, "artifact_reviews": 0, "goal_posts": 0, "model_calls": 0, "admissions": 0}

    async def admission(scope, resource, write_id, size):
        counts["admissions"] += 1
        return {"storage_bytes": size, "fixture": "test-only-storage-admission"}

    workspace._admit = admission
    game_learning.workspace = skeleton_gameforge.workspace = studio.workspace = workspace
    studio._rows, studio._indexes_ready = workspace.revisions, False
    conversations.conversation_authority = MongoConversationAuthority(db)
    gameforge_auth._enforced = lambda: True

    def principal(authorization: str | None = Header(default=None)):
        return dict(account) if authorization == "Bearer " + token else None

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=[args.web], allow_headers=["*"], allow_methods=["*"])
    app.dependency_overrides[gameforge_auth.get_current_user] = principal
    app.include_router(ai.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api/v1")
    app.include_router(game_learning.router, prefix="/api")
    app.include_router(game_studio_agent.router, prefix="/api")
    app.include_router(skeleton_gameforge.router)
    app.include_router(health.router, prefix="/api")

    @app.get("/api/auth/me")
    def me(authorization: str | None = Header(default=None)):
        value = principal(authorization)
        return {"authenticated": value is not None, "enforced": True,
                "role": value["role"] if value else "anonymous", "user": value}

    @app.middleware("http")
    async def observe(request, call_next):
        path = request.url.path
        if path == "/api/ai/workflow-journeys": counts["catalogs"] += 1
        if path == "/api/ai/workflow-drafts": counts["drafts"] += 1
        if path == "/api/ai/workflow-artifacts": counts["artifact_reviews"] += 1
        if path == "/api/ai/chat": counts["model_calls"] += 1
        if request.method == "POST" and path.endswith("/goals"): counts["goal_posts"] += 1
        return await call_next(request)

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="error"))
    serving = asyncio.create_task(server.serve())
    api = "http://127.0.0.1:" + str(args.port)
    report = {"schema": "skeleton.jeeves.guided-browser.v1", "status": "running", "checks": [],
              "fixtures": ["authenticated bearer account lookup", "initial device-local Workbench and chat cache",
                           "scripted model reply text", "test-only storage-admission receipts", "seeded source-only creator draft"],
              "mongo": "actual authenticated disposable Mongo", "provider_model_executed": False,
              "observed_at": datetime.now(timezone.utc).isoformat(), "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "sources": {}, "page_errors": [], "external_browser_requests": [], "observed": counts}
    source_paths = ["skeleton/contracts/ai_workflows.py", "backend/routes/ai.py", "backend/core/game_studio_agent.py",
                    "backend/core/game_learning.py", "frontend/src/product/aiJourneyClient.ts",
                    "frontend/src/features/Jeeves/journeys/GuidedJourneysPanel.tsx",
                    "frontend/src/features/Jeeves/journeys/JourneyResultActions.tsx",
                    "frontend/src/features/Jeeves/journeys/journeyDraft.ts",
                    "frontend/src/features/Jeeves/journeys/journeyWorkbench.ts",
                    "frontend/src/features/Jeeves/workbench/WorkbenchStore.ts"]
    for path in source_paths: report["sources"][path] = sha256((ROOT / path).read_bytes()).hexdigest()
    report["harness_sha256"] = sha256(Path(__file__).read_bytes()).hexdigest()
    browser = None
    try:
        for _ in range(200):
            if server.started: break
            if serving.done(): await serving
            await asyncio.sleep(.05)
        assert server.started, "Qualification HTTP server did not start"
        async with httpx.AsyncClient(base_url=api, headers={"Authorization": "Bearer " + token}, timeout=30) as http:
            created = await http.post("/api/skeleton/projects", json={"name": "Journey Forge Plan", "idempotency_key": "journey-project"})
            assert created.status_code == 200, created.text
            forge_project = created.json()["project"]
            scope = workspace._scope(account["tenant_id"], account["email"])
            await workspace.create_project(scope, {"name": "Dragon creator draft", "console_id": "dragon_native:pc_linux", "idempotency_key": "creator-fixture"},
                                           initial_files=[{"path": "game/editor/dragon_native.json", "content": "{}"}], source_only=True)
            if args.http_only:
                catalog = await http.get("/api/ai/workflow-journeys")
                assert catalog.status_code == 200 and len(catalog.json()["catalog"]["journeys"]) == 5
                assert catalog.headers["cache-control"] == "no-store"
                request = {"journey_id": "plan", "goal": "Review original movement", "options": {}, "source_refs": []}
                draft = await http.post("/api/ai/workflow-drafts", json=request)
                assert draft.status_code == 200 and draft.json()["draft"]["execution_authorized"] is False
                assert (await http.get("/api/ai/workflow-journeys", headers={"Authorization": ""})).status_code == 401
                report["checks"].append("Actual typed catalog/draft HTTP wrappers and anonymous denial work without model dispatch")
                path = "/api/game-studio-agent/projects/" + forge_project["project_id"] + "/goals"
                body = {"expected_version": forge_project["version"], "idempotency_key": "preflight-goal",
                        "goal": "Inspect original source", "execution_mode": "plan", "allow_edits": False,
                        "max_jobs": 0, "completion_mode": "native", "completion_requirements": []}
                first = await http.post(path, json=body)
                assert first.status_code == 200, first.text
                replay = await http.post(path, json=body)
                assert replay.status_code == 200 and replay.json()["goal"]["goal_id"] == first.json()["goal"]["goal_id"]
                conflict = await http.post(path, json={**body, "goal": "Changed proposal"})
                assert conflict.status_code == 409 and await workspace.revisions.count_documents({**scope, "kind": "studio_agent_goal"}) == 1
                report["checks"].append("Actual Mongo plan-only goal admits once, replays exactly and rejects changed content under its original key")
                report["scope"] = "HTTP/Mongo preflight only; no browser or model execution"
                report["status"] = "passed"
                return
            seed_code = "const {harness}=require('./scripts/jeeves-workbench/helpers.cjs');const h=harness('journey-browser');h.project({title:'Orbital Garden',goal:'PRIVATE_PROJECT_GOAL_MUST_NOT_AUTO_ATTACH',context:'PRIVATE_CONTEXT_MUST_NOT_AUTO_ATTACH'});h.source({title:'Movement observation',kind:'observation',locator:'local:movement-test',excerpt:'Movement at 30 and 60 FPS reached the same distance.'});process.stdout.write(JSON.stringify(h.state));"
            seed = json.loads(subprocess.check_output(["node", "-e", seed_code], cwd=ROOT / "frontend", text=True))
            scope_key = sha256(json.dumps([account["tenant_id"], account["email"]], separators=(",", ":")).encode()).hexdigest()
            cache_key = "@tutolage/jeeves-account:v2:" + scope_key
            workbench_key = "@tutolage/jeeves-workbench:v1"
            now = int(datetime.now(timezone.utc).timestamp() * 1000)
            chat = {"id": "guided-browser-chat", "title": "Guided qualification", "createdAt": now, "updatedAt": now,
                    "pinned": False, "archived": False, "draft": "", "context": "", "allForms": False,
                    "sessionId": None, "sessionUpdatedAt": 0, "messages": []}
            saved = {"version": 1, "activeId": chat["id"], "conversations": [chat]}
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(executable_path=args.chromium, headless=True, args=["--no-sandbox"])
                context = await browser.new_context(viewport={"width": 1440, "height": 1000})
                await context.add_init_script("if(!localStorage.getItem('gameforge_auth_token'))localStorage.setItem('gameforge_auth_token'," + json.dumps(token) + ");if(!localStorage.getItem(" + json.dumps(workbench_key) + "))localStorage.setItem(" + json.dumps(workbench_key) + "," + json.dumps(json.dumps(seed)) + ");if(!localStorage.getItem(" + json.dumps(cache_key) + "))localStorage.setItem(" + json.dumps(cache_key) + "," + json.dumps(json.dumps(saved)) + ");")
                goal_requests = []
                async def transport(route):
                    request = route.request; parsed = urlsplit(request.url)
                    if parsed.path.startswith("/api/"):
                        if request.method == "POST" and parsed.path.endswith("/goals"):
                            goal_requests.append(json.loads(request.post_data or "{}"))
                        await route.continue_(url=api + parsed.path + (("?" + parsed.query) if parsed.query else ""))
                    elif parsed.hostname not in {"localhost", "127.0.0.1"}:
                        report["external_browser_requests"].append(parsed.hostname); await route.abort()
                    else: await route.continue_()
                await context.route("**/*", transport)
                page = await context.new_page()
                page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
                await page.goto(args.web + "/jeeves-chat", wait_until="domcontentloaded", timeout=120000)
                await page.get_by_test_id("journey-open").click(timeout=120000)
                await expect(page.get_by_test_id("journey-choose-plan")).to_be_visible(timeout=30000)
                report["checks"].append("Cold stored bearer opens the real typed journey catalog without an account-change retry")
                await page.get_by_test_id("journey-choose-plan").click()
                await page.get_by_test_id("journey-goal").fill("Plan an original orbital garden prototype with tested movement.")
                await page.get_by_role("button", name="+ Movement observation", exact=True).click()
                await page.get_by_test_id("journey-prepare").click()
                await expect(page.get_by_test_id("journey-preview")).to_be_visible()
                await page.screenshot(path=str(output / "guided-desktop.png"), full_page=True)
                await page.get_by_test_id("journey-replace").click()
                await expect(page.get_by_test_id("chat-input")).to_have_value(re.compile("JEEVES_WORKFLOW_REQUEST_V1="))
                prompt = await page.get_by_test_id("chat-input").input_value()
                assert "JEEVES_WORKFLOW_REQUEST_V1=" in prompt and "PRIVATE_PROJECT_GOAL" not in prompt and "PRIVATE_CONTEXT" not in prompt
                envelope = json.loads(next(line.split("=", 1)[1] for line in prompt.splitlines() if line.startswith("JEEVES_WORKFLOW_REQUEST_V1=")))
                assert envelope["request"]["options"]["strategy"] == "dependency_first" and len(envelope["request"]["source_refs"]) == 1
                report["checks"].append("Actual draft preview stages exact selected options and source without hidden project context or model dispatch")

                async def reply(journey, options, fields, message_id=None):
                    request = {"journey_id": journey, "goal": "Review original " + journey + " work", "options": options,
                               "source_refs": [{"id": "source-1", "label": "Movement observation", "locator": "local:movement-test", "excerpt": "Movement at 30 and 60 FPS reached the same distance."}]}
                    draft = prepare_workflow_draft(request)
                    artifact = {"schema_version": "skeleton.ai.workflow_artifact.v1", "journey_id": journey,
                                "request_digest": draft["request_digest"], "title": "Reviewed " + journey, **fields}
                    chat["messages"] = [{"id": "user-" + journey, "role": "user", "text": draft["prompt"], "createdAt": now, "status": "complete"},
                                        {"id": message_id or "reply-" + journey, "role": "jeeves", "text": json.dumps(artifact), "createdAt": now + 1,
                                         "status": "complete", "model": "Declared scripted response fixture"}]
                    chat["draft"] = ""
                    await page.evaluate("p => localStorage.setItem(p.key,p.value)", {"key": cache_key, "value": json.dumps(saved)})
                    await page.reload(wait_until="domcontentloaded")
                    await page.get_by_test_id("journey-result-open").click(timeout=60000)

                async def save_result():
                    await page.get_by_test_id("journey-result-check").click()
                    await expect(page.get_by_test_id("journey-result-proof")).to_be_visible(timeout=30000)
                    await page.get_by_test_id("journey-result-save").click()
                    await expect(page.get_by_role("dialog").get_by_text(re.compile("Reviewed journey saved"))).to_be_visible(timeout=30000)
                    return json.loads(await page.evaluate("key => localStorage.getItem(key)", workbench_key))

                await reply("plan", {"strategy": "dependency_first", "max_tasks": 4, "time_budget_minutes": 120, "cost_budget": 0},
                            {"tasks": [{"id": "build", "title": "Implement movement", "description": "Create bounded movement.", "estimate_minutes": 20, "cost": 0, "depends_on": []},
                                       {"id": "verify", "title": "Verify movement", "description": "Compare actual input outcomes.", "estimate_minutes": 15, "cost": 0, "depends_on": ["build"]}]})
                await page.get_by_label("Title", exact=True).first.fill("Reviewed movement implementation")
                work = await save_result()
                build = next(item for item in work["tasks"] if item["title"] == "Reviewed movement implementation")
                verify = next(item for item in work["tasks"] if item["title"] == "Verify movement")
                assert verify["dependencies"] == [build["id"]] and len(work["tasks"]) == 2
                report["checks"].append("Reviewed plan passes actual HTTP DAG checks and saves atomically with real allocated dependency IDs")
                await reply("research", {"focus": "comparison", "max_claims": 2},
                            {"summary": "The supplied observation reports consistent travel.", "claims": [{"text": "Distance matched at two frame rates.", "source_ids": ["source-1"], "confidence": "supported"}], "open_questions": ["Does this hold under latency?"]})
                work = await save_result()
                note = next(item for item in work["notes"] if item["title"] == "Reviewed research")
                assert note["confidence"] == "unverified" and note["sourceIds"] and "local:movement-test" in note["body"]
                report["checks"].append("Research preserves selected source provenance and remains explicitly unverified after saving")
                await reply("study", {"level": "beginner", "format": "short_answer", "max_cards": 2},
                            {"cards": [{"question": "What should be compared?", "answer": "Travel distance.", "explanation": "Compare equal durations.", "choices": [], "correct_choice": None, "source_ids": ["source-1"]},
                                       {"question": "What changes?", "answer": "Frame count.", "explanation": "Use two frame rates.", "choices": [], "correct_choice": None, "source_ids": ["source-1"]}]})
                work = await save_result()
                assert len(work["cards"]) == 2 and all(card["schedule"]["state"] == "new" for card in work["cards"])
                report["checks"].append("Study results become actual new scheduled cards through the existing Workbench owner")
                studio_fields = {"goal": "Inspect the saved original source.", "steps": [{"operation": "project.inspect", "description": "Review original source before proposing changes."}], "completion_requirements": []}
                studio_options = {"mode": "inspect", "completion_mode": "native"}
                await reply("studio", studio_options, studio_fields)
                await expect(page.get_by_text(re.compile("saved creator draft"))).to_be_visible(timeout=30000)
                assert await page.get_by_role("button", name="Dragon creator draft", exact=True).count() == 0
                await page.get_by_role("button", name="Journey Forge Plan · Forge source plan", exact=True).click()
                await page.get_by_test_id("journey-result-check").click()
                await page.get_by_test_id("journey-result-save").click()
                await expect(page.get_by_text(re.compile("Plan-only studio goal saved"))).to_be_visible(timeout=30000)
                assert len(goal_requests) == 1
                original_body = goal_requests[0]
                history_path = "/api/game-studio-agent/projects/" + forge_project["project_id"] + "/goals"
                history = (await http.get(history_path)).json()["goals"]
                assert len(history) == 1 and history[0]["execution_mode"] == "plan" and history[0]["allow_edits"] is False
                original_goal_id = history[0]["goal_id"]
                report["checks"].append("Dragon creator-only drafts are excluded; Forge receives exactly one real Mongo plan-only Studio goal")
                for index in range(32):
                    later = {**original_body, "goal": "Later explicit plan " + str(index), "idempotency_key": "later-" + str(index)}
                    result = await http.post(history_path, json=later)
                    assert result.status_code == 200, result.text
                assert original_goal_id not in {row["goal_id"] for row in (await http.get(history_path)).json()["goals"]}
                await reply("studio", studio_options, {**studio_fields, "goal": "Changed proposal under the same reply origin."})
                await page.get_by_role("button", name="Journey Forge Plan · Forge source plan", exact=True).click()
                await page.get_by_test_id("journey-result-check").click()
                await page.get_by_test_id("journey-result-save").click()
                await expect(page.get_by_role("alert").filter(has_text=re.compile("goal key already describes another request"))).to_be_visible(timeout=30000)
                assert await workspace.revisions.count_documents({**scope, "kind": "studio_agent_goal"}) == 33
                assert goal_requests[-1]["idempotency_key"] == original_body["idempotency_key"]
                await reply("studio", studio_options, studio_fields, "reply-studio-distinct")
                await page.get_by_role("button", name="Journey Forge Plan · Forge source plan", exact=True).click()
                await page.get_by_test_id("journey-result-check").click()
                await page.get_by_test_id("journey-result-save").click()
                await expect(page.get_by_text(re.compile("Plan-only studio goal saved"))).to_be_visible(timeout=30000)
                assert goal_requests[-1]["idempotency_key"] != original_body["idempotency_key"]
                assert await workspace.revisions.count_documents({**scope, "kind": "studio_agent_goal"}) == 34
                report["checks"].append("Edited reply cannot duplicate its goal beyond the latest32; identical content in a distinct reply gets a separate admission identity")
                await page.reload(wait_until="domcontentloaded")
                await page.set_viewport_size({"width": 390, "height": 844})
                await page.get_by_test_id("journey-open").click(timeout=60000)
                await page.get_by_test_id("journey-choose-creative").click()
                await page.get_by_test_id("journey-goal").fill("An original quiet expedition about growing a garden in orbit.")
                await page.get_by_test_id("journey-option-artifact-cast").click()
                await page.get_by_test_id("journey-option-tone-wonder").click()
                await page.get_by_test_id("journey-prepare").click()
                await expect(page.get_by_test_id("journey-preview")).to_be_visible()
                assert await page.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                await page.screenshot(path=str(output / "guided-mobile.png"), full_page=True)
                report["checks"].append("Creative option-driven preview remains usable at390px with no horizontal overflow or page errors")
                assert not report["page_errors"] and counts["model_calls"] == 0
                assert not report["external_browser_requests"]
                await context.close()
        assert all(sha256((ROOT / path).read_bytes()).hexdigest() == value for path, value in report["sources"].items()), "Product source changed during qualification"
        report["status"] = "passed"
    except BaseException as error:
        report["status"] = "failed"
        report["failure"] = {"type": type(error).__name__, "message": str(error)[:2000]}
        raise
    finally:
        if browser is not None and browser.is_connected(): await browser.close()
        server.should_exit = True
        try: await asyncio.wait_for(serving, timeout=10)
        except TimeoutError:
            serving.cancel(); await asyncio.gather(serving, return_exceptions=True)
        await mongo.drop_database(database_name)
        mongo.close()
        (output / "jeeves-journeys-browser-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "report": str(output / "jeeves-journeys-browser-report.json")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", default="http://localhost:3000")
    parser.add_argument("--port", type=int, default=8772)
    parser.add_argument("--mongo-config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--http-only", action="store_true", help="Run actual HTTP/Mongo setup and idempotency checks without taking the shared browser slot")
    args = parser.parse_args()
    if urlsplit(args.web).hostname not in {"localhost", "127.0.0.1"} or not 1024 <= args.port <= 65535:
        parser.error("Use a numeric-loopback/local Expo server and unprivileged API port")
    asyncio.run(qualify(args))


if __name__ == "__main__":
    main()
