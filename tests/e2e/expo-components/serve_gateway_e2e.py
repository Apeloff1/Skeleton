"""E2E host for the /new-game harness: the real backend forge gateway plus the static bundle.

Same-origin by design (the app's apiBase uses the page origin on web). The
engine runs as its own process; point FORGE_GATEWAY_ENGINE_URL at it and share
GF_SEAL_SECRET. Local/CI use only: auth is the backend's development mode.

    python serve_gateway_e2e.py --static <dir> --port 8722
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))


def build_app(static_dir: Path):
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from routes.forge_gateway import router

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/app.js")
    def bundle() -> FileResponse:
        return FileResponse(static_dir / "app.js", media_type="text/javascript")

    @app.get("/{_path:path}")
    def page(_path: str) -> FileResponse:
        return FileResponse(static_dir / "index.html", media_type="text/html")

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--static", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8722)
    args = parser.parse_args()
    uvicorn.run(build_app(args.static.resolve()), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
