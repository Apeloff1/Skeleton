#!/usr/bin/env python3
"""UI/HTTP/SQLite/Forge/Godot qualification with an explicit proposal fixture.

Only ``offline_game_builder.propose`` is replaced. No trained model is run or
qualified. The canonical compiler, job persistence, publication, ZIP custody
and installed Godot import/input journey remain real. The separate
``qualify_jeeves_game_builder_browser.py`` still requires an operator GGUF.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import time
from unittest.mock import patch
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qualify_jeeves_game_builder_browser import (
    connect, local_service, observe_real_execution, open_sidebar, request,
    require, screenshot, source_identity, validate_archive,
)


def qualify(output: Path, port: int, executable: str | None = None) -> dict:
    from playwright.sync_api import expect, sync_playwright
    from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
    from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
    from skeleton.app import offline_game_builder as builder
    from skeleton.cortex.transformer import TinyTransformer

    output = output.expanduser().resolve()
    require(not output.is_relative_to(ROOT), "Artifacts must be outside the checkout")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    backend = NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "local", " "),
        dim=8, ctx=2048, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))
    # A real native identity/readiness envelope is used only for store scope.
    # Proposal generation is the sole substituted application operation.
    backend.model_id = backend._admitted_model_id = "jeeves"
    token = secrets.token_urlsafe(48)
    proposal_calls: list[dict] = []
    submitted: list[dict] = []
    errors: list[str] = []
    external: list[str] = []
    checks: list[str] = []
    source = source_identity()
    source["source_sha256"][str(Path(__file__).relative_to(ROOT))] = sha256(Path(__file__).read_bytes()).hexdigest()
    started = time.monotonic()
    report = {"schema": "skeleton.jeeves.game-builder-fixture-browser.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(), "source": source,
        "scope": "Actual browser, authenticated HTTP, SQLite, compiler and installed Godot; scripted structured proposal only",
        "fixtures": ["structured proposal", "native identity envelope without inference"],
        "transport_faults": ["first POST acknowledgement lost after real admission", "job reads temporarily unavailable"],
        "model_generation_executed": False, "trained_model_quality_qualified": False,
        "native_distribution_admitted": False, "physical_device_qualified": False,
        "checks": checks, "page_errors": errors}

    async def proposal_fixture(selected_backend, compiled, **options):
        candidate = {key: compiled[key] for key in ("title", "fantasy", "core_loop", "gameplay")}
        candidate.update(title="Signal Garden",
            fantasy="Restore a silent orbital garden and recover its lost beacon.",
            core_loop="Move through the garden, clear sentinel waves and restore the beacon.")
        accepted, violations = builder.admit_proposal(compiled, candidate)
        require(not violations, "Fixture remains subject to the actual proposal guard")
        proposal_calls.append({"brief_sha256": sha256(compiled["brief"].encode()).hexdigest(),
                               "output_tokens": options["output_tokens"]})
        return accepted, {"status": "accepted", "attempts": [], "fixture_only": True,
            "model_digest": selected_backend.model_digest, "runtime_digest": selected_backend.runtime_digest,
            "network_provider_used": False, "generated_source_admitted": False,
            "quality_qualified": False, "fixture": "Scripted complete design; no model inference"}

    with tempfile.TemporaryDirectory(prefix="jeeves-forge-fixture-") as temporary:
        with patch.object(builder, "propose", proposal_fixture), observe_real_execution(backend) as observed:
            with local_service(backend, Path(temporary) / "workspace.sqlite3", token, port) as (app, origin), sync_playwright() as pw:
                browser_path = executable or shutil.which("chromium") or shutil.which("chromium-browser")
                browser = pw.chromium.launch(headless=True, executable_path=browser_path)
                report["browser"] = browser.version
                context = browser.new_context(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
                page = context.new_page()
                page.set_default_timeout(20000)
                page.on("pageerror", lambda error: errors.append(str(error).replace(token, "[redacted]")))
                fault = {"lost": False, "hold_reads": False}

                def transport(route):
                    req = route.request
                    if urlsplit(req.url).netloc != urlsplit(origin).netloc:
                        external.append(urlsplit(req.url).netloc)
                        route.abort()
                    elif req.method == "POST" and req.url == origin + "/v1/game-builds":
                        submitted.append(req.post_data_json)
                        if not fault["lost"]:
                            response = route.fetch()
                            require(response.status == 202, "The original request was actually admitted")
                            fault["lost"] = fault["hold_reads"] = True
                            route.abort("failed")
                        else:
                            fault["hold_reads"] = False
                            route.continue_()
                    elif fault["hold_reads"] and req.method == "GET" and "/v1/game-builds/" in req.url:
                        route.abort("failed")
                    else:
                        route.continue_()

                context.route("**/*", transport)
                try:
                    require(request(origin, "GET", "/v1/game-builds")[0] == 401, "Anonymous history denied")
                    require(request(origin, "POST", "/v1/game-builds", body={"request_id": "denied", "brief": "A small game"})[0] == 401, "Anonymous submission denied")
                    require(not proposal_calls, "Denied requests never start the proposal fixture")
                    checks.append("Actual HTTP denies anonymous job reads and writes before any proposal")
                    page.goto(origin)
                    connect(page, token)
                    page.locator("#forge-open").click()
                    expect(page.locator("#forge-panel")).to_be_visible()
                    page.locator("#forge-genre-shooter").click()
                    page.locator("#forge-brief").fill("An original signal garden: clear three sentinel waves and recover its beacon")
                    page.locator("#chat-open").click()
                    expect(page.locator("#chat-workspace")).to_be_visible()
                    for control in ("review", "drafts", "rounds"):
                        require(page.locator("#" + control).count() == 1, "Existing chat review controls remain present")
                    page.locator("#forge-open").click()
                    require(page.locator("#forge-brief").input_value().startswith("An original signal garden"), "Switching workspaces preserves the unsent game draft")
                    page.locator("#forge-difficulty").select_option("easy")
                    page.locator("#forge-theme").select_option("neon")
                    page.locator("#forge-encounter").select_option("patrol")
                    page.locator("#forge-speed").fill("230")
                    page.locator("#forge-objective").fill("Recover the garden beacon")
                    expect(page.locator("#forge-submit")).to_be_disabled()
                    page.locator("#forge-review").click()
                    expect(page.locator("#forge-submit")).to_be_enabled()
                    page.locator("#forge-objective").fill("Restore the garden beacon")
                    expect(page.locator("#forge-submit")).to_be_disabled()
                    page.locator("#forge-form").evaluate("node => node.dispatchEvent(new Event('submit', {bubbles:true, cancelable:true}))")
                    expect(page.locator("#status")).to_contain_text("Review the exact")
                    require(not submitted and not proposal_calls, "Unreviewed edits cannot submit a build")
                    page.locator("#forge-review").click()
                    reviewed = page.locator("#forge-reviewed-brief").inner_text()
                    checks.append("Editing and exact review are pure; changing the brief invalidates its review and submission")
                    page.locator("#forge-submit").click()
                    expect(page.locator("#status")).to_contain_text("uncertain")
                    expect(page.locator("#forge-retry-original")).to_be_visible()
                    require(len(submitted) == 1 and submitted[0]["brief"] == reviewed, "Lost acknowledgement retains exact submitted bytes")
                    job_id = submitted[0]["request_id"]
                    page.locator("#forge-brief").fill("Keep this next idea while recovering the original build")
                    expect(page.locator("#forge-retry-original")).to_be_enabled()
                    with page.expect_response(lambda response: response.url == origin + "/v1/game-builds" and response.request.method == "POST") as retry:
                        page.locator("#forge-retry-original").click()
                    require(retry.value.status == 202, "Explicit same-identity retry recovers admission")
                    require(len(submitted) == 2 and submitted[0] == submitted[1], "Only the user-requested exact retry is sent")
                    require(page.locator("#forge-brief").input_value().startswith("Keep this next idea"), "Recovery preserves the edited next draft")
                    checks.append("Lost POST acknowledgement recovers through an explicit frozen-identity retry without replacing the next draft")
                    open_sidebar(page)
                    page.locator("#disconnect").click()
                    require(page.locator("#forge-brief").input_value() == "", "Lock scrubs authored brief")
                    require(page.locator("#forge-current-id").inner_text() == "", "Lock scrubs selected job identity")
                    connect(page, token)
                    page.locator("#forge-open").click()
                    page.locator("#forge-resume-" + job_id).click()
                    deadline = time.monotonic() + 210
                    while True:
                        code, _, saved = request(origin, "GET", "/v1/game-builds/" + job_id, token)
                        require(code == 200, "Original durable build remains readable")
                        current = json.loads(saved)
                        require(current["state"] != "failed", "The real compiler/native build failed: " + str(current.get("error")))
                        if current["terminal"]:
                            break
                        require(time.monotonic() < deadline, "Original build exceeded the observation deadline")
                        page.wait_for_timeout(200)
                    expect(page.locator("#forge-download")).to_be_enabled(timeout=20000)
                    require(len(submitted) == 2 and len(proposal_calls) == 1 and observed["model_calls"] == 0,
                            "Reconnect and exact retry retain one scripted proposal and no model inference")
                    checks.append("Lock scrubs private state; reconnect reopens the original real SQLite job")
                    status, _, raw_job = request(origin, "GET", "/v1/game-builds/" + job_id, token)
                    job = json.loads(raw_job)
                    require(status == 200 and job["state"] == "complete" and job["result"]["planning"]["fixture_only"], "Saved result identifies the scripted proposal")
                    spec = job["result"]["build"]["spec"]
                    require(spec["title"] == "Signal Garden" and spec["gameplay"]["player_speed"] == 230
                            and spec["gameplay"]["theme"] == "neon"
                            and spec["gameplay"]["objective_label"] == "Restore the garden beacon",
                            "Guarded fixture design and explicit user controls reach the actual compiled game")
                    proof = job["result"]["build"]["interactive"]
                    require(proof["native_boot_verified"] and proof["input_journey_verified"], "Real Godot boot and input journey are recorded")
                    require(proof["receipt"]["phase"] == "won" and proof["receipt"]["pause_verified"] and proof["receipt"]["restart_verified"], "Real native input won, paused and restarted")
                    require(any(row["input_replay"] and row["returncode"] == 0 for row in observed["godot_processes"]), "Actual Godot input replay subprocess executed")
                    checks.append("Actual Forge source compilation and installed Godot import/input proof complete under the original job")
                    with page.expect_download() as downloaded:
                        page.locator("#forge-download").click()
                    payload = Path(downloaded.value.path()).read_bytes()
                    report["archive"] = validate_archive(payload, job["archive"])
                    (output / "forge-project.zip").write_bytes(payload)
                    checks.append("Browser download matches immutable SQLite-held ZIP size, digest and confined source entries")
                    require(request(origin, "POST", "/v1/game-builds", token, submitted[0])[0] == 202, "Exact completed replay is read-only")
                    require(request(origin, "POST", "/v1/game-builds", token, {**submitted[0], "brief": reviewed + " changed"})[0] == 409, "Conflicting request reuse is rejected")
                    require(len(proposal_calls) == 1, "Replay and conflict cannot repeat proposal work")
                    checks.append("Exact completed replay performs no new work; changed content under its identity conflicts")
                    page.locator("#forge-current").scroll_into_view_if_needed()
                    screenshot(page, output / "jeeves-forge-fixture-desktop.png")
                    page.reload()
                    connect(page, token)
                    page.locator("#forge-open").click()
                    page.locator("#forge-resume-" + job_id).click()
                    expect(page.locator("#forge-download")).to_be_enabled()
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.locator("#forge-download").scroll_into_view_if_needed()
                    require(page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile has no horizontal page overflow")
                    screenshot(page, output / "jeeves-forge-fixture-mobile.png")
                    require(not page.evaluate("token => Object.values(localStorage).some(value=>value.includes(token))", token), "Bearer token never reaches browser persistence")
                    require(len(submitted) == 2 and len(proposal_calls) == 1 and observed["model_calls"] == 0, "Reload/mobile only read existing work")
                    checks.append("Reload and 390px mobile restore the original archive without persisting tokens or rerunning work")
                    require(not errors and not external, "No page errors or external browser requests")
                    final_source = source_identity()["source_sha256"]
                    final_source[str(Path(__file__).relative_to(ROOT))] = sha256(Path(__file__).read_bytes()).hexdigest()
                    require(final_source == source["source_sha256"], "Product and harness bytes remain stable during qualification")
                    report.update(status="passed", request_id=job_id, native_input_receipt=proof["receipt"])
                except Exception as error:
                    report.update(status="failed", failure=str(error).replace(token, "[redacted]"))
                    try:
                        screenshot(page, output / "jeeves-forge-fixture-failure.png")
                    except Exception:
                        pass
                    raise
                finally:
                    report.update(observed_execution=observed, proposal_fixture_calls=proposal_calls,
                        browser_posts=submitted, external_browser_requests=external,
                        elapsed_seconds=round(time.monotonic() - started, 3))
                    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
                    context.close()
                    browser.close()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--chromium")
    args = parser.parse_args(argv)
    report = qualify(args.output, args.port, args.chromium)
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]),
        "proposal_fixture_calls": len(report["proposal_fixture_calls"]),
        "model_calls": report["observed_execution"]["model_calls"], "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
