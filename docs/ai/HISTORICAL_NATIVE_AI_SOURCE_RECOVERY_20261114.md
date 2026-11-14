# Historical native AI source recovery — review candidate

Baseline main: `d5275f6cff2b660ec6b41455fedb51567b113ad5`.
Custody source: `31cb977d1f10ea5f75edbc714c9c1575c56a300b`.
The source is not treated as a merged ancestor; broader divergent changes
are still subject to reconciliation. This change restores missing paths only,
with narrowly scoped repairs. No runtime switch, model activation, hosted
fallback, provider ownership change, evidence signature, or release is authorized.

| Historical package | Source tree | Original files |
|---|---|---:|
| durable_jobs | 279fde2a384dd2d0d4634797b7fab6e3babaf6df | 702 |
| guarded_request | 4ab705b33be8ea49d9377aa46de8220736e1c6a8 | 409 |
| native_qualification | 47f24324856ebfb326ac1983d322033d74966614 | 507 |
| native_candidate | e2699e96f88d2ca1eb49d6a9fa67212911304d73 | 914 |
| native_genesis | 05cd4cab1fe230aa99fd5af10d15baf3255baae6 | 312 |
| native_supervised | 90208764bb12e6f6d5a9f6905043f7adb3871322 | 835 |

Recovered 175 historical docs and 216 test source files, plus the historical
durable-job profile (its acceptance flags remain false). The lower-case
`docs/ai/native_candidate/status.md` was restored as `task-status.md` to
avoid Windows case collisions with `STATUS.md`.

The existing runtime-root residual ownership and current model owner remain
unchanged. The six packages are candidate-only or test/adapter surfaces;
their presence does not establish a new authoritative deployment. The current
Jeeves and OfflineAIService entrypoints remain authoritative.

## Adaptation and limits

- Accept concrete pathlib Path implementations instead of comparing their
  exact type to the Path factory.
- Anchor private artifact directory creation and open to the same trusted
  parent descriptor, using the existing GGUF traversal guard. The helper is
  POSIX-only and cannot prove arbitrary same-UID attacker resistance.
- Verify envelope structure and TTL even after authenticated construction;
  support the canonical principal/model scope in the nonce fence, retaining
  isolated historical single-label namespaces for existing local callers.
- Do not regard the historical SQLite path-based connection as a proof of
  descriptor-bound SQLite custody. Full concurrency and same-UID threat
  qualification are outstanding.
- Historical fixtures, example reports and source comments are not current
  model, native device, security or release evidence.

## Qualification (not executed in the repository connector)

Run the focused recovery regression and the six restored families:

```sh
python -m pytest -q skeleton/testing/test_operational_ai_recovery_boundaries.py
python -m pytest -q skeleton/testing/test_durable_jobs*.py skeleton/testing/test_guarded_request*.py
python -m pytest -q skeleton/testing/test_native_qualification*.py skeleton/testing/test_native_candidate*.py
python -m pytest -q skeleton/testing/test_native_genesis*.py skeleton/testing/test_native_supervised*.py
python scripts/check_ai_file_tree.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Independent exact-head CI, security review, real licensed original-source
checkpoint training/evaluation, native local inference, device tests, Windows
and WSL2 boundaries, resource pressure and recovery qualification remain
required. No merge or release readiness claimed. Other historical branches
and paths remain open until reviewed against current main.
