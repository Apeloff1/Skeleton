"""Source-only end-to-end cold transport of exact original Jeeves capsule bytes.

No model, private prompt, original project write, generated Python execution,
Git subprocess, network client or unverified release behavior is used.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_capsule_transport as transport,
    desktop_capsule_transport_cli as cli,
    desktop_capsule_source_closure as closure,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_private_capsule import (
    SEAL_NAME, SEAL_SCHEMA, verify_private_capsule,
)
from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_workspace import _canonical


A = "a" * 64
B = "b" * 64
C = "c" * 64


def digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def sealed_example() -> tuple[bytes, str, str, str]:
    code = {
        "pkg/app.py": ("new", b"from .helper import value\nanswer = value + 1\n"),
        "pkg/helper.py": ("selected-original", b"value = 42\n"),
    }
    sources = tuple(
        closure.ClosureSource(name, kind, data, digest(data))
        for name, (kind, data) in code.items()
    )
    graph = closure.analyze_capsule_source_closure(
        sources, source_manifest_sha256=A, source_patch_sha256=B,
    )
    rows = [
        {"path": name, "kind": kind, "sha256": digest(data), "bytes": len(data)}
        for name, (kind, data) in code.items()
    ]
    rows.sort(key=lambda row: (row["path"].casefold(), row["path"]))
    seal = _canonical({
        "schema": SEAL_SCHEMA,
        "status": "private-source-capsule-complete-unexecuted",
        "capsule_sha256": C,
        "source_manifest_sha256": A,
        "patch_sha256": B,
        "python_graph_sha256": "d" * 64,
        "python_closure_sha256": graph.graph_sha256,
        "unverified_source_import_count": graph.unverified_count,
        "file_count": len(rows),
        "files": rows,
        "source_code_executed": False,
        "original_checkout_modified": False,
        "full_project_or_device_qualified": False,
        "release_certified": False,
    })
    ordered_files = [(SEAL_NAME, seal)] + [
        (row["path"], code[row["path"]][1]) for row in rows
    ]
    packed = _canonical({
        "schema": transport.SCHEMA,
        "status": "sealed-private-source-bytes-unexecuted",
        "capsule_sha256": C,
        "seal_sha256": digest(seal),
        "file_count": len(ordered_files),
        "files": [
            {"path": name, "sha256": digest(data), "bytes": len(data),
             "content_b64": base64.b64encode(data).decode("ascii")}
            for name, data in ordered_files
        ],
        "source_code_executed": False,
        "release_certified": False,
    })
    return packed, digest(packed), digest(seal), graph.graph_sha256


def change_archive(raw: bytes, change):
    document = json.loads(raw)
    change(document)
    edited = _canonical(document)
    return edited, digest(edited)


class ColdCapsuleTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.original = str(self.base / "original-project")
        self.bytes, self.archive_sha, self.seal_sha, self.graph_sha = sealed_example()
        self.archive = self.base / "verified-capsule.jcaps"
        self.archive.write_bytes(self.bytes)
        self.archive.chmod(0o600)

    def fields(self):
        return {
            "original_project_root": self.original,
            "expected_archive_sha256": self.archive_sha,
            "expected_capsule_sha256": C,
            "expected_seal_sha256": self.seal_sha,
        }

    def verify(self):
        return transport.inspect_private_transport(self.archive, **self.fields())

    def test_cold_inspection_exposes_receipts_not_source_bytes_or_paths(self):
        result = self.verify()
        self.assertEqual(result["status"], "cold-private-source-archive-verified")
        self.assertEqual(result["python_closure_sha256"], self.graph_sha)
        self.assertEqual(result["source_file_count"], 2)
        self.assertEqual(result["selected_original_file_count"], 1)
        self.assertEqual(result["reviewed_change_file_count"], 1)
        self.assertEqual(result["unverified_external_or_unselected_imports"], 0)
        self.assertFalse(result["release_certified"])
        text = json.dumps(result)
        self.assertNotIn("pkg/app.py", text)
        self.assertNotIn("answer = value", text)
        self.assertNotIn(self.original, text)

    def test_exact_archive_cold_import_export_and_second_independent_import(self):
        first = self.base / "stage-one"
        with (
            mock.patch("subprocess.run") as subprocess,
            mock.patch("os.system") as system,
        ):
            imported = transport.import_private_transport(
                self.archive, first, approve_import=True, **self.fields(),
            )
            self.assertEqual(
                imported["status"], "imported-private-source-capsule-cold-verified",
            )
            self.assertEqual((first / "pkg" / "helper.py").read_bytes(), b"value = 42\n")
            self.assertEqual((first / "pkg" / "app.py").read_bytes(),
                             b"from .helper import value\nanswer = value + 1\n")
            self.assertEqual((first / SEAL_NAME).stat().st_mode & 0o777, 0o600)
            self.assertEqual(first.stat().st_mode & 0o777, 0o700)
            cold = verify_private_capsule(
                first, original_project_root=self.original,
                expected_capsule_sha256=C, expected_seal_sha256=self.seal_sha,
            )
            self.assertEqual(cold["python_closure_sha256"], self.graph_sha)
            second_archive = self.base / "second.jcaps"
            exported = transport.export_private_transport(
                first, second_archive,
                original_project_root=self.original,
                expected_capsule_sha256=C, expected_seal_sha256=self.seal_sha,
                approve_export=True,
            )
            self.assertEqual(exported["archive_sha256"], self.archive_sha)
            self.assertEqual(second_archive.read_bytes(), self.bytes)
            second = self.base / "stage-two"
            restored = transport.import_private_transport(
                second_archive, second, original_project_root=self.original,
                expected_archive_sha256=self.archive_sha,
                expected_capsule_sha256=C, expected_seal_sha256=self.seal_sha,
                approve_import=True,
            )
            self.assertTrue(restored["source_bytes_cold_verified"])
            self.assertEqual((second / "pkg" / "app.py").read_bytes(),
                             (first / "pkg" / "app.py").read_bytes())
            subprocess.assert_not_called()
            system.assert_not_called()

    def test_exact_complete_digest_is_a_required_independent_approval(self):
        with self.assertRaises(transport.CapsuleTransportHold):
            transport.inspect_private_transport(
                self.archive, **{**self.fields(), "expected_archive_sha256": A},
            )

    def test_missing_explicit_import_authority_precedes_any_private_write(self):
        target = self.base / "not-approved"
        with self.assertRaises(transport.CapsuleTransportHold):
            transport.import_private_transport(
                self.archive, target, approve_import=False, **self.fields(),
            )
        self.assertFalse(target.exists())

    def test_import_never_clobbers_an_existing_private_destination(self):
        target = self.base / "already-present"
        target.mkdir(mode=0o700)
        marker = target / "owner.txt"
        marker.write_text("keep")
        with self.assertRaises(FileExistsError):
            transport.import_private_transport(
                self.archive, target, approve_import=True, **self.fields(),
            )
        self.assertEqual(marker.read_text(), "keep")

    def test_transport_source_payload_tamper_fails_even_with_new_archive_sha(self):
        def mutate(document):
            row = document["files"][1]
            raw = base64.b64decode(row["content_b64"])
            row["content_b64"] = base64.b64encode(raw + b"#changed\n").decode("ascii")
            row["bytes"] += 9
            row["sha256"] = digest(raw + b"#changed\n")
        changed, changed_sha = change_archive(self.bytes, mutate)
        self.archive.write_bytes(changed)
        with self.assertRaises(transport.CapsuleTransportHold):
            transport.inspect_private_transport(
                self.archive, **{**self.fields(), "expected_archive_sha256": changed_sha},
            )

    def test_replaced_completion_seal_fails_even_with_new_archive_hash(self):
        def mutate(document):
            row = document["files"][0]
            original = base64.b64decode(row["content_b64"])
            row["content_b64"] = base64.b64encode(original + b" ").decode("ascii")
            row["bytes"] += 1
            row["sha256"] = digest(original + b" ")
        edited, changed_sha = change_archive(self.bytes, mutate)
        self.archive.write_bytes(edited)
        with self.assertRaises(transport.CapsuleTransportHold):
            transport.inspect_private_transport(
                self.archive, **{**self.fields(), "expected_archive_sha256": changed_sha},
            )

    def test_unknown_extra_file_and_path_escape_cannot_enter_capsule(self):
        for name in ("../escape.py", "/absolute.py", "pkg/../../escape.py",
                     ".env", "pkg/.git/config"):
            with self.subTest(name=name):
                def add(document):
                    document["files"].append({
                        "path": name, "bytes": 1, "sha256": digest(b"x"),
                        "content_b64": base64.b64encode(b"x").decode("ascii"),
                    })
                    document["file_count"] += 1
                raw, new_sha = change_archive(self.bytes, add)
                self.archive.write_bytes(raw)
                with self.assertRaises((transport.CapsuleTransportHold, ValueError)):
                    transport.inspect_private_transport(
                        self.archive,
                        **{**self.fields(), "expected_archive_sha256": new_sha},
                    )

    def test_duplicate_json_keys_and_noncanonical_serialization_are_denied(self):
        malformed = self.bytes.replace(
            b'"file_count":3', b'"file_count":3,"file_count":3', 1,
        )
        self.archive.write_bytes(malformed)
        with self.assertRaises((transport.CapsuleTransportHold, ValueError)):
            transport.inspect_private_transport(
                self.archive,
                **{**self.fields(), "expected_archive_sha256": digest(malformed)},
            )
        pretty = json.dumps(json.loads(self.bytes), indent=2).encode("utf-8")
        self.archive.write_bytes(pretty)
        with self.assertRaises(transport.CapsuleTransportHold):
            transport.inspect_private_transport(
                self.archive,
                **{**self.fields(), "expected_archive_sha256": digest(pretty)},
            )

    @unittest.skipUnless(os.name == "posix", "no-follow owner descriptor transport")
    def test_symlink_archive_rejected_before_private_read(self):
        alias = self.base / "alias.jcaps"
        alias.symlink_to(self.archive)
        with self.assertRaises((OSError, ValueError)):
            transport.inspect_private_transport(
                alias, **self.fields(),
            )

    def test_input_byte_budget_rejects_multi_megabyte_untrusted_archive(self):
        self.archive.write_bytes(b"A" * (transport.MAX_ARCHIVE_BYTES + 1))
        with self.assertRaises((ValueError, OSError)):
            self.verify()

    def test_export_refuses_to_write_inside_the_source_capsule(self):
        stage = self.base / "stage"
        transport.import_private_transport(
            self.archive, stage, approve_import=True, **self.fields(),
        )
        with self.assertRaises(transport.CapsuleTransportHold):
            transport.export_private_transport(
                stage, stage / "bad.jcaps",
                original_project_root=self.original,
                expected_capsule_sha256=C, expected_seal_sha256=self.seal_sha,
                approve_export=True,
            )
        self.assertFalse((stage / "bad.jcaps").exists())


class SourceTransportCommandTests(unittest.TestCase):
    def request(self, action: str):
        return {
            "schema": cli.SCHEMA,
            "action": action,
            "original_project_root": "/private/original",
            "capsule_directory": "/private/capsule" if action == "export" else None,
            "archive_file": "/private/archive.jcaps",
            "destination": "/private/new-capsule" if action == "import" else None,
            "expected_capsule_sha256": C,
            "expected_seal_sha256": A,
            "expected_archive_sha256": B if action != "export" else None,
        }

    def test_one_exact_schema_for_inspect_export_import(self):
        for action in ("inspect", "export", "import"):
            self.assertEqual(
                cli.parse_transport_request(_canonical(self.request(action)))["action"],
                action,
            )

    def test_duplicate_unknown_and_nonfinite_request_fields_hold(self):
        base = _canonical(self.request("inspect"))
        duplicates = base.replace(b'"action":"inspect"', b'"action":"inspect","action":"import"')
        with self.assertRaises(cli.CapsuleTransportCLIHold):
            cli.parse_transport_request(duplicates)
        expanded = self.request("inspect")
        expanded["secret_extra"] = True
        with self.assertRaises(cli.CapsuleTransportCLIHold):
            cli.parse_transport_request(_canonical(expanded))
        with self.assertRaises(cli.CapsuleTransportCLIHold):
            cli.parse_transport_request(base.replace(
                b'"action":"inspect"', b'"action":NaN',
            ))

    def test_explicit_consent_is_action_specific_before_calls(self):
        for action in ("inspect", "export", "import"):
            with self.subTest(action=action):
                with mock.patch.object(cli, "export_private_transport") as exported, \
                     mock.patch.object(cli, "import_private_transport") as imported, \
                     mock.patch.object(cli, "inspect_private_transport") as inspected:
                    with self.assertRaises(cli.CapsuleTransportCLIHold):
                        cli.execute_transport_request(
                            self.request(action),
                            approve_export=action == "inspect",
                        )
                    exported.assert_not_called()
                    imported.assert_not_called()
                    inspected.assert_not_called()

    def test_bad_approval_and_failed_source_inspection_do_not_disclose_paths(self):
        request = self.request("import")
        request["original_project_root"] = "/home/private-sensitive-root"
        output = io.StringIO()
        error = io.StringIO()
        code = cli.main(
            ["--approve-import"],
            stdin=io.BytesIO(_canonical(request)),
            stdout=output, stderr=error,
        )
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(error.getvalue(), "JEEVES_PRIVATE_CAPSULE_TRANSPORT_HELD\n")
        self.assertNotIn("private-sensitive-root", error.getvalue())

    def test_no_source_bytes_emitted_from_successful_inspection(self):
        with mock.patch.object(cli, "inspect_private_transport", return_value={
            "status": "cold-private-source-archive-verified",
            "archive_sha256": B,
        }):
            output = io.StringIO()
            result = cli.main(
                [], stdin=io.BytesIO(_canonical(self.request("inspect"))),
                stdout=output, stderr=io.StringIO(),
            )
            self.assertEqual(result, 0)
            self.assertIn('"release_certified":false', output.getvalue())
            self.assertNotIn("/private/archive.jcaps", output.getvalue())


if __name__ == "__main__":
    unittest.main()
