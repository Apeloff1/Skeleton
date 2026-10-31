def test_gated_create_app_end_to_end(gated_client):
    c, h = gated_client.client, gated_client.headers
    assert c.get("/api/v1/projects").status_code == 401  # no seal: gate rejects
    r = c.get("/api/v1/projects", headers=gated_client.seal_only)
    assert r.status_code == 401 and r.json()["error"]["code"] == "PROJECT.UNAUTHENTICATED"
    p = c.post("/api/v1/projects", json={"brief": "Gated game"}, headers=h)
    assert p.status_code == 201, p.text
    pid = p.json()["project_id"]
    b = c.post(f"/api/v1/projects/{pid}/builds", json={"target": "gb"}, headers=h)
    assert b.status_code == 202 and b.json()["status"] == "queued"
    assert gated_client.services.jobs.get_status(b.json()["job_id"]).status == "queued"
