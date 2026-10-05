"""
routes/galaxy_studio_pipeline.py — Pipeline read sub-router.

Extracted from routes/galaxy_studio.py (Phase-6 decomposition, Feb 2026).
Hosts the 4 batched-file pipeline endpoints used by the frontend to page
through massive (250k+ file) builds:

  GET /pipeline/{build_id}                       — single batch metadata
  GET /pipeline/{build_id}/content               — single batch full content (amplified)
  GET /pipeline/{build_id}/multibatch            — N batches metadata (parallel-friendly)
  GET /pipeline/{build_id}/multibatch/content    — N batches full content

All heavy generators (_generate_batch_files, _get_total_file_count, _amplify)
stay in the parent module — we access them via galaxy_studio_state lazy
proxies so this sub-router never triggers a circular import.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from routes.galaxy_studio_state import (
    load_build,
    get_generate_batch_files,
    get_total_file_count,
    get_amplify,
)

router = APIRouter(tags=["galaxy-studio"])


@router.get("/pipeline/{build_id}")
async def get_pipeline_batch(build_id: str, batch: int = 0, batch_size: int = 5000):
    """Retrieve files in batches. Batch 0 = core files. Subsequent batches = procedural expansion."""
    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    if build["status"] != "completed":
        raise HTTPException(400, f"Build not complete. Status: {build['status']}")

    _gen   = get_generate_batch_files()
    _count = get_total_file_count()

    files = _gen(build, batch, batch_size)
    total_files   = _count(build)
    total_batches = max(1, (total_files + batch_size - 1) // batch_size)

    file_list = []
    for path, content in files.items():
        file_list.append({
            "path":  path,
            "size":  len(content),
            "lines": content.count("\\n") + 1,
            "type":  path.split(".")[-1] if "." in path else "txt",
        })

    return {
        "build_id":       build_id,
        "batch":          batch,
        "batch_size":     batch_size,
        "files_in_batch": len(files),
        "total_files":    total_files,
        "total_batches":  total_batches,
        "has_more":       batch < total_batches - 1,
        "scale":          build.get("scale_info", {}),
        "files":          sorted(file_list, key=lambda f: f["path"]),
    }


@router.get("/pipeline/{build_id}/content")
async def get_pipeline_content(build_id: str, batch: int = 0, batch_size: int = 5000):
    """Get full file content for a batch — AMPLIFIED to 30K+ lines per file."""
    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    if build["status"] != "completed":
        raise HTTPException(400, "Build not complete")

    _gen     = get_generate_batch_files()
    _amplify = get_amplify()

    title = build["title"]
    genre = build["genre"]
    files = _gen(build, batch, batch_size)

    amplified: dict = {}
    for path, content in files.items():
        if isinstance(content, str) and (
            path.endswith(".ts") or path.endswith(".tsx") or path.endswith(".glsl")
        ):
            fname = path.split("/")[-1].replace(".ts", "").replace(".tsx", "").replace(".glsl", "")
            amplified[path] = _amplify(content, fname, title, genre)
        else:
            amplified[path] = content

    return {
        "build_id":   build_id,
        "batch":      batch,
        "file_count": len(amplified),
        "files": {
            path: {
                "content": content,
                "size":    len(content.encode("utf-8") if isinstance(content, str) else content),
            }
            for path, content in amplified.items()
        },
    }


@router.get("/pipeline/{build_id}/multibatch")
async def get_pipeline_multibatch(
    build_id:    str,
    start_batch: int = 0,
    num_batches: int = 5,
    batch_size:  int = 5000,
):
    """Retrieve multiple batches in a single request. Enables parallel/bulk retrieval."""
    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    if build["status"] != "completed":
        raise HTTPException(400, f"Build not complete. Status: {build['status']}")

    _gen   = get_generate_batch_files()
    _count = get_total_file_count()

    total_files   = _count(build)
    total_batches = max(1, (total_files + batch_size - 1) // batch_size)
    num_batches   = min(num_batches, 20)  # Cap at 20 batches per request
    end_batch     = min(start_batch + num_batches, total_batches)

    batches: list[dict] = []
    cumulative_files = 0
    cumulative_size  = 0
    AMPLIFIED_AVG_SIZE  = 1_500_000   # ~1.5 MB per amplified file
    AMPLIFIED_AVG_LINES = 30_000

    for b in range(start_batch, end_batch):
        files = _gen(build, b, batch_size)
        batch_files: list[dict] = []
        batch_size_bytes = 0
        for path, content in files.items():
            base_size  = len(content.encode("utf-8")) if isinstance(content, str) else len(content)
            base_lines = content.count("\n") + 1 if isinstance(content, str) else 0
            amp_size  = max(base_size,  AMPLIFIED_AVG_SIZE)  if path.endswith((".ts", ".tsx", ".glsl")) else base_size
            amp_lines = max(base_lines, AMPLIFIED_AVG_LINES) if path.endswith((".ts", ".tsx", ".glsl")) else base_lines
            batch_files.append({"path": path, "size": amp_size, "lines": amp_lines})
            batch_size_bytes += amp_size

        batches.append({
            "batch":       b,
            "files_count": len(files),
            "size_bytes":  batch_size_bytes,
            "files":       sorted(batch_files, key=lambda f: f["path"]),
        })
        cumulative_files += len(files)
        cumulative_size  += batch_size_bytes

    return {
        "build_id":         build_id,
        "start_batch":      start_batch,
        "end_batch":        end_batch,
        "batch_size":       batch_size,
        "num_batches":      len(batches),
        "total_batches":    total_batches,
        "total_files":      total_files,
        "cumulative_files": cumulative_files,
        "cumulative_size":  cumulative_size,
        "has_more":         end_batch < total_batches,
        "batches":          batches,
    }


@router.get("/pipeline/{build_id}/multibatch/content")
async def get_pipeline_multibatch_content(
    build_id:    str,
    start_batch: int = 0,
    num_batches: int = 3,
    batch_size:  int = 5000,
):
    """Get FULL CONTENT for multiple batches — AMPLIFIED.
    Returns actual amplified file content (200K+ lines per .ts/.tsx/.glsl)."""
    build = await load_build(build_id)
    if not build:
        raise HTTPException(404, "Build not found")
    if build["status"] != "completed":
        raise HTTPException(400, f"Build not complete. Status: {build['status']}")

    _gen     = get_generate_batch_files()
    _count   = get_total_file_count()
    _amplify = get_amplify()

    title = build["title"]
    genre = build["genre"]
    total_files   = _count(build)
    total_batches = max(1, (total_files + batch_size - 1) // batch_size)
    num_batches   = min(num_batches, 10)  # Cap at 10 batches per request (amplified payload size)
    end_batch     = min(start_batch + num_batches, total_batches)

    batches: list[dict] = []
    for b in range(start_batch, end_batch):
        files = _gen(build, b, batch_size)
        amplified: dict = {}
        for path, content in files.items():
            if isinstance(content, str) and (
                path.endswith(".ts") or path.endswith(".tsx") or path.endswith(".glsl")
            ):
                fname = path.split("/")[-1].replace(".ts", "").replace(".tsx", "").replace(".glsl", "")
                amplified[path] = _amplify(content, fname, title, genre)
            else:
                amplified[path] = content
        batches.append({
            "batch":      b,
            "file_count": len(amplified),
            "files": {
                path: {
                    "content": content,
                    "size":    len(content.encode("utf-8") if isinstance(content, str) else content),
                }
                for path, content in amplified.items()
            },
        })

    return {
        "build_id":    build_id,
        "start_batch": start_batch,
        "end_batch":   end_batch,
        "num_batches": len(batches),
        "batches":     batches,
    }
