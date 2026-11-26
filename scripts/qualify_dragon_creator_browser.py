#!/usr/bin/env python3
"""Actual Expo + FastAPI + disposable Mongo creator-continuity qualification.

Requires an already-running Expo web server and a private operator Mongo config.
Only account lookup and storage-admission are explicit fixtures. Creator API,
Mongo persistence, canonical revisions, art/starter routes and browser UI run
unchanged. No model, compiler, native renderer or source review is qualified.
"""
from __future__ import annotations

import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]


async def qualify(args):
    from fastapi import FastAPI, Header
    from fastapi.middleware.cors import CORSMiddleware
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo import MongoClient
    from playwright.async_api import async_playwright, expect
    import uvicorn
    from core.game_learning import GameLearningWorkspace
    from core import dragon_native_projects as creator
    from routes import dragon_academy

    output = Path(args.output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Evidence must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads(Path(args.mongo_config).read_text())
    database_name = config["database_prefix"][:24] + "_dragon_browser_" + uuid4().hex[:16]
    token = secrets.token_urlsafe(32)
    account = {"email": "creator-browser@example.test", "tenant_id": "creator-browser", "role": "editor"}
    mongo = AsyncIOMotorClient(config["uri"])
    sync = MongoClient(config["uri"])
    db = mongo[database_name]
    counts = {"creates": 0, "saves": 0, "admissions": 0}

    def authority():
        owner = GameLearningWorkspace(db)
        async def admit(scope, resource, write_id, size):
            counts["admissions"] += 1
            return {"storage_bytes": size, "fixture": "storage-admission-only"}
        owner._admit = admit
        return owner

    creator.creator_projects = creator.DragonCreatorProjects(authority())
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=[args.web], allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["X-Content-SHA256", "Content-Disposition"])
    app.include_router(dragon_academy.router)
    def principal(authorization: str | None = Header(default=None)):
        return account if authorization == "Bearer " + token else None
    app.dependency_overrides[dragon_academy.get_current_user] = principal
    @app.get("/api/auth/me")
    def me(authorization: str | None = Header(default=None)):
        current = principal(authorization)
        return {"authenticated": current is not None, "enforced": True,
                "role": current["role"] if current else "anonymous", "user": current}
    @app.middleware("http")
    async def observe(request, call_next):
        if request.url.path == "/api/dragon-academy/native/production/projects" and request.method == "POST":
            counts["creates"] += 1
        if request.url.path.startswith("/api/dragon-academy/native/production/projects/") and request.method == "PUT":
            counts["saves"] += 1
        return await call_next(request)

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="error"))
    worker = threading.Thread(target=server.run, daemon=True); worker.start()
    for _ in range(100):
        if server.started: break
        await asyncio.sleep(.1)
    assert server.started
    report = {"schema": "skeleton.dragon.creator-browser.v1", "checks": [],
              "fixtures": ["authenticated account dependency", "governed storage-admission response"],
              "mongo": "actual disposable authenticated Mongo", "model_executed": False,
              "creator_api_mocked": False, "mongo_mocked": False,
              "transport": "Browser API requests forwarded to the actual loopback FastAPI test application",
              "network_observation_scope": "Browser requests only; no whole-process offline qualification",
              "native_engine_executed": False, "source_review_granted": False,
              "python": sys.version.split()[0], "platform": platform.platform(),
              "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "tracked_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT)),
              "sources": {}, "page_errors": [], "external_browser_requests": []}
    for path in ["backend/core/game_learning.py", "backend/core/dragon_native_projects.py", "backend/routes/dragon_academy.py",
                 "frontend/app/dragon-native-production.tsx", "frontend/src/components/DragonOriginalPuzzleEditor.tsx",
                 "frontend/src/product/dragonCreatorProject.ts", "frontend/src/features/Jeeves/companion/DragonCreatorProjects.tsx",
                 "scripts/qualify_dragon_creator_browser.py"]:
        report["sources"][path] = sha256((ROOT / path).read_bytes()).hexdigest()
    started = time.monotonic()
    prefix = "/api/dragon-academy/native/production/projects"
    api = "http://127.0.0.1:" + str(args.port)
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
            report["browser"] = browser.version
            context = await browser.new_context(viewport={"width": 1440, "height": 1050}, accept_downloads=True)
            await context.add_init_script("localStorage.setItem('gameforge_auth_token'," + json.dumps(token) + ");")
            page = await context.new_page()
            page.set_default_timeout(20000)
            page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
            lost_ack = {"armed": False}
            async def transport(route):
                parsed = urlsplit(route.request.url)
                if parsed.path.startswith("/api/"):
                    target = api + parsed.path + (("?" + parsed.query) if parsed.query else "")
                    if lost_ack["armed"] and route.request.method == "PUT" and parsed.path.startswith(prefix):
                        lost_ack["armed"] = False
                        response = await route.fetch(url=target)
                        assert response.status == 200
                        await route.abort("failed")
                    else:
                        await route.continue_(url=target)
                elif parsed.hostname not in {"localhost", "127.0.0.1"}:
                    report["external_browser_requests"].append(parsed.hostname)
                    await route.abort()
                else:
                    await route.continue_()
            await context.route("**/*", transport)
            async def confirm_replacement(expected_title):
                await page.wait_for_function("""expected => {
                  const approval=document.querySelector('[data-testid="dcp-approve-replace"]');
                  const title=document.querySelector('[data-testid="dragon-native-title"]');
                  return !!approval || title?.value===expected;
                }""", arg=expected_title)
                if await page.get_by_test_id("dcp-approve-replace").is_visible():
                    await page.get_by_test_id("dcp-approve-replace").click()
                    await page.get_by_test_id("dcp-confirm-replace").click()
                await expect(page.get_by_test_id("dragon-native-title")).to_have_value(expected_title)
            await page.goto(args.web + "/dragon-native-production", wait_until="domcontentloaded", timeout=120000)
            try:
                await page.get_by_test_id("dragon-native-title").wait_for(timeout=60000)
            except BaseException:
                report["last_page"] = {"url": page.url,
                    "visible_text": (await page.locator("body").inner_text())[:4000]}
                await page.screenshot(path=str(output / "creator-failure.png"))
                raise
            print("Creator route ready", flush=True)
            await page.get_by_test_id("dragon-native-title").fill("Lantern Route Lab")
            await page.get_by_test_id("dragon-native-seed").fill("314159")
            await page.get_by_test_id("dragon-native-notes").fill("Authored exploration with branching stages")
            await page.get_by_test_id("dragon-native-style-fixed_screen_puzzle").click()
            await page.get_by_test_id("dragon-native-target-pc_linux").click()
            await page.get_by_test_id("dragon-native-target-pc_windows").click()
            for _ in range(3):
                await page.get_by_role("button", name="Reduce Campaign stages", exact=True).click()
            await page.get_by_test_id("dragon-native-authored").click()
            await page.get_by_role("button", name="Stage 1 row 2 column 2: .", exact=True).wait_for()
            await page.get_by_role("button", name="Stage 1 row 2 column 2: .", exact=True).click()
            await page.get_by_test_id("dragon-native-brief-toggle").click()
            await page.get_by_test_id("dragon-native-brief").fill("An original lantern game. Reference notes remain unapproved. α")
            citations = [{"source_id": "source-example", "revision_digest": "a" * 64,
                          "title": "Reference passage", "url": "https://example.test/design"}]
            await page.get_by_test_id("dragon-native-citations").fill(json.dumps(citations))
            await page.get_by_test_id("dcp-save").click()
            await page.get_by_test_id("dcp-status").filter(has_text="Saved revision 1").wait_for()
            print("Creator first save confirmed", flush=True)
            row = sync[database_name].game_learning_projects.find_one({})
            project_id = row["project_id"]
            original = json.loads(row["files"][0]["content"])
            assert original["seed"] == 314159 and original["authored_puzzles"][0][1][1] == "#"
            assert original["cited_brief"]["citations"] == citations and counts["creates"] == 1
            report["checks"].append("Explicit save persisted exact design, unfinished painted boards, targets and cited brief in actual Mongo")
            await page.reload(wait_until="domcontentloaded")
            await page.get_by_test_id("dcp-project-" + project_id).wait_for(timeout=60000)
            await page.get_by_test_id("dcp-project-" + project_id).click()
            await confirm_replacement(original["title"])
            assert await page.get_by_test_id("dragon-native-title").input_value() == original["title"]
            assert await page.get_by_test_id("dragon-native-seed").input_value() == "314159"
            await page.get_by_role("button", name="Stage 1 row 2 column 2: #", exact=True).wait_for()
            assert await page.get_by_test_id("dragon-native-export").is_disabled()
            report["checks"].append("Reload and explicit reopen restore authored source without restoring validation or export approval")
            await page.get_by_test_id("dragon-native-title").fill("Lantern Route Revised")
            lost_ack["armed"] = True
            await page.get_by_test_id("dcp-save").click()
            await page.get_by_test_id("dcp-retry").wait_for()
            await expect(page.get_by_test_id("dcp-retry")).to_be_enabled()
            assert sync[database_name].game_learning_projects.find_one({})["version"] == 2
            await page.get_by_test_id("dcp-retry").click()
            await page.get_by_test_id("dcp-status").filter(has_text="Saved revision 2").wait_for()
            assert sync[database_name].game_learning_projects.find_one({})["version"] == 2
            report["checks"].append("Lost save acknowledgment retries original identity without creating another revision")
            # Reconstruct the backend authority against exactly the same bytes.
            creator.creator_projects = creator.DragonCreatorProjects(authority())
            await page.get_by_test_id("dcp-refresh").click()
            await page.get_by_test_id("dcp-history-" + project_id).click()
            await page.get_by_test_id("dcp-revision-1").click()
            await confirm_replacement(original["title"])
            assert await page.get_by_test_id("dragon-native-title").input_value() == original["title"]
            assert sync[database_name].game_learning_projects.find_one({})["version"] == 2
            report["checks"].append("New backend authority reopens committed history; loading an old revision changes only the draft")
            async with page.expect_download() as downloading:
                await page.get_by_test_id("dcp-export").click()
            download = await downloading.value
            destination = output / "creator-project.json"; await download.save_as(destination)
            exported = json.loads(destination.read_text())
            assert exported["document"]["title"] == "Lantern Route Revised"
            assert set(exported) == {"schema", "document", "document_sha256"}
            report["export_sha256"] = sha256(destination.read_bytes()).hexdigest()
            report["checks"].append("Browser portable export delivers the saved source, preserving current unsaved history draft")
            import httpx
            async with httpx.AsyncClient() as peer:
                current = (await peer.get(api + prefix + "/" + project_id,
                    headers={"Authorization": "Bearer " + token})).json()["project"]
                peer_document = json.loads(json.dumps(current["document"]))
                peer_document["title"] = "Peer Lantern Revision"
                result = await peer.put(api + prefix + "/" + project_id,
                    headers={"Authorization": "Bearer " + token}, json={
                        "idempotency_key": "peer-write", "expected_version": current["version"],
                        "expected_sha256": current["document_sha256"], "document": peer_document})
                assert result.status_code == 200
            await page.get_by_test_id("dcp-save").click()
            await page.get_by_test_id("dcp-error").filter(has_text="newer revision").wait_for()
            assert await page.get_by_test_id("dragon-native-title").input_value() == original["title"]
            assert sync[database_name].game_learning_projects.find_one({"_id": project_id})["version"] == 3
            report["checks"].append("A real peer HTTP save causes an explicit CAS conflict while preserving the browser's authored draft")
            await page.get_by_test_id("dcp-save-copy").click()
            await page.get_by_test_id("dcp-status").filter(has_text="Saved revision 1").wait_for()
            assert sync[database_name].game_learning_projects.count_documents({}) == 2
            report["checks"].append("Save a copy resolves the conflict without overwriting the newer original")
            async with page.expect_file_chooser() as choosing:
                await page.get_by_test_id("dcp-import").click()
            chooser = await choosing.value
            await chooser.set_files(str(destination))
            await confirm_replacement("Lantern Route Revised")
            assert await page.get_by_test_id("dragon-native-title").input_value() == "Lantern Route Revised"
            await page.get_by_test_id("dcp-save").click()
            await page.get_by_test_id("dcp-status").filter(has_text="Saved revision 1").wait_for()
            assert sync[database_name].game_learning_projects.count_documents({}) == 3
            report["checks"].append("Verified portable JSON imports through the real file chooser into an explicitly saved independent project")
            await page.get_by_test_id("dcp-library").scroll_into_view_if_needed()
            await page.screenshot(path=str(output / "dragon-creator-desktop.png"))
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.get_by_test_id("dcp-library").scroll_into_view_if_needed()
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
            await page.screenshot(path=str(output / "dragon-creator-mobile.png"))
            assert not report["page_errors"], report["page_errors"]
            report["checks"].append("Desktop and 390px mobile primary project actions render without horizontal overflow or page errors")
            await browser.close()
        report.update(status="passed", observed=counts, elapsed_seconds=round(time.monotonic()-started, 3))
    except BaseException as error:
        report.update(status="failed", error=type(error).__name__ + ": " + str(error), observed=counts)
        raise
    finally:
        for path, digest in report["sources"].items():
            if sha256((ROOT / path).read_bytes()).hexdigest() != digest:
                report.setdefault("source_changed_during_run", []).append(path)
        (output / "dragon-creator-browser-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        server.should_exit = True; worker.join(timeout=10)
        sync.drop_database(database_name); sync.close(); mongo.close()
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "report": str(output / "dragon-creator-browser-report.json")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", default="http://localhost:3000")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--mongo-config", default="/workspace/verticals-runtime/mongo.json")
    parser.add_argument("--output", required=True)
    asyncio.run(qualify(parser.parse_args()))
