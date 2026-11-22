# Source convergence R07 — v1 API edge, quotas and exact environment replay

**DRAFT / REVIEW ONLY / NO MAIN MERGE / NO AUTO-MERGE / NO RELEASE OR LIVE TRAFFIC**. Parent #5089 at `2eab3e36722281a85ed23bd01828095fd436032e`. Exact donor refs #5090 `fb99ab4cec6ce500507c4e9a4b76479181f10b3b`; #5091 `7b97d8ed05e73cfa3171272d3300489aa1c165eb`. Reuses 40 source blob identities; 21 mirrored, identical Git-object API entries. All source rights, tenant/security/canonical-data/CI/release holds remain active. Do not activate any route or provider as a result of file presence.

- #5090 remains an uninstalled bounded v1 API edge and distributed quota design. No server router registration, real multi-replica verification, production ingress or release authority. Confirm explicit tenant/principal constraints and locked no-eviction admission before adoption.
- #5091 adds exact environment replay and adversarial tests, with existing provider runtime untouched. No inference or model environment certification implied.
- AIFT-ENGINE-API `source_git_object_sha` must be recalculated from the resulting Git tree, and the destination mirror must remain source-equal except authorized overlays.
- Focused `pytest -q tests/api_v1_edge tests/api_v1_quota_store tests/test_gf_p0_16_environment_replay.py tests/test_gf_p0_16_environment_quarantine.py`; compile/import and complete exact-head security/architecture/CI, independent real device and tenancy checks remain mandatory.

Git object audit:
- #5090 `skeleton/api/v1_edge/__init__.py` `881100047d10175c7610a44db597359981674c0e`
- #5090 `skeleton/api/v1_edge/auth.py` `fe5688cabb4fb8501cf4e5393eb7118c7d595163`
- #5090 `skeleton/api/v1_edge/edge.py` `99786b6cc0cc2c1f7d5147818e26dfc1bc17b0bc`
- #5090 `skeleton/api/v1_edge/envelope.py` `4899e56cc3a002e78e3881d25df5d4e2cb2a1ab5`
- #5090 `skeleton/api/v1_edge/health.py` `60c7e554bb1703d9f77fe87d181f3f242117e250`
- #5090 `skeleton/api/v1_edge/idempotency.py` `3f522370455ab480461d1d4c9c6e9fccdbd5f436`
- #5090 `skeleton/api/v1_edge/quota_store/__init__.py` `4de043268d6c85f729de453a2ec3a2a29b186135`
- #5090 `skeleton/api/v1_edge/quota_store/headers.py` `4a2d9dffcd7240a052e792cfe0bf5de98d2dbc89`
- #5090 `skeleton/api/v1_edge/quota_store/limiter.py` `899d38e42968726df0e4122509680cba17864d5c`
- #5090 `skeleton/api/v1_edge/quota_store/memory.py` `2ec32456612e341803d11c39ea4ded719fa630fc`
- #5090 `skeleton/api/v1_edge/quota_store/policy.py` `042010aefa3b21162ab4580d67ee158317f58bb6`
- #5090 `skeleton/api/v1_edge/quota_store/remote.py` `f6dc7723ce29cc7142f9785549553bb58084b436`
- #5090 `skeleton/api/v1_edge/quota_store/store.py` `2acbe7568e263b3b34693c50b23d55279d5b7eee`
- #5090 `skeleton/api/v1_edge/quota_store/telemetry.py` `d077a563e0336d3e01d31698d1e6b0f5f905118e`
- #5090 `skeleton/api/v1_edge/quota_store/testing.py` `9eb549347d3110680b82f9b0e21e4ed9ab63ce4c`
- #5090 `skeleton/api/v1_edge/quotas.py` `b19143046d78ef2f8064bf36012643a2c8e02c8a`
- #5090 `skeleton/api/v1_edge/registry.py` `2098fb914afd822f781c1aa1b7dbbadc69caa67e`
- #5090 `skeleton/api/v1_edge/security.py` `3a55aa4c5efb3c0e2dea37791239470e2572b7af`
- #5090 `skeleton/api/v1_edge/tracing.py` `3c13760e008155de673d9cd72bfbca7e3ceae126`
- #5090 `skeleton/api/v1_edge/validation.py` `3d9dac1c44ffe71ee42fb1d62b44f572239559de`
- #5090 `skeleton/api/v1_edge/webhook_ingress.py` `7d3eed9a3d821372f86af04df33206480796794b`
- #5090 `tests/api_v1_edge/__init__.py` `8b137891791fe96927ad78e64b0aad7bded08bdc`
- #5090 `tests/api_v1_edge/conftest.py` `b7a1248652ac5e55bb85494cb2ba6950b44ec899`
- #5090 `tests/api_v1_edge/test_auth.py` `c2de73d00584735d4b946b9d96d683a8af3e62e8`
- #5090 `tests/api_v1_edge/test_edge_contract.py` `c5ceedd4050e3556524d9650efa4afd047fa0cae`
- #5090 `tests/api_v1_edge/test_quarantine_boundaries.py` `404b77a8de9be327de7ece6e8d35376fa004d3ab`
- #5090 `tests/api_v1_edge/test_quotas.py` `739bcb79c3e5a0475af2c98715fcdf6d7e898541`
- #5090 `tests/api_v1_edge/test_registry.py` `eb69e13f7b5dfddb0522ca393c0c001f6922e802`
- #5090 `tests/api_v1_edge/test_validation_tracing.py` `75ff14755556c34e9c3ad5a741e9ec5fa3195114`
- #5090 `tests/api_v1_edge/test_webhook_security_health.py` `ce56792fdf0039b82b0d53d51252d9b85b100b43`
- #5090 `tests/api_v1_quota_store/__init__.py` `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`
- #5090 `tests/api_v1_quota_store/test_counter_store_memory.py` `f8e33b9db4c5a36839837f2cd6ec8885815a8d5b`
- #5090 `tests/api_v1_quota_store/test_distributed_limiter.py` `aac42f0e4860b3b7ee2becb39b3688fa746688d6`
- #5090 `tests/api_v1_quota_store/test_edge_quota_integration.py` `feb6205636abef5d3790366894a0d21d7bf01bd0`
- #5090 `tests/api_v1_quota_store/test_policy_headers.py` `9acbca3a482ce8da01cf3f740394ea3ee7178fa4`
- #5090 `tests/api_v1_quota_store/test_quota_telemetry.py` `65647eeb5e85d251d24bcf53a2c27d2ae7ad8215`
- #5090 `tests/api_v1_quota_store/test_remote_store.py` `8e97510f939203722254f0512d05dae90e7cc51a`
- #5091 `skeleton/provider_environment.py` `fe46402597922cde5b7ee7321e757958ab1e0490`
- #5091 `tests/test_gf_p0_16_environment_quarantine.py` `64892dcda479f3ce3fc79697fa80319793ead125`
- #5091 `tests/test_gf_p0_16_environment_replay.py` `4bbb0411642f94ef21dccf1d455caed781686968`
