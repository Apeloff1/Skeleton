def test_gated_create_app_end_to_end(gated_client, monkeypatch):
    import time

    seen = []
    def handler(ctx, payload):
        seen.append((ctx.actor_id, payload["brief"]["title"], payload["project_build_authorized"]))
        return {"ok": True}
    monkeypatch.setattr("skeleton.forge.game_build_queue.handle_game_build", handler)
    c, h = gated_client.client, gated_client.headers
    assert c.get("/api/v1/projects").status_code == 401  # no seal: gate rejects
    r = c.get("/api/v1/projects", headers=gated_client.seal_only)
    assert r.status_code == 401 and r.json()["error"]["code"] == "PROJECT.UNAUTHENTICATED"
    p = c.post("/api/v1/projects", json={"brief": "Gated game"}, headers=h)
    assert p.status_code == 201, p.text
    pid = p.json()["project_id"]
    b = c.post(f"/api/v1/projects/{pid}/builds", json={"target": "godot"}, headers=h)
    assert b.status_code == 202 and b.json()["status"] == "queued"
    deadline = time.monotonic() + 5
    while gated_client.services.jobs.get_status(b.json()["job_id"]).status not in ("succeeded", "failed") and time.monotonic() < deadline:
        time.sleep(0.02)
    assert gated_client.services.jobs.get_status(b.json()["job_id"]).status == "succeeded"
    assert seen == [(gated_client.user.user_id, "Gated game", True)]
