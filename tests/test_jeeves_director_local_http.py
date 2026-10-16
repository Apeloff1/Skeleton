"""Local HTTP gameplay bridge contract (no external network dependencies)."""
from __future__ import annotations

import http.client
from http.server import HTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.quest_scene_forge import forge_director
from skeleton.developer.game_cli import SCHEMA as GAME_SCHEMA
from skeleton.developer.jeeves_game_director_session import begin
from skeleton.developer.jeeves_game_director_bridge import handler


class LocalGameplayHTTPTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name) / "game"
        root.mkdir()
        (root / "design").mkdir()
        (root / "skeleton.game.json").write_text(json.dumps({
            "schema": GAME_SCHEMA, "name": "game", "vision": "New world",
            "era": "extraction_now", "archetype": "auto",
        }))
        world = forge_director(
            "game", seed=2, regions=("north", "east", "south", "west"),
            quest_types=("main_story",), stages=2,
        )
        source = "design/director_campaign_source.json"
        (root / source).write_text(json.dumps({
            "schema": "skeleton.jeeves.director_campaign_source.v1",
            "author_review_acknowledged": True, "director_world": world.payload(),
        }))
        begin(root, source=source, session="play")
        self.token = "x" * 40
        self.server = HTTPServer(("127.0.0.1", 0),
                                 handler(root, "play", self.token, 0))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.worker.join(timeout=3)
        self.server.server_close()

    def send(self, method, path, payload=None, *, allowed=True):
        port = self.server.server_port
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
        headers = {"Host": "127.0.0.1:" + str(port)}
        if allowed:
            headers["Authorization"] = "Bearer " + self.token
        if payload is not None:
            headers["Content-Type"] = "application/json"
        try:
            connection.request(method, path,
                               body=json.dumps(payload) if payload is not None else None,
                               headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_status_auth_and_real_action(self):
        status, body = self.send("GET", "/v1/status")
        self.assertEqual(status, 200)
        self.assertEqual(self.send("GET", "/v1/status", allowed=False)[0], 401)
        current = body["snapshot"]
        action = {
            "choice": "wait:wait", "expected_sequence": current["sequence"],
            "expected_state_sha256": current["current_state_sha256"],
        }
        status, result = self.send("POST", "/v1/actions", action)
        self.assertEqual(status, 200)
        self.assertEqual(result["snapshot"]["sequence"], 1)
        self.assertEqual(self.send("POST", "/v1/actions", action)[0], 409)

    def test_invalid_input_cannot_advance_game(self):
        status, body = self.send("POST", "/v1/actions", {
            "choice": "wait:wait", "expected_sequence": True,
            "expected_state_sha256": "0" * 64,
        })
        self.assertEqual(status, 400)
        status, snapshot = self.send("GET", "/v1/status")
        self.assertEqual(snapshot["snapshot"]["sequence"], 0)


if __name__ == "__main__":
    unittest.main()
