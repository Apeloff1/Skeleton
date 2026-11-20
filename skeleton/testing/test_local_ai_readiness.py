"""Read-only standalone local Jeeves readiness matrix never grants release."""
from __future__ import annotations

import pytest

from scripts import local_ai_readiness as audit
from scripts import local_ai_offline_compose as compose
from scripts import local_ai_offline_launch as launch
from scripts import local_ai_device_admission as device
from scripts import local_ai_data_rehydration as restore
from scripts import local_ai_mongo_majority as mongo
from scripts import local_ai_docker as host

_ARCHIVE = object()
_OVERLAY = object()
_DIGEST = "b" * 64


def _mock(monkeypatch, *, image=True, physical=True, device_ok=True,
          provider_ok=True, restore_ok=True, mongo_ok=True):
    events = []
    def binding(mode, archive, output, *, expected_receipt_sha256, root):
        events.append("image")
        if not image:
            raise compose.OfflineComposeError("source unverified")
        return {
            "actual_overlay_render_verified": True,
            "all_four_image_ids_installed": True,
            "guarded_chat_qualified": False,
        }
    def dev(mode, *, root):
        events.append("device")
        if not device_ok:
            raise device.DeviceAdmissionError("capacity unavailable")
        return {"status": "physical_device_inventory_not_live_model_qualified"}
    def running(mode, archive, output, *, expected_receipt_sha256, root):
        events.append("running")
        if not physical:
            raise launch.OfflineLaunchError("running app not qualified")
        return {"status": "four_running_exact_image_containers_not_protected_chat"}
    def provider(mode, root):
        events.append("provider")
        if not provider_ok:
            raise host.LocalDockerError("no backend")
        return {"observed": True, "ready": True}
    def restored(source, dest, *, expected_receipt_sha256):
        events.append("restore")
        if not restore_ok:
            raise restore.RestoreRehearsalError("bytes differ")
        return {
            "application_restore_qualified": False,
            "cross_store_snapshot_atomic": False,
        }
    def majority(mode, archive, output, *, expected_receipt_sha256, root):
        events.append("mongo")
        if not mongo_ok:
            raise mongo.MongoMajorityError("quorum unavailable")
        return {
            "status": "live_mongo_majority_readonly_capability_not_writer_epoch",
            "shared_mongo_writer_epoch_verified": False,
        }
    monkeypatch.setattr(mongo, "inspect_mongo_majority", majority)
    monkeypatch.setattr(compose, "verify_binding", binding)
    monkeypatch.setattr(device, "preflight_device", dev)
    monkeypatch.setattr(launch, "attest_running_offline", running)
    monkeypatch.setattr(host, "live_ai_status", provider)
    monkeypatch.setattr(restore, "verify_rehydration", restored)
    return events


def _call(**kwargs):
    return audit.audit_readiness(
        "cpu", _ARCHIVE, _OVERLAY,
        expected_receipt_sha256=_DIGEST, **kwargs,
    )


def test_all_local_observations_still_fail_release(tmp_path, monkeypatch):
    events = _mock(monkeypatch)
    result = _call(
        restore_source=tmp_path / "source",
        restored_directory=tmp_path / "new",
        expected_restore_sha256="c" * 64,
    )
    assert events == ["image", "device", "running", "provider", "restore", "mongo"]
    assert result["gate_count"] == len(audit.GATES)
    assert result["bounded_local_observation_count"] == 6
    assert set(result["gates"]) == set(audit.GATES)
    assert result["protected_chat_qualified"] is False
    assert result["database_recovery_qualified"] is False
    assert result["physical_gpu_offload_qualified"] is False
    assert result["release_authorized"] is False
    assert result["merge_authorized"] is False
    assert result["docker_daemon_state_mutated"] is False
    assert result["model_inference_executed_by_audit"] is False
    assert all(result["gates"][key]["observed"] is False
               for key in audit.GATES[6:])


