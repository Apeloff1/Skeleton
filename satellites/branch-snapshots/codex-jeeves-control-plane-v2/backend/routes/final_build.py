"""Final Build & Packaging API — Vault gamefiles → downloadable build."""
from __future__ import annotations

import io
import threading
import time
import uuid
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from core import final_build

router = APIRouter(prefix="/api/galaxy-studio/final-build", tags=["final-build"])

# ── In-memory streaming-job store for the live CI-style build console. ──
# Jobs are short-lived (the pipeline finishes in well under a minute); we cap
# the store to the 32 most-recent jobs so it never grows unbounded.
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()
_STAGE_DELAY = 0.45  # seconds between stages so the console visibly streams


def _prune_jobs() -> None:
    if len(_JOBS) <= 32:
        return
    for jid in sorted(_JOBS, key=lambda k: _JOBS[k].get("created_at", 0))[:-32]:
        _JOBS.pop(jid, None)


class BuildReq(BaseModel):
    build_id: str = Field(..., min_length=1)
    genre: str = "rpg"
    era: str | None = None
    platforms: list[str] | None = None
    config: dict | None = None
    seed: int = 0
    persist: bool = True


@router.post("/package")
def package(req: BuildReq) -> dict:
    """Run the 7-stage Final Build & Packaging pipeline (verification-gated)."""
    return final_build.build_package(
        build_id=req.build_id, genre=req.genre, era=req.era,
        platforms=req.platforms, config=req.config, seed=req.seed, persist=req.persist)


def _run_job(job_id: str, req: BuildReq) -> None:
    def on_stage(stage: dict) -> None:
        with _JOBS_LOCK:
            j = _JOBS.get(job_id)
            if not j:
                return
            j["stages"].append({
                "step": stage["step"], "stage": stage["stage"],
                "gate": stage["gate"],
                # Explicit per-stage status so streaming consumers can tell a
                # finished stage at a glance ("done" = the stage ran; gate
                # carries pass/fail + score).
                "status": "done",
                "passed": bool(stage.get("gate", {}).get("passed")),
            })
            j["current_step"] = stage["step"]
        # Small pacing delay so the frontend console reveals each stage live.
        time.sleep(_STAGE_DELAY)

    try:
        result = final_build.build_package(
            build_id=req.build_id, genre=req.genre, era=req.era,
            platforms=req.platforms, config=req.config, seed=req.seed,
            persist=req.persist, on_stage=on_stage)
        with _JOBS_LOCK:
            j = _JOBS.get(job_id)
            if j:
                j["status"] = "done"
                j["result"] = result
                j["finished_at"] = time.time()
    except Exception as e:  # noqa: BLE001
        with _JOBS_LOCK:
            j = _JOBS.get(job_id)
            if j:
                j["status"] = "error"
                j["error"] = str(e)[:300]
                j["finished_at"] = time.time()


@router.post("/package/async")
def package_async(req: BuildReq) -> dict:
    """Kick the 7-stage pipeline in a background thread; returns a job_id to
    poll for a live, CI-pipeline-style stream of each stage + gate verdict."""
    job_id = uuid.uuid4().hex[:16]
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "job_id": job_id, "status": "running", "stages": [],
            "current_step": 0, "stages_total": 7,
            "build_id": req.build_id, "created_at": time.time(),
        }
        _prune_jobs()
    threading.Thread(target=_run_job, args=(job_id, req), daemon=True).start()
    return {"job_id": job_id, "status": "running", "stages_total": 7}


@router.get("/job/{job_id}")
def job_status(job_id: str) -> dict:
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
        if not j:
            raise HTTPException(404, "unknown job")
        return dict(j)


@router.get("/{build_id}")
def get_build(build_id: str) -> dict:
    b = final_build.get_final_build(build_id)
    if not b:
        raise HTTPException(404, "no final build yet")
    return b


@router.get("/{build_id}/play")
def play(build_id: str) -> HTMLResponse:
    """Serve the completed, playable game straight from the Vault."""
    g = final_build.get_playable(build_id)
    if not g:
        raise HTTPException(404, "no playable build yet")
    return HTMLResponse(g["html"])


@router.get("/{build_id}/game.zip")
def download_game(build_id: str) -> StreamingResponse:
    """Download the completed game from the Vault as a self-contained, playable
    zip (open index.html in any browser, including Android)."""
    g = final_build.get_playable(build_id)
    if not g:
        raise HTTPException(404, "no playable build in the Vault yet")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", g["html"])
        zf.writestr("game.json", g.get("game_json", "[]"))
        zf.writestr("README.txt",
                    f"{g['title']} ({g['era']})\n\nHOW TO PLAY:\n"
                    f"Open index.html in any browser (works on Android).\n"
                    f"Move with the on-screen D-pad or arrow keys; collect every "
                    f"forged item to win. Entities: {g.get('entities', 0)}.\n")
    buf.seek(0)
    fname = str(g["title"]).replace(" ", "_")[:40] + "_game.zip"
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})
