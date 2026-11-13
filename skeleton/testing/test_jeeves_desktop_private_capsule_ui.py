"""Headless Tk method contracts for the original local Jeeves capsule UI.

No Tk root or display is opened; GUI callbacks are exercised with controlled
operator inputs and mocked background threads. No original project is written.
"""
from __future__ import annotations

from queue import Queue
from types import SimpleNamespace
from unittest import mock
import unittest

from skeleton.ai.runtime.operational_ai.laptop_runtime import (
    desktop_patch_ui as ui,
)


class ImmediateThread:
    def __init__(self, *, target, daemon):
        assert daemon is True
        self.target = target

    def start(self):
        self.target()


def fake_window(*, manifest="a" * 64, patch="b" * 64,
                capsule_digest="c" * 64):
    current = SimpleNamespace(
        manifest_sha256=manifest, patch_sha256=patch, entries=(1,),
        root="/original/project",
    )
    capsule = SimpleNamespace(
        patch=current, originals=(1, 2),
        capsule_sha256=capsule_digest,
        total_bytes=2048,
        public_review=lambda: {
            "selected_python_closure_status": "partially-unverified-python",
            "linked_original_imports": 1,
            "unverified_external_or_unselected_imports": 1,
            "python_closure_sha256": "d" * 64,
        },
    )
    view = SimpleNamespace(
        _busy=False, _closed=False, _epoch=8,
        _plan=current,
        _qualification=SimpleNamespace(permits_inert_export=True),
        _source_graph=SimpleNamespace(permits_inert_export=True),
        _reviewed_texts=("/original/project", "new", "edit"),
        _source_inputs=lambda: ("/original/project", "new", "edit"),
        _capsule_selected=lambda: "src/dependency.py",
        _capsule_source_selection="src/dependency.py",
        _capsule_plan=capsule,
        _capsule_receipt=None, _capsule_path=None,
        capsule_expected=mock.Mock(),
        expected_manifest=mock.Mock(),
        expected_patch=mock.Mock(),
        progress=mock.Mock(), status=mock.Mock(),
        _buttons=mock.Mock(), _invalidate=mock.Mock(),
        _queue=Queue(), after=mock.Mock(), _poll=mock.Mock(),
    )
    view.expected_manifest.get.return_value = manifest
    view.expected_patch.get.return_value = patch
    view.capsule_expected.get.return_value = capsule_digest
    return view, capsule


