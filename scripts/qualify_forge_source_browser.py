#!/usr/bin/env python3
"""Qualify actual Expo, Forge HTTP, Mongo and exact source ZIP continuity.

Only authenticated account lookup and governed storage admission are fixtures.
The original source compiler, durable jobs, Mongo chunks, browser controls and
downloads are real. No provider model, Godot process or native binary is tested.
Run serially with other browser checks against the shared Expo development app.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
import io
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
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]


async def qualify(args):
    from fastapi import FastAPI, Header
    from fastapi.middleware.cors import CORSMiddleware
    from motor.motor_asyncio import AsyncIOMotorClient
    from playwright.async_api import async_playwright, expect
    from pymongo import MongoClient
    import uvicorn
    from core import game_console_build as forge
    from core.game_learning import GameLearningWorkspace
    from routes import game_console_build, game_learning, gameforge_auth, skeleton_gameforge
    from skeleton.forge.source_manifest import source_manifest

    output = Path(args.output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Evidence must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads(Path(args.mongo_config).read_text())
    database_name = config["database_prefix"][:16] + "_forge_browser_" + uuid4().hex[:20]
    token, other_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    account = {"email": "forge-browser@example.test", "tenant_id": "forge-browser", "role": "editor"}
    other_account = {"email": "other-forge-browser@example.test", "tenant_id": "other-forge-browser", "role": "editor"}
    mongo, sync = AsyncIOMotorClient(config["uri"]), MongoClient(config["uri"])
    db = mongo[database_name]
    owners = []
    counts = {"project_posts": 0, "build_posts": 0, "compiler_dispatches": 0,
              "artifact_gets": 0, "history_gets": 0, "admissions": 0}
    counting_lock = threading.Lock()

    def authority():
        owner = GameLearningWorkspace(db)

        async def test_only_admission(scope, resource, write_id, size):
            counts["admissions"] += 1
            return {"storage_bytes": size, "fixture": "governed-storage-admission-only"}

        owner._admit = test_only_admission
        forge.workspace = owner
        skeleton_gameforge.workspace = owner
        game_learning.workspace = owner
        game_console_build.workspace = owner
        forge.register_forge_source_handler()
        owners.append(owner)
        return owner

    current_owner = authority()
    original_compile = forge._compile_forge_source

    def observed_compile(request):
        with counting_lock:
            counts["compiler_dispatches"] += 1
        return original_compile(request)

    forge._compile_forge_source = observed_compile

    @asynccontextmanager
    async def lifespan(app):
        app.state.execution_loop = asyncio.get_running_loop()
        yield
        tasks = []
        for owner in owners:
            tasks.extend(owner._tasks.values())
            for event in owner._cancel.values():
                event.set()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[args.web], allow_methods=["*"], allow_headers=["*"],
                       expose_headers=["Content-Length", "Content-Disposition", "ETag"])
    app.include_router(skeleton_gameforge.router)
    app.include_router(game_console_build.router, prefix="/api")

    def principal(authorization: str | None = Header(default=None)):
        return account if authorization == "Bearer " + token else other_account if authorization == "Bearer " + other_token else None

    app.dependency_overrides[gameforge_auth.get_current_user] = principal

    @app.get("/api/auth/me")
    def me(authorization: str | None = Header(default=None)):
        current = principal(authorization)
        return {"authenticated": current is not None, "enforced": True,
                "role": current["role"] if current else "anonymous", "user": current}

    prefix = "/api/skeleton/projects"

    @app.middleware("http")
    async def observe(request, call_next):
        path = request.url.path
        if request.method == "POST" and path == prefix:
            counts["project_posts"] += 1
        if request.method == "POST" and path.startswith(prefix + "/") and path.endswith("/builds"):
            counts["build_posts"] += 1
        if request.method == "GET" and path.startswith(prefix + "/") and path.endswith("/builds"):
            counts["history_gets"] += 1
        if request.method == "GET" and "/build-artifacts/" in path:
            counts["artifact_gets"] += 1
        return await call_next(request)

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="error"))
    worker = threading.Thread(target=server.run, daemon=True)
    worker.start()
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(.1)
    assert server.started
    api = "http://127.0.0.1:" + str(args.port)
    report = {
        "schema": "skeleton.forge.source-browser.v1", "checks": [],
        "fixtures": ["authenticated account lookup", "governed storage-admission response"],
        "mongo": "actual disposable authenticated Mongo", "source_compiler_executed": False,
        "provider_model_executed": False, "godot_process_executed": False, "native_binary_qualified": False,
        "python": sys.version.split()[0], "platform": platform.platform(),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "tracked_tree_dirty": bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT)),
        "sources": {}, "page_errors": [], "external_browser_requests": [],
    }
    for path in (
        "backend/core/game_learning.py", "backend/core/game_console_build.py", "backend/routes/skeleton_gameforge.py",
        "frontend/src/skeletonForge/components/DurableForgePanel.tsx", "frontend/src/skeletonForge/durableForgeClient.ts",
        "frontend/src/skeletonForge/components/ForgeCockpitScreen.tsx", "frontend/src/skeletonForge/components/ForgeCockpitView.tsx",
    ):
        report["sources"][path] = sha256((ROOT / path).read_bytes()).hexdigest()
    started = time.monotonic()
    browser = None
    page = None

    def passed(message):
        report["checks"].append(message)
        print(json.dumps({"check": message, "elapsed_seconds": round(time.monotonic() - started, 2)}), flush=True)

    async def completed(job_id):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            row = sync[database_name].game_learning_jobs.find_one({"_id": job_id})
            if row and row["status"] in {"completed", "failed", "interrupted", "cancelled"}:
                assert row["status"] == "completed", row.get("error")
                return row
            await asyncio.sleep(.05)
        raise AssertionError("Source build did not reach completion within the check deadline")

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path="/usr/bin/chromium", headless=True,
                                                       args=["--no-sandbox", "--disable-dev-shm-usage"])
            report["browser"] = browser.version
            context = await browser.new_context(viewport={"width": 1440, "height": 1050}, accept_downloads=True)
            await context.add_init_script("localStorage.setItem('gameforge_auth_token'," + json.dumps(token) + ");")
            page = await context.new_page()
            page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
            lost_ack = {"armed": False, "project": False}
            project_requests = []

            async def transport(route):
                parsed = urlsplit(route.request.url)
                if parsed.path.startswith("/api/"):
                    target = api + parsed.path + (("?" + parsed.query) if parsed.query else "")
                    if route.request.method == "POST" and parsed.path == prefix:
                        project_requests.append(route.request.post_data_json)
                    if lost_ack["project"] and route.request.method == "POST" and parsed.path == prefix:
                        lost_ack["project"] = False
                        response = await route.fetch(url=target)
                        if response.status == 200:
                            await route.abort("failed")
                        else:
                            report.setdefault("transport_failures", []).append({"path": parsed.path, "status": response.status, "body": (await response.text())[:400]})
                            await route.fulfill(response=response)
                    elif lost_ack["armed"] and route.request.method == "POST" and parsed.path.endswith("/builds"):
                        lost_ack["armed"] = False
                        response = await route.fetch(url=target)
                        if response.status == 200:
                            await route.abort("failed")
                        else:
                            report.setdefault("transport_failures", []).append({"path": parsed.path, "status": response.status, "body": (await response.text())[:400]})
                            await route.fulfill(response=response)
                    else:
                        await route.continue_(url=target)
                elif parsed.hostname not in {"localhost", "127.0.0.1"}:
                    report["external_browser_requests"].append(parsed.hostname)
                    await route.abort()
                else:
                    await route.continue_()

            await context.route("**/*", transport)
            await page.goto(args.web + "/skeleton-forge?tab=build", wait_until="domcontentloaded", timeout=120000)
            await page.get_by_test_id("q-vision-input").wait_for(timeout=120000)
            vision = "An original extraction game: recover lantern fuel, avoid pressure and escape through a safe gate."
            await page.get_by_test_id("q-vision-input").fill(vision)
            await page.get_by_test_id("q-step-options").click()
            await page.get_by_test_id("q-arch-extraction").click()
            await page.get_by_test_id("q-playable-on").click()
            await page.get_by_test_id("q-playable-mode-extraction").click()
            await page.get_by_test_id("q-playable-launch").click()
            await page.get_by_test_id("cockpit-tab-run").click()
            await page.get_by_test_id("forge-project-name").fill("Lantern Extraction Laboratory")
            lost_ack["project"] = True
            await page.get_by_test_id("forge-project-create").click()
            await page.get_by_test_id("forge-project-create").filter(has_text="Recover original project creation").wait_for(timeout=30000)
            await expect(page.get_by_test_id("forge-project-create")).to_be_enabled(timeout=15000)
            await page.get_by_test_id("forge-project-name").fill("Next unsubmitted source concept")
            await page.get_by_test_id("forge-project-create").click()
            await page.get_by_test_id("forge-library-notice").filter(has_text="Original source project saved").wait_for(timeout=30000)
            project = sync[database_name].game_learning_projects.find_one({"console_id": "forge:godot"})
            project_id = project["project_id"]
            assert project["version"] == 1 and project["files"] == [] and project["_source_only_draft"]
            assert project["name"] == "Lantern Extraction Laboratory"
            assert sync[database_name].game_learning_projects.count_documents({}) == 1
            assert len(project_requests) == 2 and project_requests[0] == project_requests[1]
            assert await page.get_by_test_id("forge-project-name").input_value() == "Next unsubmitted source concept"
            passed("Lost project-creation acknowledgement retries the exact original identity and name, preserves the edited draft name and creates one actual Mongo project")

            await page.get_by_test_id("forge-source-scope").click()
            lost_ack["armed"] = True
            await page.get_by_test_id("forge-saved-build-start").click()
            await page.get_by_test_id("forge-library-notice").filter(has_text="Delivery is uncertain").wait_for(timeout=30000)
            assert counts["build_posts"] == 1
            original = sync[database_name].game_learning_jobs.find_one({"project_id": project_id})
            assert original is not None and original["request"]["run"]["vision"] == vision
            assert original["request"]["run"]["playtest"] == "off"
            assert original["request"]["run"]["playable_archetype"] == "extraction"
            original = await completed(original["job_id"])
            assert counts["build_posts"] == 1 and counts["compiler_dispatches"] == 1
            assert sync[database_name].game_learning_jobs.count_documents({"project_id": project_id}) == 1
            passed("Lost HTTP acknowledgement leaves exactly one admitted request and one real compiler dispatch")

            headers = {"Authorization": "Bearer " + token}
            for index in range(24):
                request = {**original["request"], "idempotency_key": "history-browser-" + uuid4().hex}
                response = await page.request.post(api + prefix + "/" + project_id + "/builds", data=request, headers=headers, timeout=30000)
                assert response.status == 200
                await completed((await response.json())["job"]["job_id"])
                if index % 8 == 7:
                    print(json.dumps({"phase": "actual-history-builds", "completed": index + 1}), flush=True)
            assert counts["compiler_dispatches"] == 25 and counts["build_posts"] == 25
            await page.get_by_test_id("forge-build-check").click()
            await page.get_by_test_id("forge-library-notice").filter(has_text="The original request is not yet visible").wait_for(timeout=30000)
            assert await page.get_by_test_id("forge-saved-job-" + original["job_id"]).count() == 0
            await page.get_by_test_id("forge-build-history-more").click()
            await page.get_by_test_id("forge-library-notice").filter(has_text="The original saved submission was recovered").wait_for(timeout=30000)
            await page.get_by_test_id("forge-saved-status").filter(has_text="completed").wait_for(timeout=30000)
            await expect(page.get_by_test_id("forge-saved-build-start")).to_be_enabled(timeout=15000)
            assert counts["history_gets"] >= 1 and counts["compiler_dispatches"] == 25
            assert sync[database_name].game_learning_jobs.count_documents({"request.idempotency_key": original["request"]["idempotency_key"]}) == 1
            passed("Loading older history recovers an uncertain original behind 24 genuine builds, clears its pending lock and never resubmits it")

            async def select_original():
                row = page.get_by_test_id("forge-saved-job-" + original["job_id"])
                # Opening the project replaces the previous complete history
                # asynchronously. Wait for its new first-page boundary before
                # inspecting rows from the previous view.
                more = page.get_by_test_id("forge-build-history-more")
                await expect(more).to_be_enabled(timeout=30000)
                await more.click()
                await row.wait_for(timeout=30000)
                await expect(row).to_be_enabled(timeout=15000)
                await row.click()
                await page.get_by_test_id("forge-recovered-result").wait_for(timeout=30000)

            async with page.expect_download() as downloading:
                await page.get_by_test_id("forge-saved-download").click()
            destination = output / "original-godot-source.zip"
            await (await downloading.value).save_as(destination)
            artifact = original["result"]["artifacts"][0]
            archive_bytes = destination.read_bytes()
            assert len(archive_bytes) == artifact["bytes"] and sha256(archive_bytes).hexdigest() == artifact["digest"]
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                files = {name: archive.read(name).decode("utf-8") for name in archive.namelist()}
            assert source_manifest(files) == original["result"]["source_manifest"]
            assert "project.godot" in files and original["result"]["build"]["playable_portal"]["sealed"] is True
            for private_path in (prefix + "/" + project_id, prefix + "/" + project_id + "/builds",
                                 prefix + "/" + project_id + "/builds/" + original["job_id"], "/api" + artifact["download_path"]):
                private_response = await page.request.get(api + private_path, headers=headers)
                assert private_response.status == 200
                assert private_response.headers.get("cache-control") == "private, no-store"
            report["source_zip"] = {"bytes": len(archive_bytes), "sha256": artifact["digest"], "file_count": len(files)}
            passed("Actual browser download matches the immutable ZIP digest and exact native extraction source manifest")
            await page.get_by_test_id("forge-saved-status").scroll_into_view_if_needed()
            await page.screenshot(path=str(output / "forge-source-desktop.png"))

            await page.reload(wait_until="domcontentloaded")
            await page.get_by_test_id("cockpit-tab-run").wait_for(timeout=60000)
            await page.get_by_test_id("cockpit-tab-run").click()
            await page.get_by_test_id("forge-project-" + project_id).wait_for(timeout=60000)
            await page.get_by_test_id("forge-project-" + project_id).click()
            await select_original()
            assert vision in await page.get_by_test_id("forge-saved-builds").inner_text()
            assert counts["compiler_dispatches"] == 25
            passed("Reload and explicit reopen restore the saved brief and complete result without regenerating source")

            assert not current_owner._tasks
            current_owner = authority()
            await page.get_by_test_id("forge-library-refresh").click()
            await page.get_by_test_id("forge-project-" + project_id).click()
            await select_original()
            async with page.expect_download() as downloading:
                await page.get_by_test_id("forge-saved-download").click()
            recovered_path = output / "reopened-godot-source.zip"
            await (await downloading.value).save_as(recovered_path)
            assert recovered_path.read_bytes() == archive_bytes and counts["compiler_dispatches"] == 25
            passed("A fresh backend workspace restores exact Mongo-held source bytes with no process-local build state")

            other_headers = {"Authorization": "Bearer " + other_token}
            for path in (prefix + "/" + project_id, prefix + "/" + project_id + "/builds/" + original["job_id"], "/api" + artifact["download_path"]):
                denied = await page.request.get(api + path, headers=other_headers)
                assert denied.status == 404
            anonymous = await page.request.get(api + prefix)
            assert anonymous.status == 401
            other_project = await page.request.post(api + prefix, data={"name": "Other account", "idempotency_key": uuid4().hex}, headers=other_headers)
            assert other_project.status == 200
            other_project_id = (await other_project.json())["project"]["project_id"]
            foreign_cursor = await page.request.get(api + prefix + "/" + other_project_id + "/builds?before=" + original["job_id"], headers=other_headers)
            assert foreign_cursor.status == 404
            passed("Actual HTTP owner and anonymous gates deny private projects, receipts, archives and foreign pagination cursors")

            await page.set_viewport_size({"width": 390, "height": 844})
            await page.get_by_test_id("forge-saved-status").scroll_into_view_if_needed()
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
            await page.screenshot(path=str(output / "forge-source-mobile.png"))
            assert not report["page_errors"], report["page_errors"]
            passed("Desktop and 390px mobile saved-build controls render without horizontal overflow or page errors")
            await browser.close()
            browser = None
        report.update(status="passed", observed=counts, elapsed_seconds=round(time.monotonic() - started, 3))
    except BaseException as error:
        safe = (type(error).__name__ + ": " + str(error)).replace(config["uri"], "[private Mongo URI]")
        report.update(status="failed", error=safe.replace(token, "[private token]").replace(other_token, "[private token]"), observed=counts)
        if page is not None:
            try:
                await page.screenshot(path=str(output / "forge-source-failure.png"))
            except Exception:
                pass
    finally:
        report["source_compiler_executed"] = counts["compiler_dispatches"] > 0
        if browser is not None:
            await browser.close()
        for path, digest in report["sources"].items():
            if sha256((ROOT / path).read_bytes()).hexdigest() != digest:
                report.setdefault("source_changed_during_run", []).append(path)
        if report.get("source_changed_during_run"):
            report["status"] = "failed"
            report["error"] = "Critical product source changed during qualification; rerun against a frozen tree"
        (output / "forge-source-browser-report.json").write_text(json.dumps(report, indent=2) + "\n")
        server.should_exit = True
        worker.join(timeout=30)
        forge._compile_forge_source = original_compile
        if not worker.is_alive():
            sync.drop_database(database_name)
        sync.close()
        mongo.close()
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "report": str(output / "forge-source-browser-report.json")}))
    if report["status"] != "passed":
        raise RuntimeError(report["error"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", default="http://localhost:3000")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--mongo-config", default="/workspace/verticals-runtime/mongo.json")
    parser.add_argument("--output", required=True)
    asyncio.run(qualify(parser.parse_args()))
