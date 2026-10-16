"""Actually exercise canonical Director gameplay through localhost HTTP.

Creates a temporary CLONE of approved world source, launches a loopback
service, posts every authored action from verified witness routes, restarts
the server during each route, then verifies restored state and complete
campaign outcomes. No production project save is mutated, no synthetic
evidence is presented as a Godot/human playthrough.
"""
from __future__ import annotations

import http.client
from http.server import HTTPServer
import json
from pathlib import Path
import secrets
import tempfile
import threading
import time
from typing import Any

from skeleton.ai.game_builder.quest_campaign_completion import play_campaign
from skeleton.developer.game_cli import _load
from skeleton.developer.jeeves_game_director_bridge import handler
from skeleton.developer.jeeves_game_director_session import begin, inspect
from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.jeeves.director_loopback_e2e.v1"


def _request(server: HTTPServer, token: str, method: str,
             path: str, body: dict | None = None) -> tuple[int, dict, float]:
    address = "127.0.0.1"
    port = server.server_port
    connection = http.client.HTTPConnection(address, port, timeout=15)
    headers = {"Authorization": "Bearer " + token,
               "Host": address + ":" + str(port),
               "Content-Type": "application/json"}
    begin_at = time.perf_counter()
    try:
        connection.request(method, path, body=json.dumps(body) if body is not None else None,
                           headers=headers)
        response = connection.getresponse()
        payload = response.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError("Director HTTP response exceeds local verification capacity")
        parsed = json.loads(payload.decode("ascii"))
        if not isinstance(parsed, dict):
            raise ValueError("Director bridge returned a non-object response")
        return response.status, parsed, time.perf_counter() - begin_at
    finally:
        connection.close()