def test_missing_offline_archive_stops_dependent_probes(monkeypatch):
    events = _mock(monkeypatch, image=False)
    result = _call()
    assert events == ["image"]
    assert result["bounded_local_observation_count"] == 0
    assert result["gates"]["physical_device_inventory"]["status"] == \
        "prerequisite_unverified"
    assert result["release_authorized"] is False


@pytest.mark.parametrize("missing,expected", [
    ("physical", 4), ("device_ok", 5), ("provider_ok", 5),
    ("restore_ok", 5), ("mongo_ok", 5),
])
def test_missing_real_evidence_keeps_release_blocked(
    tmp_path, monkeypatch, missing, expected,
):
    options = {missing: False}
    _mock(monkeypatch, **options)
    result = _call(
        restore_source=tmp_path / "archive",
        restored_directory=tmp_path / "output",
        expected_restore_sha256="c" * 64,
    )
    assert result["bounded_local_observation_count"] == expected
    assert result["release_authorized"] is False
    assert result["protected_chat_qualified"] is False
    assert sum(int(r["observed"]) for r in result["gates"].values()) == expected


@pytest.mark.parametrize("kwargs", [
    {"restore_source": None, "restored_directory": object()},
    {"restore_source": object(), "restored_directory": None},
    {"restore_source": object(), "restored_directory": object()},
    {"expected_restore_sha256": "a" * 64},
])
def test_partial_restore_arguments_denied_before_any_probes(monkeypatch, kwargs):
    events = _mock(monkeypatch)
    with pytest.raises(audit.ReadinessError, match="paired"):
        _call(**kwargs)
    assert events == []


def test_hypothetical_backend_readiness_cannot_grant_protected_chat(monkeypatch):
    events = _mock(monkeypatch, provider_ok=True)
    report = _call()
    assert "provider" in events
    assert report["gates"]["local_backend_provider_readiness_observation"]["observed"]
    assert report["gates"]["protected_chat_request_response"]["observed"] is False
    assert report["gates"]["shared_mongo_writer_epoch_and_migration"]["observed"] is False
    assert report["release_authorized"] is False


def test_audit_does_not_execute_native_model(monkeypatch):
    from scripts import local_ai_offline_compose
    _mock(monkeypatch)
    monkeypatch.setattr(
        local_ai_offline_compose, "qualify_offline_model",
        lambda *args, **kwargs: pytest.fail("audit cannot execute model"),
    )
    report = _call()
    assert report["model_inference_executed_by_audit"] is False


def test_new_evidence_labels_never_promote_without_trusted_authority(monkeypatch):
    _mock(monkeypatch)
    record = _call()
    independent = (
        "licensed_native_gguf_turn", "active_gguf_tokenizer",
        "independent_bounded_reviewer", "protected_chat_request_response",
        "shared_mongo_writer_epoch_and_migration",
        "coherent_database_recovery", "physical_gpu_or_cpu_inference_pressure",
        "windows_wsl2_and_restart",
        "independent_signed_release_provenance",
    )
    for gate in independent:
        assert record["gates"][gate] == {
            "observed": False,
            "status": "requires_independent_physical_or_authority_evidence",
        }



def test_single_node_mongo_failure_does_not_escalate_shared_writer_epoch(monkeypatch):
    events = _mock(monkeypatch, mongo_ok=False)
    result = _call()
    assert "mongo" in events
    assert result["gates"]["read_only_mongo_majority_capability"] == {
        "observed": False, "status": "unverified",
    }
    assert result["gates"]["shared_mongo_writer_epoch_and_migration"]["observed"] is False
    assert result["release_authorized"] is False


def test_unverified_containers_prevent_reaching_mongo_probe(monkeypatch):
    events = _mock(monkeypatch, physical=False)
    result = _call()
    assert "mongo" not in events
    assert result["gates"]["read_only_mongo_majority_capability"]["status"] == (
        "prerequisite_unverified"
    )
    assert result["release_authorized"] is False
