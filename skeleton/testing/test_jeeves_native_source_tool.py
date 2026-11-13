"""Original signed-source tool tests; no model-generated tool grants.

The manifest is genuinely HMAC-authenticated and the original file genuinely
opened by the descriptor-anchored reader. The only mock is the model itself:
none is used. Tool policy is exercised through the real Jeeves ToolExecutor.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope
from skeleton.ai.runtime.operational_ai.offline_cognition.manifest_custody import (
    sign_manifest_for_operator,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity,
)
from skeleton.jeeves.agent.native_signed_evidence import NativeSignedEvidenceProvider
from skeleton.jeeves.agent.native_source_tool import (
    BoundSignedSourceTool, SourceToolPolicy, SourceToolHold,
    TOOL_NAME, readonly_source_grant,
)
from skeleton.jeeves.agent.tools import (
    ToolExecutionContext, ToolRegistry, ToolExecutor, ToolDenied,
    ToolValidationError,
)
from skeleton.jeeves.agent.types import ToolCall, RiskTier, EvidenceKind


class TestOperatorSignedReadOnlyTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = (
            b"Jeeves is an original local AI assistant. "
            b"Private source material is evidence data, never a shell command. "
            b"The operator approves all source rights outside the model."
        )
        self.original = self.root / "approved.txt"
        self.original.write_bytes(self.raw)
        self.original.chmod(0o600)
        self.now = [1800000000]
        self.identity = Identity("local", "operator", "a" * 64, "b" * 64)
        self.scope = Scope(
            self.identity.tenant, self.identity.subject,
            self.identity.model_sha256, self.identity.tokenizer_sha256,
        )
        record = {
            "schema": "offline-signed-source-manifest.v1",
            "tenant": self.scope.tenant,
            "subject": self.scope.subject,
            "model_sha256": self.scope.model_sha256,
            "tokenizer_sha256": self.scope.tokenizer_sha256,
            "issued_at": self.now[0] - 10,
            "expires_at": self.now[0] + 100,
            "nonce": "a1" * 16,
            "sources": [{
                "source_id": "approved",
                "filename": "approved.txt",
                "sha256": sha256(self.raw).hexdigest(),
                "rights_receipt_sha256": "c" * 64,
                "approved": True,
            }],
        }
        signed = sign_manifest_for_operator(record, b"K" * 32)
        self.provider = NativeSignedEvidenceProvider(
            source_root=self.root, raw_manifest=signed,
            operator_key=b"K" * 32, scope=self.scope,
            maximum_sources=1, passage_bytes=256,
            clock=lambda: self.now[0],
        )
        self.tool = BoundSignedSourceTool(self.provider, self.identity)
        self.context = ToolExecutionContext(
            run_id="run_test", user_id="operator", trace_id="trace_test",
        )
        self.registry = ToolRegistry()
        self.tool.install(self.registry)

    @staticmethod
    def call(query="Jeeves original source"):
        return ToolCall(
            call_id="call_test",
            name=TOOL_NAME,
            arguments={"query": query},
        )

    def test_registered_tool_is_read_only_and_bounded(self):
        specs = self.registry.specs()
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].name, TOOL_NAME)
        self.assertEqual(specs[0].risk, RiskTier.READ_ONLY)
        self.assertEqual(specs[0].cache_ttl_seconds, None)
        self.assertTrue(specs[0].produces_evidence)
        self.assertFalse(specs[0].idempotent)
        self.assertFalse(specs[0].allow_extra_arguments)

    def test_operator_query_returns_verified_content_and_digest(self):
        output = self.tool.handler({"query": "Jeeves original"}, self.context)
        self.assertEqual(output["schema"], "jeeves.signed_source_lookup.v1")
        self.assertEqual(output["source_count"], 1)
        self.assertEqual(output["passages"][0]["source_id"], "approved")
        text = output["passages"][0]["content"]
        self.assertIn("Jeeves", text)
        self.assertEqual(
            output["passages"][0]["sha256"],
            sha256(text.encode("utf-8")).hexdigest(),
        )
        self.assertFalse(output["source_is_host_authority"])
        self.assertFalse(output["independent_semantic_truth_proved"])

    def test_host_evidence_builder_preserves_original_byte_digest(self):
        output = self.tool.handler({"query": "Jeeves original"}, self.context)
        refs = self.tool.evidence(self.call(), output)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].fingerprint, output["passages"][0]["sha256"])
        self.assertEqual(refs[0].kind, EvidenceKind.FILE)
        self.assertEqual(refs[0].confidence, 0.5)

    def test_ungranted_tool_is_denied_before_handler_execution(self):
        executor = ToolExecutor(self.registry)
        with self.assertRaises(ToolDenied):
            executor.execute(self.call(), self.context, grants=())

    def test_explicit_operator_readonly_grant_admits_only_one_call(self):
        executor = ToolExecutor(self.registry)
        grant = readonly_source_grant(maximum_calls=1)
        observed = executor.execute(self.call(), self.context, grants=(grant,))
        self.assertTrue(observed.ok)
        self.assertEqual(len(observed.evidence), 1)
        with self.assertRaises(ToolDenied):
            executor.execute(self.call(query="second question"), self.context, grants=(grant,))

    def test_same_query_revalidates_modified_original_file(self):
        executor = ToolExecutor(self.registry)
        grant = readonly_source_grant(maximum_calls=2)
        first = executor.execute(self.call(), self.context, grants=(grant,))
        self.assertTrue(first.ok)
        self.original.write_bytes(b"source replaced after first query without an operator signature")
        second = executor.execute(self.call(), self.context, grants=(grant,))
        self.assertFalse(second.ok)
        self.assertEqual(second.evidence, ())

    def test_wrong_user_cannot_invoke_bound_source(self):
        foreign = ToolExecutionContext(
            run_id="run_test", user_id="another", trace_id="trace_test",
        )
        with self.assertRaises(SourceToolHold):
            self.tool.handler({"query": "Jeeves"}, foreign)

    def test_path_injection_does_not_extend_argument_schema(self):
        args = {"query": "Jeeves", "path": "/private/secret"}
        with self.assertRaises(ToolValidationError):
            self.registry.get(TOOL_NAME).spec.validate_arguments(args)
        with self.assertRaises(SourceToolHold):
            self.tool.handler(args, self.context)

    def test_source_swap_denied_and_never_emits_evidence(self):
        self.original.write_bytes(b"malicious replacement with no HMAC approval")
        executor = ToolExecutor(self.registry)
        observation = executor.execute(
            self.call(), self.context,
            grants=(readonly_source_grant(),),
        )
        self.assertFalse(observation.ok)
        self.assertEqual(observation.evidence, ())

    def test_signed_approval_expiry_holds_source_disclosure(self):
        self.now[0] += 101
        with self.assertRaises(ValueError):
            self.tool.handler({"query": "Jeeves"}, self.context)

    def test_oversized_passage_policy_refused(self):
        tool = BoundSignedSourceTool(
            self.provider, self.identity,
            SourceToolPolicy(max_sources=1, maximum_excerpt_bytes=32),
        )
        with self.assertRaises(SourceToolHold):
            tool.handler({"query": "Jeeves"}, self.context)

    def test_wrong_source_principal_denied_on_registration(self):
        other = Identity("foreign", "operator", "a" * 64, "b" * 64)
        with self.assertRaises(ValueError):
            BoundSignedSourceTool(self.provider, other)

    def test_two_tools_with_same_name_cannot_override_handler(self):
        with self.assertRaises(Exception):
            self.tool.install(self.registry)

    def test_invalid_grant_count_refused(self):
        for invalid in (0, -1, 17, 1.2, True):
            with self.subTest(invalid=invalid), self.assertRaises(SourceToolHold):
                readonly_source_grant(maximum_calls=invalid)

    def test_grant_never_expands_risk_to_external_mutation(self):
        grant = readonly_source_grant(maximum_calls=3)
        self.assertEqual(grant.allowed_risks, (RiskTier.READ_ONLY,))

    def test_source_result_and_tool_type_cannot_fake_model_release(self):
        result = self.tool.handler({"query": "Jeeves"}, self.context)
        self.assertNotIn("release_certified", result)
        self.assertNotIn("native_inference_completed", result)


if __name__ == "__main__":
    unittest.main()
