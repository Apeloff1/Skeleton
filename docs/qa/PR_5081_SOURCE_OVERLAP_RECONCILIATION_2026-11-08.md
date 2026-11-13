# PR #5081 / #5079 overlap and selective source custody

Baseline main-integration parent: #5074 `5166439f8f79319efc6099f49b05e28b19abef6c`.

Source: #5081 exact review head `ce4f067dd0acd5b7b45395b3e68bdfad00140d5d`, a separate **held draft**. Its implementation fixes in `.machine/repository.toml`, `backend/core/lazy_registry.py`, `skeleton/app/offline_delivery_archive.py`, and `skeleton/testing/test_ai_next_model.py` overlap the already implemented fixes on #5079. No automatic integration or double-merge of those implementation blobs is authorized.

Unique regression source cherry-picked **without modification** from #5081 head:

- `skeleton/testing/test_app_offline_archive_schema_parity.py` (source Git blob `96e5ff0d2f50982c24278f8fac0176cc35935540`): end-to-end resealed Studio ZIP rejection; forged project, missing custody, false publication and noncanonical manifest.
- `skeleton/testing/test_repo_machine_inventory_budget.py` (source Git blob `7eeee52dea9c1717bbb538e2de94bbbc622dc707`): real enumerator exact-bound and one-over-bound denial, plus a finite budget check.

#5079's existing stricter/fail-closed audit guards, on-disk 19-source registry, GGUF descriptor custody and release-denial semantics are retained. #5081's alternative pytest basename rename is not imported because the #5079 packaging repair passes both colliding test modules unmodified. Do not delete, merge or close #5081 or its source branch as a side effect of this provenance audit.

Required validation: exact PR-head focused pytest for both donor modules, native and Studio source regression, full repository inventory with truncation denial, mandatory exact-head GitHub checks and independent security review. **No main merge, release, signing, device, native-inference or first-install certification.**
