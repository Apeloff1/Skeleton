"""The real crawler snapshot projects a complete inactive automation envelope."""
from datetime import datetime, timedelta, timezone

from core.dragon_crawler import DragonCrawlerApplication, _core


def test_never_authorized_real_snapshot_has_complete_zero_and_null_projection():
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=1)
    scope = {"tenant_id": "tenant-a", "owner_id": "a" * 64}
    request_type, run_type = _core()
    request = request_type(seed_urls=("https://example.com/",), allowed_hosts=("example.com",),
                           max_requests=1, max_documents=1)
    consent = {"consent_id": "b" * 64, "capture_acknowledged": True,
               "source_rights_acknowledged": True, "expires_at": expiry.timestamp()}
    runtime = run_type.create(request, scope=scope, consent=consent, now=now.timestamp())
    row = {"_id": "real-snapshot", "title": "Original captured session", "status": "queued",
           "version": 1, "created_at": now, "updated_at": now, "consent_expires_at": expiry,
           "request": request.as_dict(), "snapshot": runtime.snapshot(), "worker_epoch": 0}
    app = object.__new__(DragonCrawlerApplication)
    app._workers = {}
    projection = app._projection(row)
    assert projection["automation"] == {"enabled": False, "state": "not_authorized", "epoch": 0,
        "slices_started": 0, "max_slices": 0, "expires_at": None, "next_run_at": None, "stop_reason": None}
    assert projection["consent_current"] is True and projection["source_count"] == 0
    assert projection["capabilities"]["can_run"] is True

    # An actual finite active grant keeps its original epoch/count/deadline;
    # no inactive default manufactures or extends automation authorization.
    row["automation"] = {"enabled": True, "state": "authorized", "epoch": 4, "slices_started": 1,
                         "max_slices": 2, "expires_at": expiry, "next_run_at": now, "stop_reason": None,
                         "scope": scope, "principal_email": "private@example.test"}
    active = app._projection(row)["automation"]
    assert active["epoch"] == 4 and active["max_slices"] == 2 and active["slices_started"] == 1
    assert active["expires_at"] == expiry.isoformat() and "principal_email" not in active and "scope" not in active
