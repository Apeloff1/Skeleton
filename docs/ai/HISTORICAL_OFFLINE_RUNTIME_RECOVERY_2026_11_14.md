# Historical offline runtime recovery — review-only

Pinned recovery source: 3fa3c461b3759a5dcc83ab2325b44df9760070e3;
base: d5275f6cff2b660ec6b41455fedb51567b113ad5.

Six missing package subtrees (3,679 tracked files) and 216 associated tests
plus six historical runbooks were recovered without replacing current-main
files. The following package roots belong to the existing governed residual
AI-native runtime owner; their restoration is not authorization to serve a
model, promote weights, change API identity or supersede the active service.

- durable_jobs: durable work queue / native dispatch.
- guarded_request: consent-bound request admission and pressure control.
- native_qualification: real-model evaluation and private receipts.
- native_candidate: candidate-only training.
- native_genesis: original-data native initialization.
- native_supervised: completion-only supervised alignment.

Initial repair replaces impossible exact pathlib.Path checks and anchors
private output-directory creation to canonical trusted parent descriptors.
The real canonical root opener remains in use; POSIX-only custody is not
a Windows qualification. No route, workflow or launcher was rewired.

Validation in order (commands not executed by the recovery connector):

1. python scripts/check_ai_file_tree.py
2. python -m compileall -q skeleton/ai/runtime/operational_ai
3. python -m pytest -q skeleton/testing/test_recovered_native_path_custody.py
4. python -m pytest -q skeleton/testing -k 'durable_jobs or guarded_request or native_qualification or native_candidate or native_genesis or native_supervised'
5. API compatibility, dependency audit, native device and security
   qualification, private storage failure/restart, and exact-head CI.

Historical tests are restored, not certified. Existing tests that assume a
world-writable temporary parent may require explicit trusted test roots;
do not bypass the production ancestry guard. Independent runtime and
release evidence remains mandatory. No automatic activation.

## Second recovery pass

Restored 169 historical domain runbooks and specifications, one durable-jobs
machine profile (all acceptance booleans remain false), and the missing rescue
quest regression suite. Historical `native_candidate/STATUS.md` is restored as
`native_candidate/source_inventory_status.md` to avoid a case-insensitive
collision with the independent `status.md` training-domain guide. These are
historical source records, not current runtime or release evidence. No old
workflow or architecture metadata is substituted for the current main version.
