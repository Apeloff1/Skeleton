"""Recovered asset, replication, profiler and dialogue integration tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import zlib

import pytest

from skeleton.app.asset_source_audit import AssetAuditError, audit_assets
from skeleton.app.netcode_replay_qualification import ReplayError, ReplayPolicy, qualify


def _png():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (bytes.fromhex("89504e470d0a1a0a")
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(8))) + chunk(b"IEND", b""))


@pytest.fixture
def asset_pack(tmp_path):
    root = tmp_path / "assets"
    root.mkdir()
    (root / "texture.png").write_bytes(_png())
    (root / "mesh.obj").write_text(
        "mtllib mesh.mtl\no demo\nv 0 0 0\nv 1 0 0\nv 0 1 0\n"
        "usemtl stone\nf 1 2 3\n", encoding="utf-8")
    (root / "mesh.mtl").write_text("newmtl stone\n", encoding="utf-8")
    return root


def test_sidecar_bytes_bound_to_canonical_manifest(asset_pack):
    paths = ["texture.png", "mesh.obj"]
    result = audit_assets(asset_pack, paths, authorized=True)
    assert result["asset_manifest"]["paths"] == 2
    assert result["sidecar_reference_count"] == 1
    assert result["sidecars"][0]["path"] == "mesh.mtl"
    verified = audit_assets(asset_pack, paths[::-1], authorized=True,
                            expected_catalog_sha256=result["catalog_sha256"])
    assert verified["independent_pin_verified"]
    (asset_pack / "mesh.mtl").write_text("newmtl other\n", encoding="utf-8")
    with pytest.raises(AssetAuditError, match="differs"):
        audit_assets(asset_pack, paths, authorized=True,
                     expected_catalog_sha256=result["catalog_sha256"])


def test_asset_admission_fail_closed(asset_pack):
    with pytest.raises(PermissionError):
        audit_assets(asset_pack, ["texture.png"], authorized=False)
    with pytest.raises(AssetAuditError):
        audit_assets(asset_pack, ["texture.png", "texture.png"], authorized=True)
    with pytest.raises(AssetAuditError):
        audit_assets(asset_pack, ["mesh.obj"], authorized=True, max_sidecar_bytes=1)
    (asset_pack / "mesh.mtl").unlink()
    with pytest.raises(AssetAuditError):
        audit_assets(asset_pack, ["texture.png", "mesh.obj"], authorized=True)


def test_asset_installed_cli(asset_pack, capsys):
    from skeleton.__main__ import main
    args = ["--root", str(asset_pack), "--asset", "texture.png", "--trusted-local-operator"]
    assert main(["asset-source-audit", "inventory", *args]) == 0
    report = json.loads(capsys.readouterr().out)
    assert main(["asset-source-audit", "verify", *args,
                 "--expected-catalog-sha256", report["catalog_sha256"]]) == 0


@pytest.mark.parametrize("loss", [0, 250_000, 1_000_000])
def test_actual_in_memory_replication_and_replay(loss):
    policy = ReplayPolicy(ticks=25, clients=3, entities=8,
                          loss_ppm=loss, delay_ticks=3, recovery_ticks=8)
    result = qualify(policy, authorized=True)
    assert result["deterministic_replay_matched"]
    assert result["clients_converged"]
    assert result["local_qualification_passed"]
    assert not result["physical_network_tested"]
    assert result["measured_tick_profile"][0]["frames"] == 33
    assert result["deterministic_first"]["server_metrics"]["handshakes_ok"] == 3
    assert result["deterministic_evidence_digest"] == qualify(
        policy, authorized=True)["deterministic_evidence_digest"]


def test_replay_policy_bounds_and_no_implicit_execution():
    with pytest.raises(PermissionError):
        qualify(ReplayPolicy(), authorized=False)
    with pytest.raises(ReplayError):
        ReplayPolicy(ticks=4096, clients=16, entities=32)
    with pytest.raises(ReplayError):
        ReplayPolicy(delay_ticks=10, recovery_ticks=2)
    with pytest.raises(ReplayError):
        qualify(ReplayPolicy(), authorized=True, max_hitch_ratio=float("nan"))


def test_replay_installed_route(capsys):
    from skeleton.__main__ import main
    assert main(["netcode-replay-qualify", "--ticks", "3", "--clients", "1",
                 "--entities", "2", "--trusted-local-operator"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["in_process_transport_executed"]
    assert main(["netcode-replay-qualify", "--ticks", "3"]) == 2


def test_dialogue_owner_help(capsys):
    from skeleton.__main__ import main
    with pytest.raises(SystemExit) as exc:
        main(["offline-dialogue", "--help"])
    assert exc.value.code == 0
    assert "usage:" in capsys.readouterr().out.lower()
