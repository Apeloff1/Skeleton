#!/usr/bin/env python3
"""Exercise typed Forge controls against actual Expo, HTTP and disposable Mongo.

Only principal lookup and governed storage admission are declared fixtures.
Project creation, authoring previews, source revisions and conflicts use their
canonical owners. This does not qualify a model, native engine or production
identity/admission. Run browser checks serially against the shared Expo server.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
SOURCES = (
    "frontend/src/features/Jeeves/GameLearningWorkspace.tsx",
    "frontend/src/features/Jeeves/GameFrontierAuthoringPanel.tsx",
    "frontend/src/features/Jeeves/forgeParameters/ForgeParameterEditor.tsx",
    "frontend/src/features/Jeeves/forgeParameters/forgeParameterEditor.ts",
    "frontend/src/product/gameFrontierAuthoringClient.ts",
    "frontend/src/product/gameLearningClient.ts",
    "frontend/src/auth/gameforgeAuth.ts",
    "backend/core/game_learning.py", "backend/core/game_frontier_authoring.py",
    "backend/routes/game_learning.py", "backend/routes/game_frontier_authoring.py",
    "backend/routes/gameforge_auth.py", "backend/routes/health.py",
    "skeleton/forge/game_frontier_studio_authoring.py",
    "skeleton/forge/game_frontier_studio_document.py",
)


def fingerprints():
    return {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}


async def qualify(args):
    import httpx
    from fastapi import FastAPI, Header
    from fastapi.middleware.cors import CORSMiddleware
    from motor.motor_asyncio import AsyncIOMotorClient
    from pymongo import MongoClient
    import uvicorn
    from core import game_frontier_authoring, game_studio_health
    from core.game_learning import GameLearningWorkspace
    from routes import game_frontier_authoring as authoring_routes
    from routes import game_learning, gameforge_auth, health
    from routes import game_studio_health as health_routes

    output = Path(args.output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Evidence must be outside the repository")
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads(Path(args.mongo_config).read_text())
    prefix = re.sub(r"[^a-zA-Z0-9_]", "_", config["database_prefix"])[:16]
    database_name = prefix + "_forge_params_" + uuid4().hex[:16]
    token, other_token, viewer_token = (secrets.token_urlsafe(32) for _ in range(3))
    account = {"email": "forge-parameters@example.test", "tenant_id": "forge-parameters", "role": "editor"}
    other = {"email": "other-forge-parameters@example.test", "tenant_id": "other-parameters", "role": "editor"}
    viewer = {**account, "role": "viewer"}
    mongo = AsyncIOMotorClient(config["uri"], serverSelectionTimeoutMS=5000)
    sync = MongoClient(config["uri"], serverSelectionTimeoutMS=5000)
    owner = GameLearningWorkspace(mongo[database_name])
    counts = {"project_create_requests": 0, "preview_requests": 0, "commit_requests": 0,
              "committed_revisions": 0, "successful_previews": 0, "admissions": 0,
              "inspection_requests": 0}

    async def test_only_admission(scope, resource, write_id, size):
        counts["admissions"] += 1
        return {"storage_bytes": size, "fixture": "governed-storage-admission-only"}

    owner._admit = test_only_admission
    game_learning.workspace = owner
    game_frontier_authoring.workspace = owner
    game_studio_health.workspace = owner

    @asynccontextmanager
    async def lifespan(app):
        app.state.execution_loop = asyncio.get_running_loop()
        yield
        tasks = list(owner._tasks.values())
        for event in owner._cancel.values():
            event.set()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[args.web], allow_methods=["*"], allow_headers=["*"])
    for router in (game_learning.router, authoring_routes.router, health_routes.router, health.router):
        app.include_router(router, prefix="/api")

    def principal(authorization: str | None = Header(default=None)):
        return {"Bearer " + token: account, "Bearer " + other_token: other,
                "Bearer " + viewer_token: viewer}.get(authorization)

    app.dependency_overrides[gameforge_auth.get_current_user] = principal

    @app.get("/api/auth/me")
    def me(authorization: str | None = Header(default=None)):
        current = principal(authorization)
        return {"authenticated": current is not None, "enforced": True,
                "role": current["role"] if current else "anonymous", "user": current}

    @app.middleware("http")
    async def observe(request, call_next):
        path = request.url.path
        if request.method == "POST" and path == "/api/game-learning/projects":
            counts["project_create_requests"] += 1
        if request.method == "POST" and path.endswith("/edits/preview"):
            counts["preview_requests"] += 1
        if request.method == "PATCH" and path.endswith("/edits"):
            counts["commit_requests"] += 1
        if request.method == "GET" and path.startswith("/api/game-frontier-authoring/projects/"):
            counts["inspection_requests"] += 1
        response = await call_next(request)
        if response.status_code == 200 and request.method == "PATCH" and path.endswith("/edits"):
            counts["committed_revisions"] += 1
        if response.status_code == 200 and request.method == "POST" and path.endswith("/edits/preview"):
            counts["successful_previews"] += 1
        return response

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="error"))
    worker = threading.Thread(target=server.run, daemon=True)
    api = "http://127.0.0.1:" + str(args.port)
    report = {
        "schema": "skeleton.forge.parameters-browser.v1", "status": "running", "checks": [],
        "mode": "api_preflight" if args.preflight_only else "actual_expo_browser",
        "fixtures": ["authenticated principal lookup", "governed storage-admission response"],
        "mongo": "actual disposable authenticated Mongo", "provider_model_executed": False,
        "godot_process_executed": False, "native_binary_qualified": False,
        "observed_at": datetime.now(timezone.utc).isoformat(), "python": sys.version.split()[0],
        "platform": platform.platform(), "head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "tracked_tree_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT)),
        "sources": fingerprints(), "harness_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "page_errors": [], "external_browser_requests": [], "browser_mutations": [],
        "browser_api_responses": [], "console_errors": [],
        "transport": "Actual browser API requests forwarded to the isolated canonical FastAPI server; no API response fixtures",
    }
    started = time.monotonic()
    browser, context, page = None, None, None

    def record(message):
        report["checks"].append(message)
        (output / "forge-parameters-browser-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"check": message, "seconds": round(time.monotonic() - started, 2)}), flush=True)

    async def data(client, method, path, body=None, expected=200, bearer=None):
        response = await client.request(method, path, json=body,
                                        headers={"Authorization": "Bearer " + (bearer or token)})
        assert response.status_code == expected, {"path": path, "status": response.status_code,
                                                  "body": response.text[:600]}
        return response.json()

    try:
        sync.admin.command("ping")
        worker.start()
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(.1)
        assert server.started, "The isolated canonical API did not start"
        async with httpx.AsyncClient(base_url=api, timeout=30) as client:
            created = await data(client, "POST", "/api/game-learning/projects", {
                "name": "Lantern Forge Workshop", "console_id": "studio:economy", "idempotency_key": "browser-project"})
            project_id = created["project"]["project_id"]
            project_path = "/api/game-learning/projects/" + project_id
            studio_path = "/api/game-frontier-authoring/projects/" + project_id
            initial = await data(client, "GET", studio_path)
            assert len(initial["action_catalog"]) == 500
            seeded = await data(client, "PATCH", studio_path + "/edits", {
                "expected_version": initial["expected_version"], "expected_sha256": initial["source_sha256"],
                "idempotency_key": "browser-seed", "steps": [
                    {"action": "tile_set", "parameters": {"layer": "ground", "x": 0, "y": 0, "tile": 1}}]})
            source = (await data(client, "GET", project_path))["project"]
            base_version = source["version"]
            assert seeded["persisted"] is True and base_version == 2
            source_before_preview = source["files"]
            record("Canonical HTTP creates an original studio project and persists a real authored source revision in Mongo")

            denied_body = {"expected_version": base_version, "expected_sha256": seeded["source_sha256"],
                           "idempotency_key": "denied", "steps": [
                               {"action": "tile_set", "parameters": {"layer": "ground", "x": 2, "y": 3, "tile": 2}}]}
            for path in (project_path, studio_path):
                await data(client, "GET", path, expected=404, bearer=other_token)
                anonymous = await client.get(path)
                assert anonymous.status_code == 401
            await data(client, "PATCH", studio_path + "/edits", denied_body, expected=403, bearer=viewer_token)
            assert (await data(client, "GET", project_path))["project"]["version"] == base_version
            record("Actual HTTP owner, anonymous and viewer gates protect private source and forbid unauthorized changes")
            if args.preflight_only:
                report["status"] = "passed"
                return report

            from playwright.async_api import async_playwright, expect
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(executable_path=args.chromium, headless=True,
                                                           args=["--no-sandbox", "--disable-dev-shm-usage"])
                report["browser"] = browser.version
                context = await browser.new_context(viewport={"width": 1440, "height": 1050})
                await context.add_init_script("localStorage.setItem('gameforge_auth_token'," + json.dumps(token) + ");")
                page = await context.new_page()
                page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
                page.on("console", lambda message: report["console_errors"].append(message.text[:1000])
                        if message.type == "error" and len(report["console_errors"]) < 32 else None)

                async def transport(route):
                    request = route.request
                    parsed = urlsplit(request.url)
                    if parsed.path.startswith("/api/"):
                        if request.method in {"POST", "PATCH"} and "/edits" in parsed.path:
                            report["browser_mutations"].append({"method": request.method, "path": parsed.path,
                                                               "body": request.post_data_json})
                        target = api + parsed.path + ("?" + parsed.query if parsed.query else "")
                        response = await route.fetch(url=target)
                        if len(report["browser_api_responses"]) < 256:
                            report["browser_api_responses"].append({"method": request.method,
                                                                    "path": parsed.path, "status": response.status})
                        await route.fulfill(response=response)
                    elif parsed.hostname in {urlsplit(args.web).hostname, "localhost", "127.0.0.1", "::1"}:
                        await route.continue_()
                    else:
                        report["external_browser_requests"].append(parsed.scheme + "://" + (parsed.hostname or "") + parsed.path)
                        await route.abort("blockedbyclient")

                await page.route("**/*", transport)

                async def open_editor():
                    try:
                        navigation = await page.goto(args.web + "/game-learning", wait_until="domcontentloaded", timeout=120000)
                        assert navigation is not None and navigation.status == 200, "Expo did not serve the actual game-learning route"
                        opener = page.get_by_role("button", name="Open Lantern Forge Workshop", exact=True)
                        await opener.click(timeout=60000)
                        await expect(page.get_by_test_id("forge-parameter-editor")).to_be_visible(timeout=60000)
                        await expect(page.get_by_label('Parameters["x"]', exact=True)).to_have_value("0", timeout=30000)
                    except Exception:
                        await page.screenshot(path=str(output / "startup-failure.png"))
                        (output / "startup-failure-dom.txt").write_text((await page.locator("body").inner_text())[:20000])
                        raise

                await open_editor()
                panel = page.get_by_test_id("forge-authoring-panel")
                queue = panel.get_by_role("button", name="Queue editor action", exact=True)
                advanced = page.get_by_test_id("forge-parameters-advanced")
                guided = page.get_by_test_id("forge-parameters-guided")
                raw = page.get_by_test_id("forge-parameters-json")
                await advanced.click()
                original = '{ "layer": "ground", "x": 0, "y": 0, "tile": 1, "custom": {"note": "  preserve  "} }'
                await raw.fill(original)
                await guided.click()
                await page.get_by_label('Parameters["x"]', exact=True).fill("2")
                await advanced.click()
                assert await raw.input_value() == original.replace('"x": 0', '"x": 2')
                broken = '{"layer":"ground","x":'
                await raw.fill(broken)
                await expect(queue).to_be_disabled()
                assert await raw.input_value() == broken
                await raw.fill('{"layer":"ground","x":0,"y":0,"tile":1}')
                await guided.click()
                number = page.get_by_label('Parameters["x"]', exact=True)
                await number.fill("-")
                await expect(queue).to_be_disabled()
                await expect(number).to_have_value("-")
                await page.get_by_test_id("forge-param-field-x-restore").click()
                await expect(number).to_have_value("0")
                await expect(queue).to_be_enabled()
                record("Guided edits preserve unknown JSON bytes; malformed JSON and unfinished numbers remain repairable and cannot queue")

                await number.fill("2")
                await page.get_by_label('Parameters["y"]', exact=True).fill("3")
                await page.get_by_label('Parameters["tile"]', exact=True).fill("2")
                await queue.click()
                await expect(panel.get_by_text("1 queued changes", exact=True)).to_be_visible()
                async with page.expect_response(lambda response: response.request.method == "POST"
                                                and urlsplit(response.url).path == studio_path + "/edits/preview") as pending:
                    await panel.get_by_role("button", name="Preview changes", exact=True).click()
                preview_response = await pending.value
                assert preview_response.status == 200
                preview = await preview_response.json()
                assert preview["persisted"] is False and preview["candidate_sha256"] != preview["source_sha256"]
                unchanged = (await data(client, "GET", project_path))["project"]
                assert unchanged["version"] == base_version and unchanged["files"] == source_before_preview
                record("The typed tile action reaches the real preview API and changes its candidate without persisting a revision")
                async with page.expect_response(lambda response: response.request.method == "PATCH"
                                                and urlsplit(response.url).path == studio_path + "/edits") as pending:
                    await panel.get_by_role("button", name="Save source changes", exact=True).click()
                committed = await pending.value
                assert committed.status == 200
                await expect(panel.get_by_text("Real game source committed to the project revision history.", exact=True)).to_be_visible()
                saved = (await data(client, "GET", project_path))["project"]
                assert saved["version"] == base_version + 1
                tiles = await data(client, "POST", studio_path + "/tiles/copy", {"layer": "ground", "x": 2, "y": 3, "width": 1, "height": 1})
                assert tiles["tiles"] == [2]
                actual_steps = report["browser_mutations"][-1]["body"]["steps"]
                assert actual_steps == [{"action": "tile_set", "parameters": {"layer": "ground", "x": 2, "y": 3, "tile": 2}}]
                record("Saving commits the exact typed operation through canonical CAS and restores the actual painted tile from Mongo")

                await panel.get_by_label("Search 500 core game editor tools", exact=True).fill("terrain_bezier_road")
                await panel.get_by_role("button", name="terrain bezier road", exact=True).click()
                first = page.get_by_label('Parameters["control_points"][0][0]', exact=True)
                await first.fill("1")
                await page.get_by_test_id("forge-param-field-control%5Fpoints/0-duplicate").click()
                await advanced.click()
                points = json.loads(await raw.input_value())["control_points"]
                assert points == [[1, 0], [6, 8], [11, 11], [1, 0]]
                await guided.click()
                await page.get_by_test_id("forge-param-field-control%5Fpoints/3-remove").click()
                await advanced.click()
                assert json.loads(await raw.input_value())["control_points"] == [[1, 0], [6, 8], [11, 11]]
                await guided.click()
                record("Nested control-point numbers and array duplication/removal retain their types and exact unedited values")

                await panel.get_by_label("Search 500 core game editor tools", exact=True).fill("tile_set")
                await panel.get_by_role("button", name="tile set", exact=True).click()
                await page.get_by_label('Parameters["x"]', exact=True).fill("4")
                await page.get_by_label('Parameters["y"]', exact=True).fill("5")
                await queue.click()
                head = await data(client, "GET", studio_path)
                await data(client, "PATCH", studio_path + "/edits", {
                    "expected_version": head["expected_version"], "expected_sha256": head["source_sha256"],
                    "idempotency_key": "concurrent-editor", "steps": [
                        {"action": "tile_set", "parameters": {"layer": "ground", "x": 0, "y": 1, "tile": 1}}]})
                async with page.expect_response(lambda response: response.request.method == "PATCH"
                                                and urlsplit(response.url).path == studio_path + "/edits") as pending:
                    await panel.get_by_role("button", name="Save source changes", exact=True).click()
                assert (await pending.value).status == 409
                await expect(panel.get_by_text("1 queued changes", exact=True)).to_be_visible()
                await expect(page.get_by_label('Parameters["x"]', exact=True)).to_have_value("4")
                untouched = await data(client, "POST", studio_path + "/tiles/copy", {"layer": "ground", "x": 4, "y": 5, "width": 1, "height": 1})
                assert untouched["tiles"] == [0]
                record("A real concurrent source revision returns 409 and preserves the queued typed action without overwriting newer source")

                await open_editor()
                tile = panel.get_by_role("button", name="Paint map coordinate 2,3", exact=True)
                await expect(tile).to_have_css("background-color", "rgb(64, 108, 153)")
                editor = page.get_by_test_id("forge-parameter-editor")
                await editor.evaluate("node => node.scrollIntoView({block:'start'})")
                await page.screenshot(path=str(output / "forge-parameters-desktop.png"))
                await page.set_viewport_size({"width": 390, "height": 844})
                await editor.evaluate("node => node.scrollIntoView({block:'start'})")
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                assert await editor.evaluate("node => node.getBoundingClientRect().right <= innerWidth + 1")
                await page.screenshot(path=str(output / "forge-parameters-mobile.png"))
                assert not report["page_errors"], report["page_errors"]
                assert not report["external_browser_requests"], report["external_browser_requests"]
                record("Reload restores the saved painted map; desktop and 390px mobile typed controls render without overflow or page errors")
                await context.close()
                context = None
                await browser.close()
                browser = None
        assert fingerprints() == report["sources"], "Product source changed during qualification"
        report["status"] = "passed"
    except Exception as error:
        message = str(error)
        for private in (config["uri"], token, other_token, viewer_token):
            message = message.replace(private, "<private>")
        report["status"] = "failed"
        report["failure"] = {"type": type(error).__name__, "message": message[:2000]}
        if page is not None:
            try:
                await page.screenshot(path=str(output / "failure.png"))
                (output / "failure-dom.txt").write_text((await page.locator("body").inner_text())[:20000])
            except Exception:
                pass
    finally:
        if browser is not None and browser.is_connected():
            if context is not None:
                await context.close()
            await browser.close()
        server.should_exit = True
        if worker.ident is not None:
            await asyncio.to_thread(worker.join, 10)
        try:
            sync.drop_database(database_name)
        except Exception as error:
            report["cleanup_failure"] = type(error).__name__
            report["status"] = "failed"
        mongo.close()
        sync.close()
        report["observed"] = counts
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (output / "forge-parameters-browser-report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", default="http://localhost:3000", help="Already-running Expo web origin")
    parser.add_argument("--port", type=int, default=8775, help="Free numeric-loopback port for the isolated canonical API")
    parser.add_argument("--mongo-config", required=True, help="Private JSON containing uri and database_prefix; never printed")
    parser.add_argument("--output", required=True, help="New evidence directory outside the repository")
    parser.add_argument("--chromium", default="/usr/bin/chromium")
    parser.add_argument("--preflight-only", action="store_true", help="Run real HTTP/Mongo setup and owner gates without a browser claim")
    args = parser.parse_args()
    parsed = urlsplit(args.web)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username:
        parser.error("--web must be an HTTP origin without a path, query or credentials")
    args.web = args.web.rstrip("/")
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be in 1024..65535")
    report = asyncio.run(qualify(args))
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]),
                      "mode": report["mode"], "output": str(Path(args.output).resolve())}), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