class _Service:
    def __init__(self, root: Path, session: str, token: str):
        self.root, self.session, self.token = root, session, token
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.server is not None:
            raise ValueError("Director E2E service already started")
        self.server = HTTPServer(("127.0.0.1", 0), handler(
            self.root, self.session, self.token, 0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.server is None:
            return
        server, thread = self.server, self.thread
        self.server, self.thread = None, None
        server.shutdown()
        if thread is not None:
            thread.join(timeout=5)
            if thread.is_alive():
                server.server_close()
                raise ValueError("Director local HTTP service did not terminate")
        server.server_close()

    def request(self, method: str, path: str,
                body: dict | None = None) -> tuple[int, dict, float]:
        if self.server is None:
            raise ValueError("Director bridge not running")
        return _request(self.server, self.token, method, path, body)


def _mirror(root: Path, source: str, scratch: Path) -> str:
    """Copy only approved config and Director source to an isolated test root."""
    from skeleton.developer.jeeves_game_quality import _read
    from hashlib import sha256
    _load(root)
    packet, original_sha = _read(root, source, 16 * 1024 * 1024)
    manifest = root / "skeleton.game.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("unsafe game manifest for isolated E2E")
    (scratch / "design").mkdir(parents=True)
    (scratch / "skeleton.game.json").write_bytes(manifest.read_bytes())
    (scratch / "design" / "director_campaign_source.json").write_text(
        json.dumps(packet, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8")
    _load_world(scratch, "design/director_campaign_source.json")
    if _read(root, source, 16 * 1024 * 1024)[1] != original_sha:
        raise ValueError("Director source changed during isolated E2E setup")
    return "design/director_campaign_source.json"


def run(root: Path, *, source: str, routes: int = 2) -> dict[str, Any]:
    """Execute selected complete authored routes, with a genuine HTTP restart."""
    if type(routes) is not int or not 1 <= routes <= 8:
        raise ValueError("local full-campaign HTTP E2E requires 1..8 route strategies")
    world, original_sha = _load_world(root, source)
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="skeleton-director-e2e-") as directory:
        sandbox = Path(directory) / "game"
        path = _mirror(root, source, sandbox)
        clone, _ = _load_world(sandbox, path)
        if clone.digest != world.digest:
            raise ValueError("isolated Director game source differs from original")
        for route in range(routes):
            session = "automated_route_" + str(route)
            initial = begin(sandbox, source=path, session=session)
            witness = play_campaign(world, preference=route,
                                    include_optional=route % 2 == 0,
                                    segment_size=256)
            actions = [step for chunk in witness.replay["segments"]
                       for step in chunk["actions"]]
            if not actions:
                raise ValueError("empty game route cannot establish E2E coverage")
            token = secrets.token_urlsafe(36)
            service = _Service(sandbox, session, token)
            count = 0
            milliseconds = 0.0
            restart_completed = False
            first_state = None
            try:
                service.start()
                status, doc, elapsed = service.request("GET", "/v1/status")
                milliseconds += elapsed * 1000
                if status != 200 or doc.get("snapshot", {}).get("sequence") != 0:
                    raise ValueError("game HTTP status failed before first real action")
                snapshot = doc["snapshot"]
                for index, action in enumerate(actions):
                    posted = {
                        "choice": action["kind"] + ":" + action["key"],
                        "expected_sequence": snapshot["sequence"],
                        "expected_state_sha256": snapshot["current_state_sha256"],
                    }
                    status, doc, elapsed = service.request(
                        "POST", "/v1/actions", posted)
                    milliseconds += elapsed * 1000
                    if status != 200 or not doc.get("ok"):
                        raise ValueError("HTTP action rejected during playable route " + str(index))
                    new_state = doc["snapshot"]
                    if new_state["sequence"] != index + 1:
                        raise ValueError("real HTTP replay sequence differs from expected action")
                    if doc.get("presentation_warning") is not None:
                        raise ValueError("authored cinematic delta failed during HTTP playthrough")
                    snapshot = new_state
                    count += 1
                    if index == 0:
                        first_state = posted
                    if count == max(1, len(actions) // 2):
                        service.stop()
                        service.start()
                        status, reloaded, elapsed = service.request("GET", "/v1/status")
                        milliseconds += elapsed * 1000
                        # A POST snapshot has action=director-session-step;
                        # a resumed GET has action=director-session-status. This
                        # metadata differs, the canonical state must not.
                        restored = reloaded.get("snapshot", {})
                        if (status != 200 or not isinstance(restored, dict)
                                or {k: v for k, v in restored.items() if k != "action"}
                                != {k: v for k, v in snapshot.items() if k != "action"}):
                            raise ValueError("Director HTTP save recovery changed gameplay state")
                        restart_completed = True
                if first_state is not None:
                    status, _, elapsed = service.request(
                        "POST", "/v1/actions", first_state)
                    milliseconds += elapsed * 1000
                    if status != 409:
                        raise ValueError("stale replay was not rejected after campaign completion")
                status, final_doc, elapsed = service.request("GET", "/v1/status")
                milliseconds += elapsed * 1000
                if status != 200:
                    raise ValueError("final completed game HTTP state was not readable")
            finally:
                service.stop()
            final = inspect(sandbox, session=session)
            canonical = witness.report
            if (not final["complete"] or not restart_completed
                    or final["sequence"] != canonical["action_count"]
                    or final["current_state_sha256"] != canonical["final_director_state_sha256"]
                    or final_doc["snapshot"] != final
                    or len(final["quest_stage_results"]) != canonical["stages_completed"]):
                raise ValueError("real HTTP game route failed canonical completion/recovery parity")
            results.append({
                "route": route, "action_count": count,
                "http_status_recovery_verified": restart_completed,
                "source_replay_parity_verified": True,
                "stale_post_rejected": True,
                "complete_campaign": final["complete"],
                "all_stage_results": len(final["quest_stage_results"]),
                "final_state_sha256": final["current_state_sha256"],
                "approx_http_round_trip_ms_total": round(milliseconds, 2),
            })
    return {
        "ok": True, "schema": SCHEMA, "action": "director-loopback-e2e",
        "project": world.project_id, "source_sha256": original_sha,
        "world_sha256": world.digest, "route_count": routes,
        "all_routes_completed_over_real_http": len(results) == routes,
        "actual_service_restart_and_journal_recovery_tested": True,
        "results": results, "isolated_source_and_sessions_cleaned_up": True,
        "local_socket_transport_verified": True,
        "godot_binary_executed": False, "physical_controller_verified": False,
        "human_player_tested": False, "native_graphical_game_finished": False,
    }
