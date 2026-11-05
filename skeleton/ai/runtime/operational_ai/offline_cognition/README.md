# Offline cognition and operational AI capability fabric

This package is a source-controlled architecture for offline AI retrieval,
memory, context management, planning, admissions, tools-as-inert-proposals,
real GGUF supervisor receipt consumption, deterministic evaluation and
auditable restart. Its shared Python core contains finite algorithms and
scope checks. Sixty-four operator-domain capability packages bind these
primitive operations to the selected resource and provenance contracts.

The authoritative model execution remains the existing
`SupervisedAI`/`ExecutionSpine` with installed GGUF digest validation,
private SQLite state, owner authentication and source-bound receipts.
Nothing here invents generated text or permits an unverified model to
modify files or call network providers. A signed operator token or model
rights proof must originate outside the LLM.

```bash
python -m skeleton.ai.runtime.operational_ai.offline_cognition.cli
python -m unittest discover -s skeleton/testing -p 'test_offline_cognition_*.py' -q
```

The source casebooks hold 64 x 32 immutable profile scenarios, including
30 fail-closed adversarial mutations per domain. These are schema/provenance
regressions, **not** real native-model or hardware qualification.

Real laptop tests, third-party checkpoint rights, Windows/WSL2 installation,
cold restart, exact-head Merge Readiness/Backend Quality/App E2E/security,
independent review, workload latency and privacy/consent review are separate
required release holds. No skipped or missing gate is success.
