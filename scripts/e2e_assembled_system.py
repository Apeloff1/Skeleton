#!/usr/bin/env python3
"""Run disposable Mongo/engine/backend and real browser journeys at a commit.

Only loopback fixture services and a small trained native model are used.
This proves assembly, authority, persistence and UI wiring, not model quality,
installed device readiness or live-provider qualification.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import partial
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import zipfile

from e2e_evidence import Recorder, redactor

ROOT = Path(__file__).resolve().parents[1]
JOURNEYS = (
    "assembled-startup", "assembled-native-api", "assembled-conversation-lineage",
    "assembled-project-evidence", "assembled-browser-desktop", "assembled-browser-mobile",
    "assembled-restart-replay", "assembled-conversation-deletion", "assembled-engine-outage",
)


def export_digest(directory):
    """Bind every served asset and its relative path."""
    entries = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("web export contains a symbolic link")
        if path.is_file():
            entries.append([path.relative_to(directory).as_posix(),
                            hashlib.sha256(path.read_bytes()).hexdigest()])
    return hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()


class Campaign:
    def __init__(self, args):
        self.args = args
        self.output = args.output_dir.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if subprocess.run(["git", "diff", "HEAD", "--quiet"], cwd=ROOT).returncode:
            raise ValueError("commit the candidate before running exact-head assembled evidence")
        os.environ["E2E_HEAD_SHA"] = self.head
        self.scrub = redactor()
        self.rec = Recorder(self.output, self.scrub)
        self.temp = tempfile.TemporaryDirectory(prefix="skeleton-e2e-")
        self.data = Path(self.temp.name)
        self.source = self.data / "source"
        self.processes = {}
        self.process_logs = {}
        self.readers = []
        self.secrets = []
        self.forced = []
        self.browser_events = []
        self.web = None
        self.client = None
        self.mongo = None
        self.token = ""
        self.web_export = None
        self.shutdowns = []
        self.expected_journeys = list(JOURNEYS)
        if args.nginx:
            self.expected_journeys.append("assembled-same-origin-ingress")
        if args.audit_product_routes or args.audit_all_routes or args.audit_route:
            self.expected_journeys.append("assembled-product-routes")
        self.frontend_backend_url = f"http://127.0.0.1:{args.web_port if args.nginx else args.backend_port}"
        self.frontend_engine_url = f"http://127.0.0.1:{args.web_port if args.nginx else args.engine_port}"

    def safe(self, text):
        value = str(text)
        for secret in self.secrets:
            value = value.replace(secret, "[REDACTED TEST CREDENTIAL]")
        return self.scrub(value)

    @contextmanager
    def journey(self, name):
        start = time.monotonic()
        self.rec.emit("journey.started", suite=name)
        passed = False
        try:
            yield
            passed = True
        except Exception as exc:
            self.rec.issue(suite=name, phase="execute", kind=type(exc).__name__,
                           message=self.safe(str(exc))[:1200], evidence="events.jsonl")
            raise
        finally:
            self.rec.suites.append({"id": name, "status": "passed" if passed else "failed",
                                    "duration_seconds": round(time.monotonic() - start, 3)})
            self.rec.emit("journey.finished", suite=name, status="passed" if passed else "failed")

    def start(self, name, command, env, cwd=None):
        logfile = self.output / (name + ".log")
        offset = logfile.stat().st_size if logfile.exists() else 0
        process = subprocess.Popen(command, cwd=cwd or self.source, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL)
        self.processes[name] = process

        def capture():
            with logfile.open("a", encoding="utf-8") as sink:
                assert process.stdout is not None
                while chunk := process.stdout.readline(4096):
                    line = self.safe(chunk.decode("utf-8", "replace").rstrip())[:4096]
                    sink.write(datetime.now(timezone.utc).isoformat() + " " + line + "\n")
                    sink.flush()

        reader = threading.Thread(target=capture, daemon=True)
        reader.start()
        self.readers.append(reader)
        self.process_logs[name] = (offset, reader)
        return process

    def stop(self, name):
        process = self.processes.pop(name, None)
        if process is None:
            return
        offset, reader = self.process_logs.pop(name)
        started = time.monotonic()
        forced = False
        try:
            # The backend deliberately drains new requests for 20 seconds
            # before handing shutdown back to uvicorn.
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=40)
        except subprocess.TimeoutExpired:
            forced = True
            self.forced.append(name)
            process.kill()
            process.wait(timeout=5)
        reader.join(timeout=2)
        # Uvicorn restores and re-raises SIGTERM after a successful lifespan
        # teardown. Require its completion marker before accepting that exit.
        completed = process.returncode == 0
        if name in ("backend", "engine") and process.returncode == -signal.SIGTERM and not forced:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                logfile = self.output / (name + ".log")
                completed = logfile.exists() and "Application shutdown complete." in logfile.read_bytes()[offset:].decode("utf-8", "replace")
                if completed:
                    break
                time.sleep(.05)
        self.shutdowns.append({"service": name, "exit_code": process.returncode,
                               "graceful_shutdown_verified": completed, "forced": forced,
                               "duration_seconds": round(time.monotonic() - started, 3)})
        if forced or (name in ("backend", "engine", "mongo", "nginx") and not completed):
            self.rec.issue(suite="assembled-cleanup", phase="cleanup", kind="unclean-service-stop",
                           message=f"{name} stop: exit={process.returncode}, forced={forced}", evidence=name + ".log")

    def wait_http(self, name, url):
        import httpx
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            process = self.processes[name]
            if process.poll() is not None:
                raise RuntimeError(f"{name} exited {process.returncode}; see {name}.log")
            try:
                response = httpx.get(url, timeout=1, trust_env=False)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(.25)
        raise TimeoutError(name + " startup exceeded 75 seconds")

    def request(self, method, path, *, expected=200, **kwargs):
        response = self.client.request(method, path, **kwargs)
        self.rec.emit("http.result", method=method, path=path, status=response.status_code)
        if response.status_code != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {response.status_code}")
        return response.json()

    def setup(self):
        import httpx
        from pymongo import MongoClient
        subprocess.run(["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(self.source)],
                       check=True, timeout=90, stdout=subprocess.DEVNULL)
        subprocess.run(["git", "checkout", "--quiet", "--detach", self.head], cwd=self.source,
                       check=True, timeout=30)
        self.env = {key: os.environ[key] for key in ("PATH", "LANG", "HOME") if key in os.environ}
        self.build_web()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            mongo_port = listener.getsockname()[1]
        self.env.update({
            "PYTHONPATH": str(self.source) + ":" + str(self.source / "backend"),
            "PYTHONUNBUFFERED": "1", "GIT_TERMINAL_PROMPT": "0", "SKIP_HEAVY_SEED": "true",
            "MONGO_URL": f"mongodb://127.0.0.1:{mongo_port}/?replicaSet=e2e",
            "SKL_MONGO_URI": f"mongodb://127.0.0.1:{mongo_port}/?replicaSet=e2e",
            "SKL_MONGO_DATABASE": "e2e_engine", "DB_NAME": "e2e_backend",
            "APP_ENV": "development", "ENVIRONMENT": "development", "SKL_ENVIRONMENT": "development",
            "GAMEFORGE_AUTH_ENFORCE": "true", "CORS_ORIGINS": f"http://127.0.0.1:{self.args.web_port}",
            "SKL_SERVER_CORS_ORIGINS": json.dumps([f"http://127.0.0.1:{self.args.web_port}"]),
            "SKELETON_INTERNAL_URL": f"http://127.0.0.1:{self.args.engine_port}", "SKL_JEEVES_CANONICAL_CONVERSATIONS": "1",
            "PRODUCT_CONTROL_ROOT": str(self.data / "product-control"),
            "SKL_DRAGON_PRACTICE_DB_PATH": str(self.data / "dragon_practice.sqlite"),
        })
        for key in ("JWT_SECRET", "GAMEFORGE_JWT_SECRET", "SKL_ENGINE_SERVICE_TOKEN"):
            self.env[key] = secrets.token_urlsafe(48)
            self.secrets.append(self.env[key])
        for key in ("SKL_OPERATION_STATE_PATH", "SKL_OPERATION_STREAM_PATH", "SKL_ENGINE_EXECUTION_STATE_PATH",
                    "SKL_ENGINE_SUBMISSION_STATE_PATH", "SKL_ENGINE_TOOL_RECEIPT_PATH", "SKL_ENGINE_QUOTA_STATE_PATH",
                    "SKL_ENGINE_PRESSURE_STATE_PATH", "SKL_GOVERNANCE_LIFECYCLE_PATH",
                    "BACKEND_TOOL_RECEIPT_PATH", "BACKEND_TOOL_RESULT_PATH"):
            self.env[key] = str(self.data / (key.lower() + ".sqlite"))
        corpus = self.data / "fixture.txt"
        corpus.write_text("Skeleton runs locally. The model generates text from local weights.\n" * 12)
        self.model = self.data / "fixture-model.json"
        training = self.start("model-build", [sys.executable, "-m", "skeleton.ai.runtime.inference.train",
            str(corpus), "--output", str(self.model), "--hidden-size", "16", "--epochs", "3", "--seed", "20261014"], self.env)
        assert training.wait(timeout=45) == 0, "fixture model build failed"
        dbpath = self.data / "mongo"
        dbpath.mkdir()
        self.start("mongo", [str(self.args.mongod.resolve()), "--bind_ip", "127.0.0.1", "--port", str(mongo_port),
            "--nounixsocket", "--replSet", "e2e", "--dbpath", str(dbpath), "--wiredTigerCacheSizeGB", "0.25"], self.env)
        self.mongo = MongoClient(f"mongodb://127.0.0.1:{mongo_port}/?directConnection=true", serverSelectionTimeoutMS=500)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            try:
                self.mongo.admin.command("ping")
                break
            except Exception:
                time.sleep(.25)
        self.mongo.admin.command("replSetInitiate", {"_id": "e2e", "members": [{"_id": 0, "host": f"127.0.0.1:{mongo_port}"}]})
        while time.monotonic() < deadline:
            if self.mongo.admin.command("hello").get("isWritablePrimary"):
                break
            time.sleep(.25)
        assert self.mongo.admin.command("hello").get("isWritablePrimary"), "Mongo primary did not become ready"
        self.start_engine()
        self.start_backend()
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{self.args.backend_port}", timeout=25, trust_env=False)

    def build_web(self):
        if self.args.web_export is not None:
            self.web_export = self.args.web_export.resolve()
            receipt = json.loads((self.web_export.parent / (self.web_export.name + ".receipt.json")).read_text())
            if receipt.get("head_sha") != self.head or receipt.get("assets_sha256") != export_digest(self.web_export):
                raise ValueError("web export receipt does not bind the candidate and all assets")
            if receipt.get("backend_url") != self.frontend_backend_url or receipt.get("engine_url") != self.frontend_engine_url:
                raise ValueError("web export receipt has different API endpoints")
            return
        modules = self.args.node_modules.resolve()
        if not (modules / "expo" / "bin" / "cli").is_file():
            raise ValueError("installed frontend dependencies are required")
        (self.source / "frontend" / "node_modules").symlink_to(modules, target_is_directory=True)
        self.web_export = self.data / "web-export"
        env = dict(self.env, CI="1", EXPO_NO_TELEMETRY="1",
                   EXPO_PUBLIC_BACKEND_URL=self.frontend_backend_url,
                   EXPO_PUBLIC_SKELETON_URL=self.frontend_engine_url)
        process = self.start("web-build", ["node", str(modules / "expo" / "bin" / "cli"),
            "export", "--platform", "web", "--output-dir", str(self.web_export)], env, self.source / "frontend")
        if process.wait(timeout=240) != 0 or not (self.web_export / "index.html").is_file():
            raise RuntimeError("exact-head Expo export failed; see web-build.log")
        self.rec.emit("web.exported", head_sha=self.head, assets_sha256=export_digest(self.web_export))

    def start_engine(self):
        env = dict(self.env, AI_PROVIDER="local", AI_LOCAL_MODEL_PATH=str(self.model))
        self.start("engine", [sys.executable, "-m", "uvicorn", "skeleton.api.server:create_app", "--factory",
                              "--host", "127.0.0.1", "--port", str(self.args.engine_port)], env)
        self.wait_http("engine", f"http://127.0.0.1:{self.args.engine_port}/api/v1/health/live")

    def start_backend(self):
        self.start("backend", [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", str(self.args.backend_port)],
                   self.env, self.source / "backend")
        self.wait_http("backend", f"http://127.0.0.1:{self.args.backend_port}/api/health")

    def api_journeys(self):
        import httpx
        assert self.request("GET", "/api/app/ready")["ok"] is True
        with httpx.Client(base_url=f"http://127.0.0.1:{self.args.engine_port}", timeout=10, trust_env=False) as engine:
            assert engine.get("/api/v1/engine/providers").status_code == 401
            headers = {"Authorization": "Bearer " + self.env["SKL_ENGINE_SERVICE_TOKEN"],
                       "x-zaibatsu-attester": "codedock-backend"}
            status = engine.get("/api/v1/engine/providers", headers=headers)
            assert status.status_code == 200 and status.json()["active"] == "local"
            assert str(self.model) not in status.text and self.env["SKL_ENGINE_SERVICE_TOKEN"] not in status.text
            headers["x-zaibatsu-attester"] = "unknown-service"
            assert engine.get("/api/v1/engine/providers", headers=headers).status_code == 403
            self.rec.emit("engine.provider-authority", authenticated="passed", anonymous="denied", unknown_service="denied")
        auth = self.request("POST", "/api/auth/register", json={"email": "e2e-one@example.com", "password": "E2e-fixture-2026!"})
        self.token = auth["access_token"]
        self.secrets.append(self.token)
        self.client.headers["Authorization"] = "Bearer " + self.token
        providers = self.request("GET", "/api/ai/providers")
        assert providers["active"] == "local" and providers["llm_available"] is True
        assert providers["providers"][0]["network_policy"] == "none"
        thread = self.request("POST", "/api/v1/conversations", json={"title": "Assembled native E2E"})["thread"]
        self.thread_id = thread["thread_id"]
        self.chat_body = {"thread_id": self.thread_id, "expected_thread_version": thread["version"],
                          "idempotency_key": "assembled-replay", "message": "hello local model"}
        self.chat_result = self.request("POST", "/api/ai/chat", json=self.chat_body)
        assert self.chat_result["success"] is True
        messages = self.request("GET", f"/api/v1/conversations/{self.thread_id}/messages")["messages"]
        assistants = [message for message in messages if message["author_type"] == "assistant"]
        assert len(messages) == 2 and len(assistants) == 1
        self.assistant_id = assistants[0]["message_id"]
        assert assistants[0]["operation_id"] and assistants[0]["provider_receipt_refs"]
        with ThreadPoolExecutor(max_workers=3) as workers:
            futures = [workers.submit(self.client.post, "/api/ai/chat", json=self.chat_body) for _ in range(3)]
            for future in futures:
                response = future.result(timeout=25)
                assert response.status_code == 200 and response.json()["response"] == self.chat_result["response"]
        after = self.request("GET", f"/api/v1/conversations/{self.thread_id}/messages")["messages"]
        assert [m["message_id"] for m in after] == [m["message_id"] for m in messages]
        self.rec.emit("chat.concurrent-replay", retries=3, assistant_commits=1)
        other = self.request("POST", "/api/auth/register", json={"email": "e2e-two@example.com", "password": "E2e-fixture-2026!"})
        self.secrets.append(other["access_token"])
        response = self.client.get(f"/api/v1/conversations/{self.thread_id}/messages",
                                   headers={"Authorization": "Bearer " + other["access_token"]})
        assert response.status_code in (403, 404), "another principal could read private conversation state"
        self.rec.emit("authority.isolation", result="denied-other-principal")

    def lineage_journey(self):
        thread = self.request("POST", "/api/v1/conversations", json={"title": "Lineage and governed deletion"})["thread"]
        self.lineage_id = thread["thread_id"]
        path = f"/api/v1/conversations/{self.lineage_id}"
        for index in range(2):
            thread = self.request("GET", path)["thread"]
            result = self.request("POST", "/api/ai/chat", json={"thread_id": self.lineage_id,
                "expected_thread_version": thread["version"], "idempotency_key": f"lineage-{index}",
                "message": f"local model conversation turn {index}"})
            assert result["success"] is True
        messages = self.request("GET", path + "/messages")["messages"]
        assert len(messages) == 4 and [m["sequence"] for m in messages] == [1, 2, 3, 4]
        assert messages[2]["parent_message_id"] == messages[1]["message_id"]
        thread = self.request("GET", path)["thread"]
        edited = self.request("POST", path + f"/messages/{messages[0]['message_id']}/edit", json={
            "content": "edited branch of the first local turn", "idempotency_key": "lineage-edit",
            "expected_thread_version": thread["version"]})
        assert edited["message"]["supersedes_message_id"] == messages[0]["message_id"]
        full = self.request("GET", path + "/messages")["messages"]
        assert len(full) == 5 and full[0]["content"] == messages[0]["content"]
        active = self.request("GET", path + "/messages", params={"active_only": "true"})["messages"]
        assert active[-1]["message_id"] == edited["message"]["message_id"]
        self.rec.emit("conversation.lineage", turns=2, original_messages_preserved=True, edited_branch=True)

    def project_journey(self):
        db = self.mongo[self.env["DB_NAME"]]
        self.project_id = "assembled-e2e-project"
        db.playables.insert_one({"playable_id": self.project_id, "title": "E2E local project",
            "genre": "platformer", "brief": "A bounded local fixture for world evidence.", "version": 1})
        db.game_kb.insert_one({"game_id": self.project_id, "artifacts": {
            "core_specs": {"title": "E2E local project", "logline": "Local project evidence fixture"},
            "lore_graph": {"regions": [{"name": "Fixture valley"}]},
            "quest_db": {"quests": [{"name": "Fixture quest"}]},
            "mechanics_config": {"core_mechanics": ["jump"]},
        }})
        evidence = self.request("GET", f"/api/pipeline/{self.project_id}/kb")
        assert evidence["game_id"] == self.project_id and evidence["present_count"] == 4
        assets = self.request("GET", f"/api/assets/genesis/game/{self.project_id}")
        assert "error" not in assets
        self.request("GET", f"/api/galaxy-studio/systems/build/{self.project_id}")
        self.rec.emit("project.evidence", game_id=self.project_id, fixture_artifacts=4)

    def deletion_journey(self):
        path = f"/api/v1/conversations/{self.lineage_id}"
        thread = self.request("GET", path)["thread"]
        result = self.request("DELETE", path, params={"expected_thread_version": thread["version"]})
        assert result["complete"] is True and result["deletion_state"] == "deleted" and result["plan_id"]
        assert self.client.get(path + "/messages").status_code == 404
        self.rec.emit("conversation.deleted", complete=True, governance_plan_bound=True)

    def sanitize_trace(self, raw, target):
        with zipfile.ZipFile(raw) as source, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as destination:
            for item in source.infolist():
                data = source.read(item.filename)
                for secret in self.secrets:
                    data = data.replace(secret.encode(), b"[REDACTED TEST CREDENTIAL]")
                destination.writestr(item, data)
        raw.unlink()

    def browser_journey(self, name, viewport):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
            context = browser.new_context(viewport=viewport, locale="en-US")
            context.add_init_script('localStorage.setItem("gameforge_auth_token",' + json.dumps(self.token) + ');')
            context.tracing.start(screenshots=True, snapshots=True, sources=False)
            page = context.new_page()
            errors = []
            def runtime_error(error):
                message = self.safe(error)
                errors.append(urlsplit(page.url).path + ": " + message)
                self.browser_events.append({"viewport": name, "kind": "pageerror",
                    "path": urlsplit(page.url).path, "message": message[:2000]})
            page.on("pageerror", runtime_error)
            page.on("console", lambda message: self.browser_events.append({"viewport": name, "kind": "console",
                "type": message.type, "message": self.safe(message.text)[:2000]}))
            page.on("response", lambda response: self.browser_events.append({"viewport": name, "kind": "http",
                "status": response.status, "path": urlsplit(response.url).path}) if response.status >= 400 else None)
            try:
                for route in ("/product", "/jeeves-chat", "/world-workbench", "/design-review"):
                    if route in ("/world-workbench", "/design-review"):
                        route += "?game=" + self.project_id
                    page.goto(f"http://127.0.0.1:{self.args.web_port}" + route, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(700)
                    assert len(page.locator("body").inner_text()) > 30, "blank route: " + route
                    if route == "/product":
                        assert "HEALTHY" in page.locator("body").inner_text()
                    if route == "/jeeves-chat":
                        if viewport["width"] < 760:
                            page.get_by_role("button", name="Show companion", exact=True).click()
                            page.get_by_role("button", name="Hide companion", exact=True).click()
                        page.get_by_test_id("chat-input").fill("hello local model from browser")
                        with page.expect_response(lambda response: "/api/jeeves/chat" in response.url
                                and response.request.method == "POST", timeout=30000) as pending:
                            page.get_by_test_id("chat-send").click(timeout=10000)
                        response = pending.value
                        assert response.status == 200, "browser chat did not complete"
                        assert response.json()["tier"] == "local-model", "browser did not use configured local model"
                        page.wait_for_timeout(500)
                        page.reload(wait_until="networkidle")
                        page.wait_for_timeout(700)
                        assert "hello local model from browser" in page.locator("body").inner_text(), "refresh lost durable chat"
                    if route.startswith("/world-workbench"):
                        assert "Game knowledge evidence" in page.locator("body").inner_text(), "workbench did not load project KB"
                    if route.startswith("/design-review"):
                        assert "Game knowledge loaded" in page.locator("body").inner_text(), "review did not load project KB"
                        page.get_by_test_id("design-focus-narrative").click()
                        assert self.project_id in page.get_by_test_id("design-review-brief").input_value()
                    page.screenshot(path=str(self.output / (name + urlsplit(route).path.replace("/", "-") + ".png")), full_page=True)
                assert not errors, "browser runtime error: " + "; ".join(errors)[:800]
                failures = [event for event in self.browser_events
                            if event.get("viewport") == name and event.get("status", 0) >= 500]
                assert not failures, "browser API failure: " + str(failures[:3])
            except Exception:
                page.screenshot(path=str(self.output / (name + "-failure.png")), full_page=True)
                raise
            finally:
                raw = self.output / (name + "-trace-raw.zip")
                context.tracing.stop(path=str(raw))
                self.sanitize_trace(raw, self.output / (name + "-trace.zip"))
                browser.close()

    def start_web(self):
        directory = self.web_export
        if self.args.nginx:
            prefix = self.data / "nginx"
            prefix.mkdir()
            (prefix / "logs").mkdir()
            server = (self.source / "frontend/nginx.conf").read_text()
            server = server.replace("listen 8080;", f"listen 127.0.0.1:{self.args.web_port};")
            server = server.replace("root /usr/share/nginx/html;", f'root "{directory}";')
            server = server.replace("http://skeleton:8001", f"http://127.0.0.1:{self.args.engine_port}")
            server = server.replace("http://backend:8001", f"http://127.0.0.1:{self.args.backend_port}")
            config = prefix / "nginx.conf"
            # UID-mapped containers may not map Nginx's default nobody user.
            # Keep this loopback fixture's temporary files with their owner.
            owner = "user root root;\n" if os.geteuid() == 0 else ""
            config.write_text(owner + "daemon off;\nmaster_process off;\nworker_processes 1;\npid " + str(prefix / "nginx.pid")
                + ";\nerror_log stderr notice;\nevents { worker_connections 128; }\nhttp {\n"
                + "access_log off;\nclient_body_temp_path " + str(prefix / "body") + ";\n"
                + "proxy_temp_path " + str(prefix / "proxy") + ";\n"
                + "types { text/html html; text/css css; application/javascript js mjs; application/json json; "
                + "image/png png; image/jpeg jpg jpeg; image/svg+xml svg; font/ttf ttf; font/woff2 woff2; }\n"
                + server + "\n}\n")
            self.start("nginx", [str(self.args.nginx.resolve()), "-p", str(prefix) + "/", "-c", str(config)], self.env)
            self.wait_http("nginx", f"http://127.0.0.1:{self.args.web_port}/healthz")
            return
        class Handler(SimpleHTTPRequestHandler):
            def do_GET(self):
                path = urlsplit(self.path).path
                if not (directory / path.lstrip("/")).is_file():
                    self.path = path + ".html" if (directory / (path.lstrip("/") + ".html")).is_file() else (
                        "/gate/[stage].html" if path.startswith("/gate/") else "/index.html")
                return super().do_GET()
            def log_message(self, *_):
                pass
        self.web = ThreadingHTTPServer(("127.0.0.1", self.args.web_port), partial(Handler, directory=str(directory)))
        threading.Thread(target=self.web.serve_forever, daemon=True).start()

    def ingress_journey(self):
        import httpx
        direct = self.client
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{self.args.web_port}", timeout=25, trust_env=False,
                              headers={"Authorization": "Bearer " + self.token}) as ingress:
                self.client = ingress
                health = self.request("GET", "/api/v1/health/live")
                assert health["alive"] is True and health["application"]["component"] == "engine"
                threads = self.request("GET", "/api/v1/conversations")["threads"]
                assert any(thread["thread_id"] == self.thread_id for thread in threads)
                replay = self.request("POST", "/api/ai/chat", json=self.chat_body)
                assert replay["response"] == self.chat_result["response"]
                messages = self.request("GET", f"/api/v1/conversations/{self.thread_id}/messages")["messages"]
                assert len(messages) == 2
        finally:
            self.client = direct

    def product_route_audit(self):
        """Open every declared journey destination; never start a build or crawl."""
        from playwright.sync_api import sync_playwright
        catalog = (self.source / "frontend/src/product/journeyCatalog.ts").read_text()
        routes = sorted(set(re.findall(r"href:\s*'(/[^']*)'", catalog)))
        if self.args.audit_all_routes:
            routes = sorted("/" + path.relative_to(self.web_export).with_suffix("").as_posix()
                            for path in self.web_export.rglob("*.html")
                            if not any(part.startswith(("_", "+")) for part in path.relative_to(self.web_export).parts))
            routes = [route.removesuffix("index") if route.endswith("/index")
                      else "/gate/fine_tuning" if route == "/gate/[stage]" else route
                      for route in routes]
        if self.args.audit_route:
            routes = self.args.audit_route
        assert routes, "the product journey inventory is empty"
        results = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
            context.add_init_script('localStorage.setItem("gameforge_auth_token",' + json.dumps(self.token) + ');')
            for route in routes:
                page = context.new_page()
                errors, failures = [], []
                page.on("pageerror", lambda error: errors.append(self.safe(error)))
                page.on("response", lambda response: failures.append({"path": urlsplit(response.url).path,
                    "status": response.status}) if response.status >= 500 else None)
                try:
                    response = page.goto(f"http://127.0.0.1:{self.args.web_port}" + route,
                                         wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(1200)
                    assert response and response.status == 200, "route document did not load"
                    assert page.locator("body").inner_text().strip(), "route rendered a blank body"
                except Exception as exc:
                    errors.append(self.safe(exc)[:800])
                result = {"route": route, "runtime_errors": errors, "http_failures": failures}
                results.append(result)
                (self.output / "route-audit.json").write_text(json.dumps(results, indent=2))
                if errors or failures:
                    page.screenshot(path=str(self.output / ("audit" + route.replace("/", "-") + ".png")), full_page=True)
                    self.rec.issue(suite="assembled-product-routes", phase="execute", kind="route-failure",
                                   testcase=route, message=json.dumps(result)[:1200], evidence="route-audit.json")
                self.rec.emit("browser.route-audited", route=route, errors=len(errors), failures=len(failures))
                page.close()
            browser.close()
        (self.output / "route-audit.json").write_text(json.dumps(results, indent=2))
        assert not any(result["runtime_errors"] or result["http_failures"] for result in results), "product route audit failed"

    def restart_journey(self):
        self.stop("backend")
        self.stop("engine")
        self.start_engine()
        self.start_backend()
        replay = self.request("POST", "/api/ai/chat", json=self.chat_body)
        assert replay["response"] == self.chat_result["response"], "restart changed an idempotent result"
        messages = self.request("GET", f"/api/v1/conversations/{self.thread_id}/messages")["messages"]
        assistants = [message for message in messages if message["author_type"] == "assistant"]
        assert len(messages) == 2 and len(assistants) == 1
        assert assistants[0]["message_id"] == self.assistant_id, "restart duplicated assistant commit"

    def outage_journey(self):
        self.stop("engine")
        status = self.request("GET", "/api/app/status")
        assert status["ok"] is False, "engine outage was reported healthy"
        providers = self.request("GET", "/api/ai/providers")
        assert providers["llm_available"] is False
        messages = self.request("GET", f"/api/v1/conversations/{self.thread_id}/messages")["messages"]
        assert len([message for message in messages if message["author_type"] == "assistant"]) == 1

    def run(self):
        try:
            with self.journey("assembled-startup"):
                self.setup()
            with self.journey("assembled-native-api"):
                self.api_journeys()
            with self.journey("assembled-conversation-lineage"):
                self.lineage_journey()
            with self.journey("assembled-project-evidence"):
                self.project_journey()
            self.start_web()
            if self.args.nginx:
                with self.journey("assembled-same-origin-ingress"):
                    self.ingress_journey()
            with self.journey("assembled-browser-desktop"):
                self.browser_journey("desktop", {"width": 1440, "height": 1000})
            with self.journey("assembled-browser-mobile"):
                self.browser_journey("mobile", {"width": 390, "height": 844})
            if self.args.audit_product_routes or self.args.audit_all_routes or self.args.audit_route:
                with self.journey("assembled-product-routes"):
                    self.product_route_audit()
            with self.journey("assembled-restart-replay"):
                self.restart_journey()
            with self.journey("assembled-conversation-deletion"):
                self.deletion_journey()
            with self.journey("assembled-engine-outage"):
                self.outage_journey()
        except Exception as exc:
            if not self.rec.issues:
                self.rec.issue(suite="assembled-system", phase="execute", kind="harness-error",
                               message=self.safe(str(exc))[:1200], evidence="events.jsonl")
        finally:
            if self.web is not None:
                self.web.shutdown()
                self.web.server_close()
            if self.client is not None:
                self.client.close()
            for name in reversed(list(self.processes)):
                self.stop(name)
            if self.mongo is not None:
                self.mongo.close()
            for reader in self.readers:
                reader.join(timeout=2)
            (self.output / "browser-events.json").write_text(json.dumps(self.browser_events, indent=2))
            served_digest = export_digest(self.web_export) if self.web_export is not None and self.web_export.exists() else None
            self.temp.cleanup()
            cleanup = {"all_children_stopped": not self.processes, "temporary_data_removed": not self.data.exists(),
                       "forced_process_terminations": self.forced, "service_shutdowns": self.shutdowns}
            if not cleanup["all_children_stopped"] or not cleanup["temporary_data_removed"]:
                self.rec.issue(suite="assembled-cleanup", phase="cleanup", kind="incomplete-cleanup",
                               message="campaign processes or data survived cleanup", evidence="cleanup.json")
            (self.output / "cleanup.json").write_text(json.dumps(cleanup, indent=2))
            executed = {suite["id"] for suite in self.rec.suites}
            for suite in self.expected_journeys:
                if suite not in executed:
                    self.rec.suites.append({"id": suite, "status": "not_run", "duration_seconds": 0.0})
            (self.output / "scope.json").write_text(json.dumps({"head_sha": self.head,
                "model_quality_certified": False, "native_device_installer_verified": False,
                "live_providers_used": False, "source_checkout": "disposable-exact-commit",
                "browser_engine": "Chromium", "web_assets_sha256": served_digest,
                "project_generation_verified": False, "project_views": "seeded-disposable-artifacts",
                "frontend_lock_sha256": hashlib.sha256((ROOT / "frontend" / "yarn.lock").read_bytes()).hexdigest(),
                "ports": {"backend": self.args.backend_port, "engine": self.args.engine_port, "web": self.args.web_port},
                "expected_journeys": self.expected_journeys,
                "browser_api_ingress": "production-nginx" if self.args.nginx else "direct-loopback",
                "route_audit_requested": self.args.audit_all_routes or self.args.audit_product_routes or bool(self.args.audit_route)}, indent=2))
            self.rec.finish("isolated-e2e")
        return 1 if self.rec.issues else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongod", type=Path, required=True)
    parser.add_argument("--web-export", type=Path,
                        help="Optional exact-head export with sibling NAME.receipt.json; otherwise build the candidate")
    parser.add_argument("--node-modules", type=Path, default=ROOT / "frontend" / "node_modules",
                        help="Installed locked frontend dependencies for a disposable exact-head export")
    parser.add_argument("--backend-port", type=int, default=38001)
    parser.add_argument("--engine-port", type=int, default=38010)
    parser.add_argument("--web-port", type=int, default=33000)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".e2e-evidence" / "assembled-system")
    parser.add_argument("--audit-product-routes", action="store_true",
                        help="also open every destination declared in the product journey catalog")
    parser.add_argument("--audit-all-routes", action="store_true",
                        help="audit every exported public HTML route instead of only journey destinations")
    parser.add_argument("--nginx", type=Path,
                        help="use a real Nginx executable with the production ingress config")
    parser.add_argument("--audit-route", action="append", default=[],
                        help="audit a specific relative route; repeat to reproduce individual failures")
    args = parser.parse_args()
    ports = (args.backend_port, args.engine_port, args.web_port)
    if len(set(ports)) != 3 or any(not 1024 <= port <= 65535 for port in ports):
        parser.error("campaign ports must be distinct unprivileged ports")
    if not args.mongod.is_file() or (args.web_export is not None and not (args.web_export / "index.html").is_file()):
        parser.error("a local mongod executable and valid optional Expo export are required")
    return Campaign(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