class SourceCapsuleDesktopUIContractTests(unittest.TestCase):
    def test_review_never_publishes_or_invokes_native_model(self):
        view, planned = fake_window()
        with (
            mock.patch.object(ui, "prepare_private_capsule", return_value=planned) as plan,
            mock.patch.object(ui, "publish_private_capsule") as publication,
            mock.patch.object(ui.threading, "Thread", side_effect=ImmediateThread),
        ):
            ui.PortablePatchWindow._review_capsule(view)
        publication.assert_not_called()
        plan.assert_called_once()
        self.assertTrue(view._busy)
        self.assertEqual(view._queue.get_nowait()[0], "capsule-reviewed")
        view.capsule_expected.set.assert_called_with("")

    def test_changed_source_panes_invalidate_before_inspect(self):
        view, planned = fake_window()
        view._reviewed_texts = ("different", "new", "edit")
        with mock.patch.object(ui, "prepare_private_capsule") as plan:
            ui.PortablePatchWindow._review_capsule(view)
        plan.assert_not_called()
        view._invalidate.assert_called_once()

    def test_full_three_sha_required_before_private_publish_prompt(self):
        for field in ("expected_manifest", "expected_patch", "capsule_expected"):
            with self.subTest(field=field):
                view, _ = fake_window()
                getattr(view, field).get.return_value = "0"*64
                with mock.patch.object(ui.filedialog, "askdirectory") as choice:
                    ui.PortablePatchWindow._publish_capsule(view)
                choice.assert_not_called()
                self.assertTrue(view._queue.empty())
                view.status.set.assert_called()

    def test_selected_original_changes_invalidate_private_publish(self):
        view, _ = fake_window()
        view._capsule_selected = lambda: "src/other.py"
        with mock.patch.object(ui, "publish_private_capsule") as pub:
            ui.PortablePatchWindow._publish_capsule(view)
        view._invalidate.assert_called_once()
        pub.assert_not_called()

    def test_separately_consented_publish_uses_full_three_sha(self):
        view, plan = fake_window()
        with (
            mock.patch.object(ui.filedialog, "askdirectory", return_value="/private"),
            mock.patch.object(ui.simpledialog, "askstring", return_value="new_capsule"),
            mock.patch.object(ui.messagebox, "askyesno", return_value=True),
            mock.patch.object(ui, "publish_private_capsule", return_value={
                "seal_sha256": "d"*64, "file_count": 3,
            }) as publication,
            mock.patch.object(ui.threading, "Thread", side_effect=ImmediateThread),
        ):
            ui.PortablePatchWindow._publish_capsule(view)
        publication.assert_called_once_with(
            plan, "/private/new_capsule",
            expected_capsule_sha256="c"*64,
            expected_manifest_sha256="a"*64,
            expected_patch_sha256="b"*64,
            approve_private_capsule=True,
        )
        self.assertEqual(view._queue.get_nowait()[0], "capsule-published")

    def test_rejected_human_confirmation_cannot_publish(self):
        view, _ = fake_window()
        with (
            mock.patch.object(ui.filedialog, "askdirectory", return_value="/private"),
            mock.patch.object(ui.simpledialog, "askstring", return_value="new_capsule"),
            mock.patch.object(ui.messagebox, "askyesno", return_value=False),
            mock.patch.object(ui, "publish_private_capsule") as publication,
        ):
            ui.PortablePatchWindow._publish_capsule(view)
        publication.assert_not_called()
        self.assertTrue(view._queue.empty())

    def test_cold_verify_requires_saved_receipt_and_does_not_open_model(self):
        view, _ = fake_window()
        view._capsule_path = "/private/new_capsule"
        view._capsule_receipt = {"seal_sha256": "d"*64}
        with (
            mock.patch.object(ui, "verify_private_capsule", return_value={
                "file_count": 3,
            }) as verify,
            mock.patch.object(ui.threading, "Thread", side_effect=ImmediateThread),
        ):
            ui.PortablePatchWindow._verify_capsule(view)
        verify.assert_called_once_with(
            "/private/new_capsule",
            original_project_root="/original/project",
            expected_capsule_sha256="c"*64,
            expected_seal_sha256="d"*64,
        )
        self.assertEqual(view._queue.get_nowait()[0], "capsule-verified")

    def test_ui_rejects_stale_selection_returned_from_background_review(self):
        view, plan = fake_window()
        view._capsule_source_selection = None
        view._capsule_selected = lambda: "src/changed.py"
        view._capsule_plan = None
        view._queue.put((
            "capsule-reviewed", view._epoch, "src/dependency.py", plan,
            plan.public_review(),
        ))
        ui.PortablePatchWindow._poll(view)
        self.assertIsNone(view._capsule_plan)
        self.assertFalse(view._busy)
        view.status.set.assert_called()
        view.after.assert_called_once()

    def test_ui_accepts_new_capsule_digest_but_never_auto_approves(self):
        view, plan = fake_window()
        view._capsule_plan = None
        view._queue.put((
            "capsule-reviewed", view._epoch, "src/dependency.py", plan,
            plan.public_review(),
        ))
        ui.PortablePatchWindow._poll(view)
        self.assertIs(view._capsule_plan, plan)
        self.assertEqual(view._capsule_source_selection, "src/dependency.py")
        view.capsule_expected.set.assert_called_with("")
        self.assertFalse(view._busy)

    def test_ui_records_seal_without_running_source_code(self):
        view, _ = fake_window()
        receipt = {"file_count": 3, "seal_sha256": "d"*64}
        view._queue.put((
            "capsule-published", view._epoch, "/private/new_capsule", receipt,
        ))
        ui.PortablePatchWindow._poll(view)
        self.assertEqual(view._capsule_receipt, receipt)
        self.assertEqual(view._capsule_path, "/private/new_capsule")
        view._buttons.assert_called()


if __name__ == "__main__":
    unittest.main()
