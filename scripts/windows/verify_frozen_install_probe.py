"""Actual installed-console readiness protocol acceptance, without Docker."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading

FLAG = "--internal-install-probe-v1"
TOKEN = "fixture-bearer-not-a-credential-12345"
SCHEMA = "skeleton.game.studio_readiness.v1"
PATH = "/api/game-studio-health"


@contextmanager
def fixture_server():
    events = []
    mode = {"value": "ok"}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass
        def do_GET(self):
            events.append((self.path, self.headers.get("Authorization")))
            value = mode["value"]
            if value == "redirect":
                self.send_response(302)
                self.send_header("Location", "/other")
                self.end_headers()
                return
            payload = {"schema_version": SCHEMA, "status": "ready"}
            if value == "reflect":
                payload["secret"] = TOKEN
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", events, mode
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def qualify(root: Path):
    exe = root / "SkeletonOffline.exe"
    if not exe.is_file():
        raise RuntimeError("installed readiness console missing")
    env = {key: os.environ[key] for key in ("SYSTEMROOT","WINDIR","TEMP","TMP","PATH")
           if key in os.environ}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    env["HTTP_PROXY"] = "http://127.0.0.1:1"
    env["HTTPS_PROXY"] = "http://127.0.0.1:1"
    env["NO_PROXY"] = ""
    def child(packet):
        done = subprocess.run([str(exe), FLAG], cwd=root, input=packet,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=60, env=env, check=False)
        if TOKEN.encode() in done.stdout or TOKEN.encode() in done.stderr:
            raise RuntimeError("fixture credential reflected by frozen worker")
        return done
    with fixture_server() as (base, events, mode):
        request = {"base": base,"token": TOKEN,"timeout": 5,"endpoint": PATH,
                   "schema": SCHEMA,"max_response_bytes": 65536}
        packet = json.dumps(request).encode()
        for scenario in ("ok","redirect","reflect"):
            mode["value"] = scenario
            done = child(packet)
            if done.returncode != 0:
                raise RuntimeError("frozen readiness protocol unavailable")
            output = json.loads(done.stdout)
            if output.get("observed") is not (scenario == "ok"):
                raise RuntimeError("unexpected frozen readiness verdict")
        if events != [(PATH, "Bearer "+TOKEN)]*3:
            raise RuntimeError("frozen worker transport violated fixture contract")
        invalid = dict(request, endpoint="/other")
        done = child(json.dumps(invalid).encode())
        if done.returncode != 2 or done.stdout or len(events) != 3:
            raise RuntimeError("frozen worker admitted an unsupported endpoint")
    # Source-only acceptance must not be mistaken for Docker or device proof.
    print("Frozen readiness worker: PASS (loopback transport, denial, reflection; fixture only)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--install-root", type=Path, required=True)
    qualify(parser.parse_args().install_root.resolve(strict=True))
