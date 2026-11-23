# Offline Mongo restore — pinned parent/child directory custody

The existing Mongo WiredTiger cold-file scan in PR #5728 already used
`O_NOFOLLOW` for journal files and an opened `mongo_data` directory.
This extra source repair closes a **parent path substitution gap**:
opening `/private/restore/mongo_data` directly could still traverse a
parent changed between preflight and opened directory admission.

The revised scan pins the **private restore root** with an
`O_DIRECTORY|O_NOFOLLOW` descriptor first. It then opens
`mongo_data` via `openat("mongo_data", dir_fd=root_fd)`, checks the
child against a nofollow `fstatat` identity, and performs all catalog,
collection, index and journal scans from that child descriptor. Both
root and child paths are rechecked before accepting a receipt. The file
hash path remains pinned to opened regular-file descriptors.

The tests use **only disposable private fake WiredTiger data** and
exercise four distinct attacks: swapping the restore root after both
descriptors open; swapping `mongo_data` after `openat`; replacing the
parent path with a symlink before admission; and failures with open
directory descriptors to prove they are closed on denial. A source
test also checks that `mongo_data` is always opened with a valid
parent descriptor and the nofollow directory flags.

The verifier does **not** run `mongod`, parse WiredTiger pages, recover
journal records, load real Mongo documents, mutate production volumes,
pause real writers or claim atomic Mongo/SQLite/Chroma state. A successful
receipt remains static-file custody evidence only.

Focused exact-head acceptance:

```sh
python -m compileall -q scripts/local_ai_restored_mongo.py \
  skeleton/testing/test_local_ai_restored_mongo.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  skeleton/testing/test_local_ai_restored_mongo.py \
  skeleton/testing/test_local_ai_offline_three_store.py
```

Draft/review only; no merge, release or production state changes.
