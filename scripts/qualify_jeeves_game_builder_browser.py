"""Real local-model -> browser -> Godot -> verified source ZIP acceptance.

Requires an operator-owned pinned Jeeves GGUF deployment, installed Godot 4,
NumPy, Playwright and Chromium. It never downloads a model or substitutes a
fixture response. Example::

    python scripts/qualify_jeeves_game_builder_browser.py --manifest /private/jeeves.json \
        --output /tmp/jeeves-forge-browser --port 8766

The generated game is a synthetic test project. This checks the complete local
workflow, not general model quality, human enjoyment or production release.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import http.client
import io
import json
from pathlib import Path, PurePosixPath
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
import zipfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SOURCES = (
    "skeleton/app/offline_game_builder.py", "skeleton/app/offline_http.py",
    "skeleton/app/offline_web.py", "skeleton/forge/game_builder.py",
    "skeleton/forge/game_design_spec.py", "skeleton/forge/game_content.py",
    "skeleton/forge/playable_runtime.py", "skeleton/app/jeeves_local_lease.py",
    "scripts/qualify_jeeves_game_builder_browser.py",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def source_identity() -> dict:
    return {
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "tracked_tree_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True).strip()),
        "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES},
    }


def request(origin: str, method: str, path: str, token: str | None = None, body=None):
    parsed = urlsplit(origin)
    connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=20)
    headers = {"Authorization": "Bearer " + token} if token else {}
    if body is not None:
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


@contextmanager
def observe_real_execution(backend):
    """Count genuine calls while forwarding arguments/results unchanged."""
    lock = threading.Lock()
    observations = {"model_calls": 0, "godot_processes": []}
    original_infer = backend.infer
    original_run = subprocess.run

    def observed_infer(*args, **kwargs):
        with lock:
            observations["model_calls"] += 1
        return original_infer(*args, **kwargs)

    def observed_run(*args, **kwargs):
        command = args[0] if args else kwargs.get("args")
        native = (isinstance(command, (list, tuple)) and command
                  and "godot" in Path(str(command[0])).name.lower())
        result = original_run(*args, **kwargs)
        if native:
            with lock:
                observations["godot_processes"].append({
                    "headless": "--headless" in command,
                    "import": "--import" in command,
                    "input_replay": "--script" in command,
                    "returncode": result.returncode,
                })
        return result

    backend.infer = observed_infer
    subprocess.run = observed_run
    try:
        yield observations
    finally:
        backend.infer = original_infer
        subprocess.run = original_run


@contextmanager
def local_service(backend, database: Path, token: str, port: int):
    from skeleton.app.offline_http import LocalOnlyHTTPServer, OfflineHTTPApplication

    application = OfflineHTTPApplication(backend, database, token=token)
    server = LocalOnlyHTTPServer(application, port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield application, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
        application.close()


def open_sidebar(page) -> None:
    if page.viewport_size["width"] <= 720 and page.locator("#sidebar-toggle").get_attribute("aria-expanded") != "true":
        page.locator("#sidebar-toggle").click()


def connect(page, token: str) -> None:
    from playwright.sync_api import expect

    open_sidebar(page)
    page.locator("#secret").fill(token)
    page.locator("#connect").click()
    expect(page.locator("#disconnect")).to_be_enabled()
    require(page.locator("#secret").input_value() == "", "connection clears token input")


def screenshot(page, path: Path) -> None:
    page.screenshot(path=str(path), full_page=True,
                    mask=[page.locator("#secret")], mask_color="#1b2230")


def validate_archive(payload: bytes, metadata: dict) -> dict:
    require(0 < len(payload) <= 16 * 1024 * 1024, "archive fits the fixed response budget")
    require(len(payload) == metadata["bytes"] and sha256(payload).hexdigest() == metadata["sha256"],
            "downloaded bytes match durable archive size and digest")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        require(archive.testzip() is None, "archive entries have valid CRCs")
        names = archive.namelist()
        require(len(names) == metadata["file_count"], "archive member count matches receipt")
        for name in names:
            path = PurePosixPath(name)
            require(not path.is_absolute() and ".." not in path.parts and "\\" not in name and ":" not in name,
                    "source archive uses confined portable relative paths")
            require(not any(part in {".git", ".godot", ".env"} for part in path.parts),
                    "archive excludes local state and credentials")
        for expected in ("project.godot", "PLAY.md", "data/design_spec.json", "scripts/runtime/playable_game.gd"):
            require(any(name == expected or name.endswith("/" + expected) for name in names),
                    "archive includes the maintained game source: " + expected)
        spec_name = next(name for name in names if name == "data/design_spec.json" or name.endswith("/data/design_spec.json"))
        spec = json.loads(archive.read(spec_name))
    return {"sha256": metadata["sha256"], "bytes": len(payload), "file_count": len(names),
            "spec_id": spec["spec_id"], "genre": spec["genre"]}


def qualify(manifest: Path, output: Path, port: int, executable: str | None = None) -> dict:
    from playwright.sync_api import expect, sync_playwright
    from skeleton.app.local_ai import load_gguf_deployment

    output = output.expanduser().resolve()
    require(not output.is_relative_to(ROOT), "qualification artifacts must be outside the source checkout")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    token = secrets.token_urlsafe(48)
    checks: list[str] = []
    page_errors: list[str] = []
    external: list[str] = []
    submitted: list[dict] = []
    source = source_identity()
    started = time.monotonic()
    backend = load_gguf_deployment(manifest)
    require(backend.model_id == "jeeves", "operator deployment is the actual primary Jeeves model")
    report = {
        "schema": "skeleton.jeeves.game-builder-browser-qualification.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(), "source": source,
        "model_sha256": backend.model_digest, "runtime_sha256": backend.runtime_digest,
        "deployment_manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
        "python": platform.python_version(), "platform": platform.platform(),
        "synthetic_test_project": True, "model_or_native_results_mocked": False,
        "general_model_quality_qualified": False, "human_game_quality_qualified": False,
        "network_observation_scope": "browser requests only; whole-process egress not measured",
        "checks": checks, "page_errors": page_errors,
    }
    with tempfile.TemporaryDirectory(prefix="jeeves-forge-browser-") as temporary, observe_real_execution(backend) as observations:
        with local_service(backend, Path(temporary) / "workspace.sqlite3", token, port) as (app, origin), sync_playwright() as pw:
            options = {"headless": True}
            browser_path = executable or shutil.which("chromium") or shutil.which("chromium-browser")
            if browser_path:
                options["executable_path"] = browser_path
            browser = pw.chromium.launch(**options)
            report["browser"] = browser.version
            context = browser.new_context(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
            page = context.new_page()
            page.set_default_timeout(15000)
            page.on("pageerror", lambda error: page_errors.append(str(error).replace(token, "[redacted]")))

            def route_local_only(route):
                if urlsplit(route.request.url).netloc != urlsplit(origin).netloc:
                    external.append(urlsplit(route.request.url).netloc)
                    route.abort()
                else:
                    route.continue_()

            def observe_request(req):
                if req.method == "POST" and req.url == origin + "/v1/game-builds":
                    submitted.append(req.post_data_json)

            context.route("**/*", route_local_only)
            page.on("request", observe_request)
            try:
                status, _, _ = request(origin, "GET", "/v1/game-builds")
                require(status == 401, "anonymous client cannot inspect local game jobs")
                status, _, _ = request(origin, "POST", "/v1/game-builds", body={"request_id": "anonymous", "brief": "A small game"})
                require(status == 401 and observations["model_calls"] == 0,
                        "anonymous submission performs no model work")
                checks.append("real HTTP denies anonymous job reads and submissions before inference")
                page.goto(origin)
                connect(page, token)
                page.locator("#forge-open").click()
                expect(page.locator("#forge-panel")).to_be_visible()
                page.locator("#forge-genre-shooter").click()
                page.locator("#forge-brief").fill(
                    "A small original signal garden where a caretaker clears sentinel waves and restores the beacon")
                page.locator("#forge-difficulty").select_option("easy")
                page.locator("#forge-theme").select_option("neon")
                page.locator("#forge-encounter").select_option("patrol")
                page.locator("#forge-speed").fill("230")
                page.locator("#forge-objective").fill("Restore the garden beacon")
                page.locator("#forge-review").click()
                expect(page.locator("#forge-submit")).to_be_enabled()
                require(observations["model_calls"] == 0 and not submitted,
                        "editing and reviewing a brief never generate a model request")
                checks.append("authenticated guided brief and exact review perform zero generation")
                reviewed = page.locator("#forge-reviewed-brief").inner_text()
                with page.expect_response(lambda response: response.url == origin + "/v1/game-builds"
                                          and response.request.method == "POST") as admitted:
                    page.locator("#forge-submit").click()
                require(admitted.value.status == 202, "explicit reviewed submit receives asynchronous admission")
                job_id = admitted.value.json()["request_id"]
                require(len(submitted) == 1 and submitted[0]["request_id"] == job_id
                        and submitted[0]["brief"] == reviewed, "submitted bytes match the reviewed brief")
                report["request_id"] = job_id
                report["brief_sha256"] = sha256(reviewed.encode()).hexdigest()
                checks.append("one explicit review submits the exact brief and receives a durable request identity")

                # Locking the tab must scrub its contents without creating a
                # replacement operation when the user reconnects.
                open_sidebar(page)
                page.locator("#disconnect").click()
                require(page.locator("#forge-brief").input_value() == "", "lock clears the authored game brief")
                require(page.locator("#forge-current-id").inner_text() == "", "lock clears selected build identity")
                connect(page, token)
                page.locator("#forge-open").click()
                resume = page.locator("#forge-resume-" + job_id)
                expect(resume).to_be_visible()
                resume.click()
                expect(page.locator("#forge-download")).to_be_enabled(timeout=210000)
                require(len(submitted) == 1, "lock/reconnect recovery never submits another operation")
                checks.append("lock scrubs brief/job state; reconnect resumes the original operation")

                status, _, raw_job = request(origin, "GET", "/v1/game-builds/" + job_id, token)
                require(status == 200, "completed job can be read through authenticated HTTP")
                job = json.loads(raw_job)
                require(job["state"] == "complete" and job["terminal"] is True and job["result"]["ok"] is True,
                        "durable terminal job reports actual successful completion")
                planning = job["result"]["planning"]
                require(planning["status"] == "accepted" and planning["model_digest"] == backend.model_digest,
                        "a genuine bound model proposal was accepted")
                proof = job["result"]["build"]["interactive"]
                require(proof["input_journey_verified"] is True and proof["receipt"]["phase"] == "won"
                        and proof["receipt"]["pause_verified"] is True and proof["receipt"]["restart_verified"] is True,
                        "actual Godot input journey won, paused and restarted")
                require(observations["model_calls"] == len(planning["attempts"])
                        and 1 <= observations["model_calls"] <= 2,
                        "observed real inference count matches bounded planning attempts")
                require(any(run["input_replay"] and run["returncode"] == 0 for run in observations["godot_processes"]),
                        "a real Godot input replay subprocess executed successfully")
                checks.append("real pinned GGUF proposal and real Godot winning input proof are durably recorded")
                snapshot_calls = observations["model_calls"]
                with page.expect_download() as downloaded:
                    page.locator("#forge-download").click()
                payload = Path(downloaded.value.path()).read_bytes()
                report["archive"] = validate_archive(payload, job["archive"])
                (output / "forge-project.zip").write_bytes(payload)
                checks.append("browser ZIP download matches durable digest and contains confined complete game source")

                status, _, replay_bytes = request(origin, "POST", "/v1/game-builds", token, submitted[0])
                require(status == 202 and json.loads(replay_bytes)["request_id"] == job_id,
                        "same identity and body replay the original job")
                status, _, _ = request(origin, "POST", "/v1/game-builds", token,
                                       {**submitted[0], "brief": reviewed + " changed"})
                require(status == 409, "changed content under the same request identity conflicts")
                require(observations["model_calls"] == snapshot_calls, "replay/conflict perform no new model inference")
                checks.append("exact request replay is read-only; conflicting reuse is rejected")
                page.locator("#forge-current").scroll_into_view_if_needed()
                screenshot(page, output / "jeeves-forge-desktop.png")

                page.reload()
                connect(page, token)
                page.locator("#forge-open").click()
                page.locator("#forge-resume-" + job_id).click()
                expect(page.locator("#forge-download")).to_be_enabled()
                page.set_viewport_size({"width": 390, "height": 844})
                page.locator("#forge-download").scroll_into_view_if_needed()
                require(page.evaluate("() => document.documentElement.scrollWidth <= innerWidth"),
                        "mobile native builder has no horizontal document overflow")
                box = page.locator("#forge-download").bounding_box()
                require(bool(box) and box["x"] >= 0 and box["x"] + box["width"] <= 390
                        and box["y"] >= 0 and box["y"] + box["height"] <= 844,
                        "mobile source download control is reachable inside the viewport")
                screenshot(page, output / "jeeves-forge-mobile.png")
                require(observations["model_calls"] == snapshot_calls and len(submitted) == 1,
                        "reload, saved-job inspection and mobile rendering never rerun inference")
                checks.append("reload recovers the durable job; desktop and 390px mobile expose its original archive")
                require(not page_errors and not external, "browser has no page crashes or external requests")
                require(source_identity()["source_sha256"] == source["source_sha256"],
                        "tested product source bytes remained stable during qualification")
                report["status"] = "passed"
                report["planning_attempts"] = len(planning["attempts"])
                report["native_input_receipt"] = proof["receipt"]
            except Exception as error:
                report["status"] = "failed"
                report["failure"] = str(error).replace(token, "[redacted]")
                try:
                    screenshot(page, output / "jeeves-forge-failure.png")
                except Exception:
                    pass
                raise
            finally:
                report["observed_execution"] = observations
                report["external_browser_requests"] = len(external)
                report["elapsed_seconds"] = round(time.monotonic() - started, 3)
                (output / "jeeves-forge-browser-report.json").write_text(json.dumps(report, indent=2) + "\n")
                context.close()
                browser.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("/workspace/artifacts/jeeves-forge-browser"))
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--chromium")
    args = parser.parse_args()
    try:
        report = qualify(args.manifest, args.output, args.port, args.chromium)
    except Exception:
        print("Real Jeeves game-builder browser qualification FAILED; inspect the redacted report.", file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]),
                      "report": str(args.output / "jeeves-forge-browser-report.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
