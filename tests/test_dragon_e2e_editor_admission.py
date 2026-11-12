"""CI-only, least-authority Dragon editor promotion regression tests.

Does not contact a network. No production role promotion is tested/allowed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.qualify_e2e_dragon_editor import (
    EditorQualificationError,
    _token,
    qualify_editor,
)

EMAIL = "dragon-pilot-e2e-1780000000000-testabc@example.com"
SCOPED_ENV = {
    "CI": "true",
    "GITHUB_ACTIONS": "true",
    "SKELETON_E2E_BASE_URL": "http://127.0.0.1:8001",
}


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count):
        return self.body[:count]


class FakeOpener:
    def __init__(self, body):
        self.body = body
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return FakeResponse(self.body)


class DragonE2EEditorAdmissionTests(unittest.TestCase):
    def test_only_isolated_ci_and_loopback_may_reach_token_file(self):
        for altered in (
            {"CI": "false"},
            {"GITHUB_ACTIONS": "false"},
            {"SKELETON_E2E_BASE_URL": "https://example.org"},
            {"SKELETON_E2E_BASE_URL": "http://localhost:8001"},
            {"SKELETON_E2E_BASE_URL": "http://127.0.0.1:8002"},
        ):
            with self.subTest(altered=altered):
                env = {**SCOPED_ENV, **altered}
                with patch("scripts.qualify_e2e_dragon_editor._token", side_effect=AssertionError):
                    with self.assertRaises(EditorQualificationError):
                        qualify_editor(EMAIL, env)

    def test_unscoped_users_and_email_injection_never_reach_token(self):
        for email in (
            "", "public@example.com", "admin@gameforge.io",
            "dragon-pilot-e2e-1-abc@example.com",
            "dragon-pilot-e2e-1780000000000-a@example.com",
            "dragon-pilot-e2e-1780000000000-testabc@example.com\nrole=admin",
        ):
            with self.subTest(email=email):
                with patch("scripts.qualify_e2e_dragon_editor._token", side_effect=AssertionError):
                    with self.assertRaises(EditorQualificationError):
                        qualify_editor(email, SCOPED_ENV)

    def test_verified_admin_token_grants_only_editor_to_exact_ephemeral_viewer(self):
        opener = FakeOpener({"ok": True, "email": EMAIL, "role": "editor"})
        with patch("scripts.qualify_e2e_dragon_editor._token", return_value="a" * 80):
            qualify_editor(EMAIL, SCOPED_ENV, opener=opener)
        self.assertEqual(len(opener.requests), 1)
        request, timeout = opener.requests[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8001/api/auth/set-role")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(timeout, 8)
        self.assertEqual(json.loads(request.data), {"email": EMAIL, "role": "editor"})
        self.assertEqual(request.get_header("Authorization"), "Bearer " + "a" * 80)

    def test_backend_must_confirm_exact_email_role_and_success(self):
        for body in (
            {"ok": True, "email": EMAIL, "role": "admin"},
            {"ok": True, "email": "other@example.com", "role": "editor"},
            {"ok": False, "email": EMAIL, "role": "editor"},
            {"ok": True, "email": EMAIL},
            {"message": "done"},
        ):
            with self.subTest(body=body):
                with patch("scripts.qualify_e2e_dragon_editor._token", return_value="a" * 80):
                    with self.assertRaises(EditorQualificationError):
                        qualify_editor(EMAIL, SCOPED_ENV, opener=FakeOpener(body))

    @unittest.skipUnless(os.name == "posix" and hasattr(os, "O_NOFOLLOW"),
                         "Secure descriptor-custody tests require POSIX")
    def test_private_token_requires_0600_one_link_and_no_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "skeleton-ci-operator-abc123.token"
            original.write_text("a" * 80 + "\n", encoding="ascii")
            original.chmod(0o600)
            env = {"RUNNER_TEMP": tmp, "SKELETON_E2E_OPERATOR_TOKEN_FILE": str(original)}
            self.assertEqual(_token(env), "a" * 80)
            original.chmod(0o644)
            with self.assertRaises(EditorQualificationError):
                _token(env)
            original.chmod(0o600)
            hardlink = root / "hardlink.token"
            os.link(original, hardlink)
            with self.assertRaises(EditorQualificationError):
                _token(env)
            hardlink.unlink()
            alias = root / "skeleton-ci-operator-alias.token"
            alias.symlink_to(original)
            with self.assertRaises(EditorQualificationError):
                _token({**env, "SKELETON_E2E_OPERATOR_TOKEN_FILE": str(alias)})
            with self.assertRaises(EditorQualificationError):
                _token({**env, "SKELETON_E2E_OPERATOR_TOKEN_FILE": str(root / "other.token")})


if __name__ == "__main__":
    unittest.main()
