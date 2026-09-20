from __future__ import annotations

import unittest

from skeleton.automation.build_contracts import (
    BuildBudget,
    CandidateFile,
)
from skeleton.automation.build_validation import ValidationDiagnostic
from skeleton.automation.build_review import (
    _review_content,
    model_review,
    repair_prompt,
    static_review,
)


class FakeClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def chat(self, system: str, prompt: str, *, max_tokens: int) -> str:
        self.calls += 1
        return self.response


class StaticBuildReviewTests(unittest.TestCase):
    def test_python_syntax_error_is_blocker(self) -> None:
        findings = static_review(
            (
                CandidateFile(
                    path="skeleton/bad.py",
                    content="def broken(:\n",
                ),
            )
        )
        self.assertTrue(
            any(
                item.severity == "blocker"
                and item.category == "syntax"
                for item in findings
            )
        )

    def test_invalid_json_is_blocker(self) -> None:
        findings = static_review(
            (
                CandidateFile(
                    path="docs/example.json",
                    content='{"broken":',
                ),
            )
        )
        self.assertTrue(
            any(item.category == "syntax" for item in findings)
        )

    def test_secret_markers_are_blocking(self) -> None:
        findings = static_review(
            (
                CandidateFile(
                    path="docs/example.md",
                    content="credential github_pat_example\n",
                ),
            )
        )
        self.assertTrue(
            any(
                item.category == "secret"
                and item.severity == "blocker"
                for item in findings
            )
        )

    def test_dynamic_execution_is_visible_but_not_automatically_blocking(self) -> None:
        findings = static_review(
            (
                CandidateFile(
                    path="skeleton/example.py",
                    content="value = eval('1 + 1')\n",
                ),
            )
        )
        dynamic = [
            item
            for item in findings
            if item.category == "dynamic_execution"
        ]
        self.assertEqual(len(dynamic), 1)
        self.assertEqual(dynamic[0].severity, "medium")

    def test_missing_final_newline_is_low_severity(self) -> None:
        findings = static_review(
            (
                CandidateFile(
                    path="docs/example.md",
                    content="hello",
                ),
            )
        )
        self.assertTrue(
            any(
                item.category == "format"
                and item.severity == "low"
                for item in findings
            )
        )


class ReviewPromptTests(unittest.TestCase):
    def test_review_content_is_bounded(self) -> None:
        files = tuple(
            CandidateFile(
                path=f"skeleton/file_{index}.py",
                content=("x = 1\n" * 4_000),
            )
            for index in range(4)
        )
        rendered = _review_content(
            files,
            per_file_bytes=1_000,
            total_bytes=2_500,
        )
        self.assertLessEqual(
            len(rendered.encode("utf-8")),
            2_500,
        )
        self.assertIn("skeleton/file_0.py", rendered)

    def test_static_blocker_short_circuits_provider_review(self) -> None:
        client = FakeClient(
            '{"verdict":"accept","summary":"ignored",'
            '"confidence":100,"findings":[]}'
        )
        review = model_review(
            client=client,
            objective="fix syntax",
            acceptance=("valid Python",),
            files=(
                CandidateFile(
                    path="skeleton/bad.py",
                    content="def broken(:\n",
                ),
            ),
            budget=BuildBudget(),
        )
        self.assertEqual(review.verdict, "repair")
        self.assertEqual(client.calls, 0)
        self.assertTrue(review.required_findings)

    def test_blocking_candidate_validation_short_circuits_provider(self) -> None:
        client = FakeClient(
            '{"verdict":"accept","summary":"ignored",'
            '"confidence":100,"findings":[]}'
        )
        review = model_review(
            client=client,
            objective="repair deterministic blocker",
            acceptance=("publishable",),
            files=(
                CandidateFile(
                    path="docs/example.md",
                    content="clean text\n",
                ),
            ),
            budget=BuildBudget(),
            validation_findings=(
                ValidationDiagnostic(
                    severity="blocker",
                    code="merge-conflict-marker",
                    path="docs/example.md",
                    message="unresolved merge conflict marker",
                    line=1,
                ),
            ),
        )
        self.assertEqual(review.verdict, "repair")
        self.assertEqual(client.calls, 0)
        self.assertTrue(review.required_findings)
        self.assertEqual(
            review.required_findings[0].category,
            "merge_conflict_marker",
        )

    def test_nonblocking_validation_is_visible_to_model_review(self) -> None:
        client = FakeClient(
            '{"verdict":"accept","summary":"acceptable",'
            '"confidence":80,"findings":[]}'
        )
        review = model_review(
            client=client,
            objective="review warning",
            acceptance=("works",),
            files=(
                CandidateFile(
                    path="docs/example.md",
                    content="clean text\n",
                ),
            ),
            budget=BuildBudget(),
            validation_findings=(
                ValidationDiagnostic(
                    severity="warning",
                    code="markdown-fence-balance",
                    path="docs/example.md",
                    message="unmatched fence",
                    line=0,
                ),
            ),
        )
        self.assertEqual(review.verdict, "accept")
        self.assertEqual(client.calls, 1)
        self.assertTrue(
            any(
                item.category == "markdown_fence_balance"
                for item in review.findings
            )
        )

    def test_model_review_accepts_strict_json(self) -> None:
        client = FakeClient(
            '{"verdict":"accept","summary":"looks integrated",'
            '"confidence":88,"findings":[]}'
        )
        review = model_review(
            client=client,
            objective="add helper",
            acceptance=("helper works",),
            files=(
                CandidateFile(
                    path="skeleton/helper.py",
                    content="def helper():\n    return 1\n",
                ),
            ),
            budget=BuildBudget(),
        )
        self.assertEqual(review.verdict, "accept")
        self.assertEqual(review.confidence, 88)
        self.assertEqual(client.calls, 1)

    def test_static_nonblocking_findings_are_merged_into_model_review(self) -> None:
        client = FakeClient(
            '{"verdict":"accept","summary":"acceptable",'
            '"confidence":70,"findings":[]}'
        )
        review = model_review(
            client=client,
            objective="example",
            acceptance=("works",),
            files=(
                CandidateFile(
                    path="skeleton/helper.py",
                    content="value = eval('1')\n",
                ),
            ),
            budget=BuildBudget(),
        )
        self.assertEqual(review.verdict, "accept")
        self.assertTrue(
            any(
                item.category == "dynamic_execution"
                for item in review.findings
            )
        )

    def test_repair_prompt_only_promotes_required_findings(self) -> None:
        client = FakeClient(
            '{"verdict":"repair","summary":"needs fix","confidence":90,'
            '"findings":[{"severity":"high","category":"integration",'
            '"path":"skeleton/helper.py","message":"wire the result",'
            '"required":true},{"severity":"low","category":"style",'
            '"path":"skeleton/helper.py","message":"rename local",'
            '"required":false}]}'
        )
        files = (
            CandidateFile(
                path="skeleton/helper.py",
                content="def helper():\n    return 1\n",
            ),
        )
        review = model_review(
            client=client,
            objective="example",
            acceptance=("integrated",),
            files=files,
            budget=BuildBudget(),
        )
        prompt = repair_prompt(
            objective="example",
            files=files,
            review=review,
        )
        self.assertIn("wire the result", prompt)
        self.assertNotIn("rename local", prompt)


if __name__ == "__main__":
    unittest.main()
