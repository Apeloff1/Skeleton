"""Consent-gated visual Dragon observation of the GENERATED game canvas only.

An operator may opt in to real headless Chromium capture of original artwork
and gameplay. This does not capture the user's desktop, webcam, personal
applications or browser history. The capture cannot automatically enter model
training or approved Dragon knowledge. It is local and source-bound.
"""
from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile

from .contracts import canonical_digest
from .studio_runtime_qualification import _inputs

SCHEMA = "skeleton.game_builder.dragon_generated_canvas_capture.v1"
_MAX_ACTIONS = 20_000
_MAX_FRAMES = 3
_MAX_IMAGE = 1_000_000


class DragonCanvasCaptureError(ValueError):
    """Real generated-game pixel capture or consent evidence is not valid."""


def _png_geometry(image: bytes) -> tuple[int, int]:
    if (type(image) is not bytes or len(image) < 33 or len(image) > _MAX_IMAGE
            or not image.startswith(b"\x89PNG\r\n\x1a\n")
            or image[12:16] != b"IHDR"):
        raise DragonCanvasCaptureError("browser did not render a bounded PNG framebuffer")
    width, height = struct.unpack(">II", image[16:24])
    if not 1 <= width <= 2048 or not 1 <= height <= 2048:
        raise DragonCanvasCaptureError("canvas screenshot pixel size exceeds original game limits")
    return width, height


def capture_generated_game(
    engines: str | Path, destination: str | Path, *,
    authorized: bool, capture_consent: bool,
    execute: bool, timeout_seconds: int = 60,
) -> dict:
    """Capture at most three actual canvas frames during a real winning run."""
    if authorized is not True or capture_consent is not True:
        raise PermissionError("specific consent required for generated game canvas capture")
    if execute is not True:
        raise DragonCanvasCaptureError("a real graphical browser run requires execution opt-in")
    if type(timeout_seconds) is not int or not 5 <= timeout_seconds <= 120:
        raise DragonCanvasCaptureError("capture run needs bounded local time")
    root = Path(engines)
    html, data, world = _inputs(root)
    proof = json.loads(data)
    actions = proof["actions"]
    if not 1 <= len(actions) <= _MAX_ACTIONS:
        raise DragonCanvasCaptureError("original game trace outside capture work budget")
    dest = Path(destination)
    if dest.exists() or dest.is_symlink() or not dest.parent.is_dir() or dest.parent.is_symlink():
        raise DragonCanvasCaptureError("new private capture directory required")
    if importlib.util.find_spec("playwright") is None:
        return {
            "schema": SCHEMA, "framebuffer_recorded": False,
            "blocker": "playwright_not_available",
            "model_training_authorized": False,
            "user_screen_recorded": False,
        }
    # The source is an already SHA-checked standalone game. A browser is not
    # a security sandbox; the operator owns and authorizes the source project.
    from playwright.sync_api import sync_playwright

    stage = Path(tempfile.mkdtemp(prefix=".dragon-canvas-", dir=dest.parent))
    try:
        with sync_playwright() as runner:
            browser = runner.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    offline=True, java_script_enabled=True,
                    permissions=[], service_workers="block",
                    viewport={"width": 900, "height": 720},
                )
                page = context.new_page()
                page.goto((root / "index.html").resolve().as_uri(),
                          wait_until="load", timeout=timeout_seconds * 1000)
                # Every move goes through the real DOM controller listener.
                script = """moves => {
                  for(const value of moves) {
                    const keys={up:'ArrowUp',down:'ArrowDown',
                                left:'ArrowLeft',right:'ArrowRight'};
                    document.dispatchEvent(new KeyboardEvent('keydown',
                      {code:keys[value],bubbles:true}));
                  }
                  return {status:state.status,steps:state.steps,score:state.score,
                          health:state.health,x:state.x,y:state.y,level:state.level};
                }"""
                checkpoints = sorted({0, max(1, len(actions) // 2), len(actions)})
                files: dict[str, bytes] = {}
                position = 0
                final = None
                for index, checkpoint in enumerate(checkpoints):
                    section = actions[position:checkpoint]
                    final = page.evaluate(script, section)
                    position = checkpoint
                    screenshot = page.locator("#screen").screenshot(
                        type="png", timeout=timeout_seconds * 1000,
                    )
                    dimensions = _png_geometry(screenshot)
                    files[f"frame_{index:02d}.png"] = screenshot
                    if dimensions != (proof["final_state"].get("width", dimensions[0]),
                                      proof["final_state"].get("height", dimensions[1])):
                        raise DragonCanvasCaptureError("source canvas changed dimensions")
                state = proof["final_state"]
                if (final["status"] != "won" or final["status"] != state["status"]
                        or final["steps"] != state["steps"] or final["score"] != state["score"]
                        or final["health"] != state["health"] or final["level"] != state["level_index"]
                        or final["x"] != state["x"] or final["y"] != state["y"]):
                    raise DragonCanvasCaptureError("rendered graphical game diverged from Python replay")
                if page.locator("#progress").inner_text() != "Victory":
                    raise DragonCanvasCaptureError("actual browser UI did not report victory")
                context.close()
            finally:
                browser.close()
        if len(files) > _MAX_FRAMES or len({sha256(data).hexdigest() for data in files.values()}) < 2:
            raise DragonCanvasCaptureError("generated graphical frames do not show distinct gameplay")
        body = {
            "schema": SCHEMA, "world_digest": world,
            "html_sha256": sha256(html).hexdigest(),
            "proof_sha256": sha256(data).hexdigest(),
            "action_count": len(actions), "consent": "explicit_original_canvas_only",
            "frames": {name: {"sha256": sha256(blob).hexdigest(), "bytes": len(blob)}
                       for name, blob in sorted(files.items())},
            "source": "actual_local_headless_browser_canvas_screenshots",
            "graphical_browser_pixels_observed": True,
            "user_screen_recorded": False, "model_training_authorized": False,
            "dragon_knowledge_promoted": False,
            "human_gameplay_or_hardware_qualified": False,
            "release_authorized": False,
        }
        record = {**body, "capture_digest": canonical_digest(body)}
        for name, blob in files.items():
            with (stage / name).open("xb") as handle:
                handle.write(blob)
        with (stage / "capture.json").open("xb") as handle:
            handle.write((json.dumps(record, sort_keys=True, indent=2) + "\n").encode())
        if dest.exists() or dest.is_symlink():
            raise DragonCanvasCaptureError("another capture appeared during publication")
        os.rename(stage, dest)
        return {**record, "output": str(dest)}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


__all__ = ["DragonCanvasCaptureError", "capture_generated_game"]
