"""Exercise the real localhost Jeeves workspace in Chromium.

Run from a checkout with NumPy and Playwright installed::

    python scripts/qualify_jeeves_workspace_browser.py --output /tmp/jeeves-browser

This uses an actual, deliberately untrained TinyTransformer and private SQLite
database. It proves browser/API/storage integration, not useful language quality,
an operator GGUF installation, native-device qualification or competitor parity.
No bearer token, conversation backup or source document is written to artifacts.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import platform
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TESTED_SOURCES = (
    "skeleton/app/offline_web.py",
    "skeleton/app/offline_http.py",
    "skeleton/app/local_ai.py",
    "skeleton/app/offline_grounding.py",
    "skeleton/app/offline_knowledge.py",
    "skeleton/ai/model_runtime/offline_chat.py",
    "scripts/qualify_jeeves_workspace_browser.py",
)


def source_identity() -> dict:
    """Bind tested source bytes even when working on an uncommitted draft."""
    return {
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
        ).strip(),
        "tracked_tree_dirty": bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True,
        ).strip()),
        "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in TESTED_SOURCES},
    }


@contextmanager
def local_service(database: Path, token: str):
    """Run the production HTTP handler and actual model adapter, without mocks."""
    from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
    from skeleton.ai.runtime.inference.native_runtime import NativeRuntimeLocalModel
    from skeleton.app.offline_http import LocalOnlyHTTPServer, OfflineHTTPApplication
    from skeleton.cortex.transformer import TinyTransformer

    model = NativeRuntimeLocalModel(NativeLLMRuntime(TinyTransformer(
        vocab=("system:", "user:", "assistant:", "hello", "world", "answer",
               "local", "offline", "jeeves", "computer", ".", " "),
        dim=8, ctx=1024, seed=41, n_heads=2, n_layers=2, d_ff=16,
    )))
    app = OfflineHTTPApplication(model, database, token=token)
    server = LocalOnlyHTTPServer(app)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield app, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        worker.join(timeout=10)
        server.server_close()
        app.close()


def require(condition: bool, description: str) -> None:
    if not condition:
        raise AssertionError(description)


def open_details(page, identifier: str) -> None:
    details = page.locator("#" + identifier)
    if details.count() and not details.evaluate("node => node.open"):
        details.locator("summary").first.click()


def open_sidebar(page) -> None:
    if page.viewport_size["width"] <= 720:
        toggle = page.locator("#sidebar-toggle")
        if toggle.get_attribute("aria-expanded") != "true":
            toggle.click()


def close_sidebar(page) -> None:
    if page.viewport_size["width"] <= 720:
        close = page.locator("#sidebar-close")
        if close.is_visible():
            close.click()


def connect(page, token: str) -> None:
    from playwright.sync_api import expect

    open_sidebar(page)
    page.locator("#secret").fill(token)
    page.locator("#connect").click()
    expect(page.locator("#connect")).to_be_disabled()
    expect(page.locator("#disconnect")).to_be_enabled()
    require(page.locator("#secret").input_value() == "", "token input cleared after connect")


def wait_ready(page) -> None:
    from playwright.sync_api import expect

    expect(page.locator("#send")).to_be_enabled()


def select_session(page, sid: str) -> None:
    from playwright.sync_api import expect

    open_sidebar(page)
    page.locator(f'[data-session="{sid}"]').click()
    expect(page.locator(".session.active")).to_have_attribute("data-session", sid)
    close_sidebar(page)


def screenshot(page, destination: Path) -> None:
    # Mask even an unexpectedly retained input before capturing failure evidence.
    page.screenshot(path=str(destination), full_page=True, mask=[page.locator("#secret")],
                    mask_color="#1b2230")


def qualify(output: Path, executable: str | None = None) -> dict:
    from playwright.sync_api import expect, sync_playwright

    output = output.expanduser().resolve()
    require(not output.is_relative_to(ROOT), "browser artifacts must be outside the source checkout")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    checks: list[str] = []
    errors: list[str] = []
    outgoing: list[str] = []
    started = time.monotonic()
    token = secrets.token_urlsafe(48)
    report = {
        "schema": "skeleton.jeeves.workspace-browser-qualification.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "mode": "actual-untrained-native-transformer-and-private-sqlite",
        "production_model_quality_qualified": False,
        "source": source_identity(),
        "environment": {"python": platform.python_version(), "platform": platform.platform(),
                        "viewports": [{"width": 1440, "height": 1000}, {"width": 390, "height": 844}]},
        "network_observation_scope": "browser requests only; whole-process egress not measured",
        "checks": checks,
        "errors": errors,
    }
    with tempfile.TemporaryDirectory(prefix="jeeves-workspace-") as private, sync_playwright() as pw:
        database = Path(private) / "workspace.sqlite3"
        selected_executable = executable or shutil.which("chromium") or shutil.which("chromium-browser")
        options = {"headless": True}
        if selected_executable:
            options["executable_path"] = selected_executable
        browser = pw.chromium.launch(**options)
        report["environment"]["browser"] = browser.version
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(15000)
        page.on("pageerror", lambda error: errors.append(str(error).replace(token, "[redacted]")))
        allowed_origin = {"value": ""}
        delivery_fault = {"drop_next_turn": False, "dropped": 0, "request": None}
        metadata_refresh_fault = {"armed": False, "drop_search": False,
                                  "dropped": 0, "metadata_posts": 0}

        def local_requests_only(route):
            url = route.request.url
            if urlsplit(url).netloc != urlsplit(allowed_origin["value"]).netloc:
                outgoing.append(urlsplit(url).scheme + "://" + urlsplit(url).netloc)
                route.abort()
            elif metadata_refresh_fault["armed"] and route.request.method == "POST" and url.endswith("/metadata"):
                # Deliver the authentic committed mutation, then fail only its
                # subsequent derived summaries read. Do not fake either result.
                response = route.fetch()
                require(response.status == 200, "rename genuinely committed before list refresh failure")
                metadata_refresh_fault["metadata_posts"] += 1
                metadata_refresh_fault["drop_search"] = True
                route.fulfill(response=response)
            elif metadata_refresh_fault["drop_search"] and route.request.method == "POST" and url.endswith("/sessions/search"):
                metadata_refresh_fault["drop_search"] = False
                metadata_refresh_fault["dropped"] += 1
                route.abort("failed")
            elif delivery_fault["drop_next_turn"] and route.request.method == "POST" and url.endswith("/turns"):
                # Let the genuine request reach the genuine server, then lose
                # only its HTTP delivery. Recovery must use the original ID.
                delivery_fault["drop_next_turn"] = False
                delivery_fault["request"] = route.request.post_data_json
                response = route.fetch()
                require(response.status in (200, 202), "real turn admitted before response loss")
                delivery_fault["dropped"] += 1
                route.abort("failed")
            else:
                route.continue_()

        context.route("**/*", local_requests_only)
        try:
            with local_service(database, token) as (app, origin):
                report["fixture_model_digest"] = app.model_digest
                allowed_origin["value"] = origin
                page.goto(origin)
                require(page.locator("#send").is_disabled(), "locked workspace disables generation")
                connect(page, token)
                checks.append("authenticated connection; token input scrubbed")
                page.locator("#new").click()
                wait_ready(page)
                sid = page.locator(".session.active").get_attribute("data-session")
                require(bool(sid), "new conversation has a durable identifier")
                open_details(page, "generation-options")
                page.locator("#budget").fill("2")
                page.locator("#prompt").fill("hello offline")
                page.locator("#send").click()
                expect(page.locator("#messages .assistant")).to_have_count(1)
                wait_ready(page)
                _, saved = app.dispatch("GET", "/v1/sessions/" + sid)
                require(saved["revision"] == 1 and len(saved["messages"]) == 2,
                        "actual local answer committed once to SQLite")
                checks.append("actual native inference through browser; one durable committed turn")

                delivery_fault["drop_next_turn"] = True
                page.locator("#prompt").fill("hello world")
                page.locator("#send").click()
                expect(page.locator("#messages .assistant")).to_have_count(2, timeout=15000)
                wait_ready(page)
                require(delivery_fault["dropped"] == 1, "response loss actually injected after server admission")
                _, saved = app.dispatch("GET", "/v1/sessions/" + sid)
                require(saved["revision"] == 2 and len(saved["messages"]) == 4,
                        "uncertain delivery recovered exactly one additional answer")
                replay_status, replay = app.dispatch("POST", "/v1/sessions/" + sid + "/turns",
                                                    delivery_fault["request"])
                require(replay_status == 200 and replay["state"] == "complete"
                        and replay["result"]["replayed"] is True,
                        "same original request replays without another model invocation")
                checks.append("lost HTTP response recovered by polling; original ID replays without duplicate turn")

                page.locator("#session-title-open").click()
                page.locator("#session-title-input").fill("Harbor research workspace")
                metadata_refresh_fault["armed"] = True
                page.locator("#session-title-save").click()
                expect(page.locator("#conversation-title")).to_have_text("Harbor research workspace")
                expect(page.locator("#session-title-dialog")).to_be_hidden()
                expect(page.locator("#status")).to_contain_text("Conversation title saved.")
                expect(page.locator("#status")).to_contain_text("Choose Search to retry.")
                require(metadata_refresh_fault["dropped"] == 1
                        and metadata_refresh_fault["metadata_posts"] == 1,
                        "one genuine rename and exactly one failed derived list refresh")
                _, renamed = app.dispatch("GET", "/v1/sessions/" + sid)
                require(renamed["title"] == "Harbor research workspace" and renamed["metadata_revision"] == 1,
                        "confirmed rename remains durably saved despite list read failure")
                with page.expect_response(lambda response: response.url.endswith("/sessions/search")) as refreshed:
                    page.locator("#session-search").click()
                require(refreshed.value.status == 200, "explicit Search retries the list read successfully")
                expect(page.locator(f'[data-session="{sid}"] .session-title')).to_have_text("Harbor research workspace")
                require(metadata_refresh_fault["metadata_posts"] == 1,
                        "list recovery never resubmits stale metadata CAS mutation")
                metadata_refresh_fault["armed"] = False
                checks.append("confirmed rename survives failed list refresh; Search recovers without mutation retry")
                page.locator("#session-pin").click()
                expect(page.locator("#session-pin")).to_have_attribute("aria-pressed", "true")
                _, organized = app.dispatch("GET", "/v1/sessions/" + sid)
                require(organized["title"] == "Harbor research workspace" and organized["pinned"] is True,
                        "title and pin persisted")
                require(organized["revision"] == 2 and organized["messages"] == saved["messages"],
                        "organization does not rewrite committed transcript")
                checks.append("rename and pin persisted without transcript mutation")

                open_details(page, "reference-library")
                page.locator("#knowledge-file").set_input_files({
                    "name": "harbor-reference.txt", "mimeType": "text/plain",
                    "buffer": b"The harbor signal is amber. The harbor gate opens at sunrise.",
                })
                expect(page.locator(".knowledge-record")).to_have_count(1)
                page.locator(".knowledge-scope-picker").check()
                page.locator("#grounded").check()
                page.locator("#prompt").fill("What is the harbor signal?")
                with page.expect_response(lambda response: response.url.endswith("/context-preview")) as previewed:
                    page.locator("#context-preview").click()
                preview = previewed.value.json()
                require(previewed.value.status == 200 and preview["generation_performed"] is False,
                        "grounded context preview is read-only")
                require(preview.get("grounding_preview", {}).get("citations"), "selected source yields exact passages")
                _, unchanged = app.dispatch("GET", "/v1/sessions/" + sid)
                require(unchanged["revision"] == 2, "context preview creates no completed turn")
                checks.append("source file import; explicit source scope; read-only grounding preview")
                page.once("dialog", lambda dialog: dialog.accept())
                page.locator(".knowledge-record").get_by_role("button", name="Remove", exact=True).click()
                expect(page.locator(".knowledge-record")).to_have_count(0)
                expect(page.locator("#send")).to_be_disabled()
                require("selected" in page.locator("#knowledge-scope-status").inner_text().lower(),
                        "missing selected source remains an explicit restriction")
                page.locator("#knowledge-scope-reset").click()
                checks.append("deleting selected source blocks generation until explicit scope reset")
                page.locator("#grounded").uncheck()
                page.locator("#prompt").fill("")
                if page.locator("#context-grounding-preview").count():
                    page.locator("#context-grounding-preview").evaluate("node => node.open = false")
                page.locator("#reference-library").evaluate("node => node.open = false")

                with page.expect_download() as downloaded:
                    open_details(page, "conversation-tools")
                    page.locator("#export").click()
                backup_path = Path(downloaded.value.path())
                bundle = json.loads(backup_path.read_text())
                require(bundle["body"]["revision"] == 2, "downloaded backup contains committed turns")
                require(bundle["body"]["schema"] == "skeleton.ai.offline-chat-bundle.v3"
                        and bundle["body"]["metadata"]["title"] == "Harbor research workspace"
                        and bundle["body"]["metadata"]["pinned"] is True,
                        "v3 download preserves explicit title and pin")
                with page.expect_response(lambda response: response.url.endswith("/v1/sessions/import")) as imported:
                    page.locator("#import").set_input_files({
                        "name": "private-backup.json", "mimeType": "application/json",
                        "buffer": backup_path.read_bytes(),
                    })
                imported_sid = imported.value.json()["session_id"]
                expect(page.locator(".session.active")).to_have_attribute("data-session", imported_sid)
                require(imported_sid != sid, "backup import creates an independent session")
                _, restored_backup = app.dispatch("GET", "/v1/sessions/" + imported_sid)
                require(restored_backup["revision"] == 2 and restored_backup["title"] == "Harbor research workspace"
                        and restored_backup["pinned"] is True and restored_backup["messages"] == saved["messages"],
                        "browser backup import restores exact transcript and organization")
                select_session(page, sid)
                checks.append("v3 private backup download and browser import preserve history, title and pin")

                page.locator("#session-archive").click()
                expect(page.locator("#session-archive")).to_be_enabled()
                open_sidebar(page)
                page.locator("#session-view-archived").click()
                page.locator(f'[data-session="{sid}"]').wait_for()
                select_session(page, sid)
                page.locator("#session-archive").click()
                expect(page.locator("#session-archive")).to_be_enabled()
                open_sidebar(page)
                page.locator("#session-view-active").click()
                select_session(page, sid)
                checks.append("archive, discover archived conversation, restore and reopen")

                page.reload()
                require(page.locator("#send").is_disabled(), "reload requires explicit authentication")
                connect(page, token)
                select_session(page, sid)
                require(page.locator("#messages .assistant").count() == 2, "reload retains committed replies")
                require(page.locator("#conversation-title").inner_text() == "Harbor research workspace",
                        "reload retains title")
                checks.append("reload, explicit reconnect and durable conversation recovery")
                screenshot(page, output / "jeeves-desktop.png")

            # Recreate both service and store against the same private database.
            with local_service(database, token) as (restarted, origin):
                require(restarted.model_digest == report["fixture_model_digest"],
                        "restart uses the same fixture model identity")
                allowed_origin["value"] = origin
                page.goto(origin)
                connect(page, token)
                select_session(page, sid)
                _, recovered = restarted.dispatch("GET", "/v1/sessions/" + sid)
                require(recovered["revision"] == 2 and recovered["pinned"] is True,
                        "service restart preserves transcript and organization")
                checks.append("service/store restart; committed answer and metadata recovered")
                open_details(page, "generation-options")
                page.locator("#budget").fill("2")
                page.locator("#prompt").fill("hello local")
                page.locator("#send").click()
                expect(page.locator("#messages .assistant")).to_have_count(3)
                wait_ready(page)
                _, continued = restarted.dispatch("GET", "/v1/sessions/" + sid)
                require(continued["revision"] == 3, "third actual model turn commits after service restart")
                checks.append("third genuine model turn after service restart continues recovered history")

                page.set_viewport_size({"width": 390, "height": 844})
                close_sidebar(page)
                page.locator("#prompt").focus()
                require(page.locator("#prompt").evaluate("node => document.activeElement === node"),
                        "mobile composer receives keyboard focus")
                page.keyboard.press("Tab")
                require(page.evaluate("() => document.activeElement !== document.body"), "keyboard focus stays in controls")
                require(page.evaluate("() => document.documentElement.scrollWidth <= innerWidth"),
                        "mobile viewport has no horizontal document overflow")
                send = page.locator("#send").bounding_box()
                require(bool(send) and send["x"] >= 0 and send["x"] + send["width"] <= 390
                        and send["y"] >= 0 and send["y"] + send["height"] <= 844,
                        "mobile primary action is inside the viewport")
                screenshot(page, output / "jeeves-mobile.png")
                checks.append("390px mobile layout; visible primary action; keyboard focus")
                open_sidebar(page)
                page.locator("#disconnect").click()
                require(page.locator("#messages .message").count() == 0, "lock scrubs visible transcript")
                require(page.locator("#prompt").input_value() == "", "lock scrubs draft")
                require(page.locator("#send").is_disabled(), "lock denies generation")
                require(page.evaluate("() => localStorage.length === 0 && sessionStorage.length === 0"),
                        "no private text or token persisted in browser storage")
                checks.append("lock clears transcript/draft; no localStorage or sessionStorage")
            require(not errors, "no browser page errors")
            require(not outgoing, "all browser requests stayed on the active numeric-loopback origin")
            require(source_identity()["source_sha256"] == report["source"]["source_sha256"],
                    "tested product sources remained unchanged throughout browser qualification")
            checks.append("no page crashes or external browser network requests")
            report["status"] = "passed"
        except Exception as error:
            report["status"] = "failed"
            report["failure"] = str(error).replace(token, "[redacted]")
            try:
                screenshot(page, output / "jeeves-failure.png")
            except Exception:
                pass
            raise
        finally:
            report["elapsed_seconds"] = round(time.monotonic() - started, 3)
            report["external_request_count"] = len(outgoing)
            (output / "jeeves-browser-report.json").write_text(json.dumps(report, indent=2) + "\n")
            context.close()
            browser.close()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/workspace/artifacts/jeeves-workspace"))
    parser.add_argument("--chromium", help="Optional installed Chromium executable")
    args = parser.parse_args()
    try:
        report = qualify(args.output, args.chromium)
    except Exception:
        print("Jeeves browser qualification FAILED; inspect the redacted JSON report.", file=sys.stderr)
        return 1
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]),
                      "report": str(args.output / "jeeves-browser-report.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
