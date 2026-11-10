"""Post-merge cross-plane offline acceptance, not device or release certification."""
from __future__ import annotations

import contextlib
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

from scripts.game.offline_grid_campaign import main as campaign_main
from skeleton.__main__ import main as skeleton_main
from skeleton.ai.build.core.delivery import remote_bridge as mirrored
from skeleton.build.delivery import remote_bridge as canonical
from skeleton.build.delivery._util import DeliveryError
from skeleton.build.remote_build import RemoteArtifactRef, VerifiedRemoteReceipt
from skeleton.game.gameplay.offline_grid_save_slot import SaveSlotError, read_slot, write_slot
from skeleton.install.first_run_probe_gate import SERVICE_ORDER, ServiceState
from skeleton.install.wizard_10000x import FirstRunWizard10000x
from skeleton.local_ai.model_loader import ModelLoader


def invoke(*args: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        status = campaign_main(list(args))
    return status, stdout.getvalue(), stderr.getvalue()


def receipt(job: str, artifact: str) -> VerifiedRemoteReceipt:
    return VerifiedRemoteReceipt(
        job, "runner1", "success", (RemoteArtifactRef(artifact, "a" * 64, 3),),
        "0" * 64, "1" * 64,
    )


class PostMergeOfflineIntegrations(unittest.TestCase):
    def test_cli_help_exposes_restored_game_authoring_commands(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(skeleton_main([]), 0)
        for command in ("combat-contract-author", "quest-author", "quest-campaign-route",
                        "arena-forge-author", "world-quest"):
            self.assertIn(command, out.getvalue())

    def test_first_run_failure_keeps_setup_but_blocks_dependents(self):
        invoked: list[str] = []
        def bad_backend():
            invoked.append("backend")
            return False
        def forbidden():
            invoked.append("downstream")
            raise AssertionError("dependency gate bypass")
        state = FirstRunWizard10000x().check_services(
            {"backend": bad_backend, "local_ai": forbidden},
        )
        self.assertEqual(invoked, ["backend"])
        self.assertTrue(state.setup_accessible)
        self.assertFalse(state.guarded_ai_available)
        self.assertFalse(state.playable_enabled)
        self.assertEqual(state.services[0].state, ServiceState.UNAVAILABLE)
        self.assertEqual(state.services[1].reason, "dependency-unavailable")

    def test_mock_healthy_probes_never_claim_release_or_device_approval(self):
        state = FirstRunWizard10000x().check_services(
            {name: (lambda: True) for name in SERVICE_ORDER},
        )
        self.assertTrue(state.setup_accessible)
        self.assertTrue(state.playable_enabled)
        self.assertFalse(state.as_dict()["release_ready"])
        self.assertFalse(state.as_dict()["device_qualified"])

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "requires POSIX descriptor guards")
    def test_campaign_cli_create_and_replace_modes_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            actions = root / "actions.json"
            actions.write_text("[]", encoding="utf-8")
            create = root / "create.json"
            slot = root / "replace.json"
            rc, _, error = invoke("run", "--commands", str(actions), "--out-save", str(create))
            self.assertEqual(rc, 0, error)
            old = create.read_bytes()
            rc, _, _ = invoke("run", "--commands", str(actions), "--out-save", str(create))
            self.assertEqual(rc, 2)
            self.assertEqual(create.read_bytes(), old)
            rc, out, error = invoke("run", "--commands", str(actions), "--save-slot", str(slot))
            self.assertEqual(rc, 0, error)
            self.assertEqual(json.loads(out)["save"], read_slot(slot))
            rc, out, error = invoke(
                "run", "--commands", str(actions), "--resume", str(slot),
                "--save-slot", str(slot),
            )
            self.assertEqual(rc, 0, error)
            self.assertEqual(json.loads(out)["save"], read_slot(slot))
            self.assertEqual(list(root.glob(".campaign-*.tmp")), [])

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "requires POSIX descriptor guards")
    def test_save_rejection_preserves_last_committed_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            slot = Path(tmp) / "slot.json"
            write_slot(slot, {"tick": 7})
            before = slot.read_bytes()
            with self.assertRaises(SaveSlotError):
                write_slot(slot, {"tick": float("nan")})
            self.assertEqual(slot.read_bytes(), before)
            self.assertEqual(read_slot(slot), {"tick": 7})
            alias = Path(tmp) / "alias.json"
            alias.symlink_to(slot)
            with self.assertRaises(SaveSlotError):
                read_slot(alias)
            self.assertEqual(slot.read_bytes(), before)

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "requires POSIX descriptor guards")
    def test_local_gguf_custody_does_not_claim_live_inference(self):
        data = b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + b"source-fixture"
        digest = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.gguf"
            path.write_bytes(data)
            loader = ModelLoader(str(path))
            proof = loader.load("c" * 32, expected_sha256=digest, license_accepted=True)
            self.assertEqual(proof["status"], "artifact_verified_not_loaded")
            self.assertEqual(proof["digest"], digest)
            self.assertFalse(loader.loaded)
            self.assertFalse(loader.verify(digest))
            with self.assertRaises(ValueError):
                loader.load("c" * 32, expected_sha256="0" * 64, license_accepted=True)

    def test_canonical_and_mirrored_remote_receipts_have_same_custody(self):
        first = receipt("job1", "dist/first.whl")
        second = receipt("job2", "dist/second.whl")
        for bridge in (canonical, mirrored):
            with self.subTest(bridge=bridge.__name__):
                result = bridge.entries_from_receipts([first, first])
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0].path, "dist/first.whl")
                with self.assertRaises(DeliveryError):
                    bridge.entries_from_receipts(
                        [first, second],
                        paths={"dist/first.whl": "out/shared.whl",
                               "dist/second.whl": "out/shared.whl"},
                    )
                with self.assertRaises(DeliveryError):
                    bridge.entries_from_receipts(
                        [first, replace(first, runner_id="different")],
                    )

    def test_compose_application_ports_have_literal_loopback_defaults(self):
        root = Path(__file__).resolve().parents[2]
        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        for service_port in (
            "SKELETON_PORT:-8010}:8001",
            "BACKEND_PORT:-8001}:8001",
            "FRONTEND_PORT:-3000}:",
        ):
            self.assertIn("127.0.0.1:", compose)
            self.assertIn(service_port, compose)


if __name__ == "__main__":
    unittest.main()
