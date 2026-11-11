"""Hermetic adversarial coverage for real CI E2E operator admission.

No network requests, external credentials, or privileged backend are used.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "ci_operator", ROOT / "scripts/provision_e2e_operator.py",
)
assert spec is not None and spec.loader is not None
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)

TOKEN = "ci-test-only." + "x" * 64


class Reply(io.BytesIO):
    status = 200

    def __init__(self, value):
        super().__init__(json.dumps(value).encode("utf-8"))


class AuthenticatedBackend:
    def __init__(self, *, role="admin", enforced=True, email=None):
        self.role = role
        self.enforced = enforced
        self.email = email
        self.requests = []

    def open(self, request, timeout=0):
        self.requests.append((request.full_url, timeout))
        if request.full_url.endswith("/api/auth/login"):
            body = json.loads(request.data)
            assert body["email"].startswith("qa-e2e-operator-")
            assert len(body["password"]) >= 32
            return Reply({"access_token": TOKEN, "role": self.role})
        if request.full_url.endswith("/api/auth/me"):
            assert request.get_header("Authorization") == "Bearer " + TOKEN
            return Reply({
                "authenticated": True, "enforced": self.enforced,
                "user": {
                    "email": self.email or "qa-e2e-operator-123-1@example.com",
                    "role": self.role, "tenant_id": "default",
                },
            })
        raise AssertionError("unrecognized request")


class EphemeralOperatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.github_env = self.root / "github-env"
        self.github_env.write_text("", encoding="utf-8")
        self.env = {
            "GITHUB_ACTIONS": "true",
            "SKELETON_E2E_BASE_URL": "http://127.0.0.1:8001",
            "GAMEFORGE_SEED_ADMIN_EMAIL": "qa-e2e-operator-123-1@example.com",
            "GAMEFORGE_SEED_ADMIN_PASSWORD": "only-test-data-" + "p" * 40,
            "RUNNER_TEMP": str(self.root),
            "GITHUB_ENV": str(self.github_env),
        }

    def test_real_login_and_me_required_before_private_publication(self):
        backend = AuthenticatedBackend()
        path = operator.provision(self.env, backend)
        self.assertTrue(path.is_file())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(path.read_text(encoding="ascii").strip(), TOKEN)
        self.assertEqual(len(backend.requests), 2)
        self.assertEqual(
            self.github_env.read_text(encoding="utf-8"),
            "SKELETON_E2E_OPERATOR_TOKEN_FILE=" + str(path) + "\n",
        )
        self.assertNotIn(TOKEN, self.github_env.read_text(encoding="utf-8"))
        path.unlink()

    def test_public_viewer_cannot_be_promoted_by_ci_helper(self):
        with self.assertRaises(operator.OperatorAdmissionError):
            operator.provision(self.env, AuthenticatedBackend(role="viewer"))
        self.assertFalse(list(self.root.glob("skeleton-ci-operator-*.token")))

    def test_disabled_auth_is_not_qualifying(self):
        with self.assertRaises(operator.OperatorAdmissionError):
            operator.provision(self.env, AuthenticatedBackend(enforced=False))
        self.assertEqual(self.github_env.read_text(encoding="utf-8"), "")

    def test_mismatched_authenticated_identity_is_rejected(self):
        with self.assertRaises(operator.OperatorAdmissionError):
            operator.provision(
                self.env, AuthenticatedBackend(email="other@example.com")
            )

    def test_remote_hosts_proxy_urls_and_userinfo_fail_before_network(self):
        for base in (
            "https://example.org:8001", "http://127.0.0.1:8002",
            "http://someone@127.0.0.1:8001",
            "http://127.0.0.1:8001/?x=1",
            "http://localhost:8001",
        ):
            with self.subTest(base=base):
                env = dict(self.env, SKELETON_E2E_BASE_URL=base)
                backend = AuthenticatedBackend()
                with self.assertRaises(operator.OperatorAdmissionError):
                    operator.provision(env, backend)
                self.assertEqual(backend.requests, [])

    def test_non_ci_and_weak_or_unscoped_seeds_are_rejected(self):
        altered = (
            {"GITHUB_ACTIONS": "false"},
            {"GAMEFORGE_SEED_ADMIN_EMAIL": "admin@example.com"},
            {"GAMEFORGE_SEED_ADMIN_PASSWORD": "weak"},
        )
        for change in altered:
            with self.subTest(change=tuple(change)):
                env = dict(self.env, **change)
                with self.assertRaises(operator.OperatorAdmissionError):
                    operator.provision(env, AuthenticatedBackend())


if __name__ == "__main__":
    unittest.main()
