from __future__ import annotations

import unittest

from skeleton.automation.build_contracts import BuildBudget
from skeleton.automation.build_edits import (
    BuildEditError,
    FileEditPlan,
    TextEdit,
    apply_edit_plan,
    normalize_implementation_payload,
)


class TextEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.budget = BuildBudget()

    def test_replace_requires_unique_anchor(self) -> None:
        plan = FileEditPlan(
            path="skeleton/example.py",
            edits=(
                TextEdit(
                    kind="replace",
                    anchor="VALUE = 1",
                    replacement="VALUE = 2",
                ),
            ),
        )
        candidate, evidence = apply_edit_plan(
            "VALUE = 1\n",
            plan,
            budget=self.budget,
        )
        self.assertEqual(candidate.content, "VALUE = 2\n")
        self.assertNotEqual(
            evidence.before_digest,
            evidence.after_digest,
        )
        self.assertEqual(evidence.path, "skeleton/example.py")

    def test_insert_before(self) -> None:
        plan = FileEditPlan(
            path="skeleton/example.py",
            edits=(
                TextEdit(
                    kind="insert_before",
                    anchor="def run():",
                    replacement="@decorator\n",
                ),
            ),
        )
        candidate, _ = apply_edit_plan(
            "def run():\n    pass\n",
            plan,
            budget=self.budget,
        )
        self.assertTrue(
            candidate.content.startswith(
                "@decorator\ndef run():"
            )
        )

    def test_insert_after(self) -> None:
        plan = FileEditPlan(
            path="skeleton/example.py",
            edits=(
                TextEdit(
                    kind="insert_after",
                    anchor="VALUE = 1\n",
                    replacement="OTHER = 2\n",
                ),
            ),
        )
        candidate, _ = apply_edit_plan(
            "VALUE = 1\n",
            plan,
            budget=self.budget,
        )
        self.assertEqual(
            candidate.content,
            "VALUE = 1\nOTHER = 2\n",
        )

    def test_delete(self) -> None:
        plan = FileEditPlan(
            path="skeleton/example.py",
            edits=(
                TextEdit(
                    kind="delete",
                    anchor="REMOVE = True\n",
                ),
            ),
        )
        candidate, _ = apply_edit_plan(
            "KEEP = True\nREMOVE = True\n",
            plan,
            budget=self.budget,
        )
        self.assertEqual(candidate.content, "KEEP = True\n")

    def test_ambiguous_anchor_fails_closed(self) -> None:
        plan = FileEditPlan(
            path="skeleton/example.py",
            edits=(
                TextEdit(
                    kind="replace",
                    anchor="x",
                    replacement="y",
                ),
            ),
        )
        with self.assertRaises(BuildEditError):
            apply_edit_plan(
                "x\nx\n",
                plan,
                budget=self.budget,
            )

    def test_missing_anchor_fails_closed(self) -> None:
        plan = FileEditPlan(
            path="skeleton/example.py",
            edits=(
                TextEdit(
                    kind="replace",
                    anchor="missing",
                    replacement="value",
                ),
            ),
        )
        with self.assertRaises(BuildEditError):
            apply_edit_plan(
                "present\n",
                plan,
                budget=self.budget,
            )

    def test_edit_sequence_is_host_ordered(self) -> None:
        plan = FileEditPlan(
            path="skeleton/example.py",
            edits=(
                TextEdit(
                    kind="replace",
                    anchor="VALUE = 1",
                    replacement="VALUE = 2",
                ),
                TextEdit(
                    kind="insert_after",
                    anchor="VALUE = 2\n",
                    replacement="VALUE_2 = 3\n",
                ),
            ),
        )
        candidate, _ = apply_edit_plan(
            "VALUE = 1\n",
            plan,
            budget=self.budget,
        )
        self.assertEqual(
            candidate.content,
            "VALUE = 2\nVALUE_2 = 3\n",
        )

    def test_delete_rejects_replacement(self) -> None:
        with self.assertRaises(BuildEditError):
            TextEdit(
                kind="delete",
                anchor="x",
                replacement="y",
            )

    def test_insert_requires_replacement(self) -> None:
        with self.assertRaises(BuildEditError):
            TextEdit(
                kind="insert_before",
                anchor="x",
                replacement="",
            )

    def test_path_traversal_rejected(self) -> None:
        with self.assertRaises(BuildEditError):
            FileEditPlan(
                path="skeleton/../unsafe.py",
                edits=(
                    TextEdit(
                        kind="delete",
                        anchor="x",
                    ),
                ),
            )

    def test_duplicate_edit_operation_rejected(self) -> None:
        edit = TextEdit(
            kind="replace",
            anchor="x",
            replacement="y",
        )
        with self.assertRaises(BuildEditError):
            FileEditPlan(
                path="skeleton/example.py",
                edits=(edit, edit),
            )

    def test_post_edit_file_budget_enforced(self) -> None:
        budget = BuildBudget(
            max_total_bytes=4_000,
            max_file_bytes=1_000,
        )
        plan = FileEditPlan(
            path="docs/example.md",
            edits=(
                TextEdit(
                    kind="insert_after",
                    anchor="a",
                    replacement="b" * 1_000,
                ),
            ),
        )
        with self.assertRaises(BuildEditError):
            apply_edit_plan(
                "a",
                plan,
                budget=budget,
            )


class ImplementationNormalizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.budget = BuildBudget()

    def test_normalizes_complete_new_file(self) -> None:
        result = normalize_implementation_payload(
            {
                "summary": "new file",
                "files": [
                    {
                        "path": "skeleton/new.py",
                        "content": "VALUE = 1\n",
                        "intent": "feature",
                    }
                ],
                "tests": ["cover feature"],
            },
            assigned_paths=("skeleton/new.py",),
            budget=self.budget,
            source_reader=lambda _path: (_ for _ in ()).throw(
                AssertionError("source reader should not run")
            ),
        )
        self.assertEqual(len(result.files), 1)
        self.assertEqual(result.applied_edits, ())
        self.assertEqual(
            result.to_shard_payload()["files"][0]["path"],
            "skeleton/new.py",
        )

    def test_normalizes_existing_file_edit(self) -> None:
        result = normalize_implementation_payload(
            {
                "summary": "edit",
                "edits": [
                    {
                        "path": "skeleton/example.py",
                        "intent": "change value",
                        "edits": [
                            {
                                "kind": "replace",
                                "anchor": "VALUE = 1",
                                "replacement": "VALUE = 2",
                            }
                        ],
                    }
                ],
                "tests": ["value changes"],
            },
            assigned_paths=("skeleton/example.py",),
            budget=self.budget,
            source_reader=lambda path: (
                "VALUE = 1\n"
                if path == "skeleton/example.py"
                else ""
            ),
        )
        self.assertEqual(
            result.files[0].content,
            "VALUE = 2\n",
        )
        self.assertEqual(len(result.applied_edits), 1)

    def test_full_and_edit_for_same_path_is_rejected(self) -> None:
        payload = {
            "summary": "ambiguous",
            "files": [
                {
                    "path": "skeleton/example.py",
                    "content": "VALUE = 2\n",
                }
            ],
            "edits": [
                {
                    "path": "skeleton/example.py",
                    "edits": [
                        {
                            "kind": "replace",
                            "anchor": "VALUE = 1",
                            "replacement": "VALUE = 2",
                        }
                    ],
                }
            ],
            "tests": [],
        }
        with self.assertRaises(BuildEditError):
            normalize_implementation_payload(
                payload,
                assigned_paths=("skeleton/example.py",),
                budget=self.budget,
                source_reader=lambda _path: "VALUE = 1\n",
            )

    def test_missing_assigned_path_is_rejected_for_implementation(self) -> None:
        with self.assertRaises(BuildEditError):
            normalize_implementation_payload(
                {
                    "summary": "missing",
                    "files": [],
                    "tests": [],
                },
                assigned_paths=(
                    "skeleton/a.py",
                    "skeleton/b.py",
                ),
                budget=self.budget,
                source_reader=lambda _path: "",
            )

    def test_extra_unassigned_path_is_rejected(self) -> None:
        with self.assertRaises(BuildEditError):
            normalize_implementation_payload(
                {
                    "summary": "extra",
                    "files": [
                        {
                            "path": "skeleton/extra.py",
                            "content": "X = 1\n",
                        }
                    ],
                    "tests": [],
                },
                assigned_paths=("skeleton/a.py",),
                budget=self.budget,
                source_reader=lambda _path: "",
            )

    def test_repair_may_return_bounded_subset(self) -> None:
        result = normalize_implementation_payload(
            {
                "summary": "repair one",
                "files": [
                    {
                        "path": "skeleton/a.py",
                        "content": "A = 2\n",
                    }
                ],
                "tests": ["a fixed"],
            },
            assigned_paths=(
                "skeleton/a.py",
                "skeleton/b.py",
            ),
            budget=self.budget,
            source_reader=lambda _path: "",
            require_all=False,
        )
        self.assertEqual(
            [item.path for item in result.files],
            ["skeleton/a.py"],
        )

    def test_repair_subset_must_not_be_empty(self) -> None:
        with self.assertRaises(BuildEditError):
            normalize_implementation_payload(
                {
                    "summary": "empty repair",
                    "files": [],
                    "edits": [],
                    "tests": [],
                },
                assigned_paths=("skeleton/a.py",),
                budget=self.budget,
                source_reader=lambda _path: "",
                require_all=False,
            )

    def test_unknown_payload_field_is_rejected(self) -> None:
        with self.assertRaises(BuildEditError):
            normalize_implementation_payload(
                {
                    "summary": "bad",
                    "files": [
                        {
                            "path": "skeleton/a.py",
                            "content": "A = 1\n",
                        }
                    ],
                    "tests": [],
                    "command": "python unsafe.py",
                },
                assigned_paths=("skeleton/a.py",),
                budget=self.budget,
                source_reader=lambda _path: "",
            )

    def test_source_reader_failure_is_wrapped(self) -> None:
        def broken_reader(_path: str) -> str:
            raise RuntimeError("missing")

        with self.assertRaises(BuildEditError):
            normalize_implementation_payload(
                {
                    "summary": "edit",
                    "edits": [
                        {
                            "path": "skeleton/a.py",
                            "edits": [
                                {
                                    "kind": "replace",
                                    "anchor": "A = 1",
                                    "replacement": "A = 2",
                                }
                            ],
                        }
                    ],
                    "tests": [],
                },
                assigned_paths=("skeleton/a.py",),
                budget=self.budget,
                source_reader=broken_reader,
            )


if __name__ == "__main__":
    unittest.main()
