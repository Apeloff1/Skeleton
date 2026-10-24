# Codex ↔ VM exact source parity

**Authority:** `main`'s Git commit SHA; never a branch name or a previous
pull request's passing checks.

**Scope:** Two distinct, readable Git checkouts on a trusted host. Codex's
private unpublished changes, a live VM filesystem, and any container state
are *not* accessible from a GitHub repository API. Do not report parity when
those readbacks have not occurred.

## Required on-host verification

On a trusted machine where both checkouts are mounted, independently read
the current 40-character SHA from GitHub's `main` and execute:

```sh
python scripts/check_codex_vm_parity.py \
  --codex-root /absolute/path/to/codex-checkout \
  --vm-root /absolute/path/to/vm-checkout \
  --required-sha PINNED_GITHUB_MAIN_SHA
```

The verifier:

1. Resolves each checkout as a real Git repository root. It rejects using
   the same checkout twice, a wrong HEAD, unsupported Git entries, and dirty
   or untracked Git paths.
2. Traverses every tracked Git entry and compares actual checkout bytes
   using SHA-256, executable-mode bits, and literal symlink targets. It also
   matches each file's actual bytes to the committed Git blob SHA-1, so two
   equally corrupted or `skip-worktree`-hidden files cannot pass.
3. Fails closed with a nonzero exit and `verdict=not_verified` on missing
   evidence, source drift or any error. The receipt does not expose file
   contents or credentials.
4. Reports `identical_tracked_source` and a deterministic source receipt
   only after *both* checkouts have been read successfully at the requested
   commit. Preserve that receipt with the VM deployment evidence.

**Not included:** ignored local configuration or secrets, untracked
databases and model weights, Docker image digests, dependency installations,
and running process state. An on-disk file match does not prove that a
service has been restarted using those files.

## One-checkout VM audit against a freshly pinned main

If the trusted operator can access the VM checkout but not a second Codex
checkout, use the independently pinned canonical main commit with the
complementary single-checkout auditor:

```sh
python scripts/audit_codex_vm_parity.py \
  --repo /absolute/path/to/vm-checkout \
  --fetch \
  --expected-main-sha PINNED_GITHUB_MAIN_SHA \
  --json /absolute/path/outside-checkout/vm-parity.json
```

The Git remote must be independently verified as the intended repository;
merely naming a remote `origin` does not establish GitHub authority. Without
`--fetch` and an independently pinned SHA, this script cannot issue an
`identical` CLI verdict. The on-host audit inspects actual worktree bytes,
committed-tree differences, staged changes, symlink targets, executable modes,
submodules, and untracked paths. Use `--include-ignored` only when audited
runtime state requires strict ignored-path equivalence. Review any excluded
build artifacts and model files separately.

These two tools have different evidence scopes: the two-checkout checker
asserts `identical_tracked_source` only for two independently read checkouts;
the one-checkout checker asserts `identical` only relative to its freshly
fetched, pinned Git main. Neither checks running image digests, memory state,
model weights, or services. Neither certifies unpublished private Codex edits.

## Separate runtime acceptance (required for a running VM)

- Read back the deployed VM's actual Git HEAD and working tree.
- Confirm the effective Compose configuration is consistent with
  `skeleton/app/manifest.json` using the repository's Compose parity check.
- Inspect *running* container image IDs/digests, image architecture,
  mounts, active model artifacts and model-provenance manifests; bind the
  resulting evidence to the same Git SHA.
- Verify API readiness and installer startup against actual VM services,
  not mocked fixtures. A successful CI run on GitHub is not deployment
  evidence.
- Roll forward only through the approved deployment flow. Never force-reset
  a dirty VM checkout or delete unpublished Codex edits to manufacture
  equality.

## Historical Codex branch handling

`codex/adaptive-ai-runtime-2026-10-20` is ancestral to current `main`.
`codex/ai-studio-foundations-2026-10-20` was reconciled by content in
PR #4227: 62/67 paths have identical blobs; five newer `main` versions are
retained. The October 15 Jeeves and first-install branches predate numerous
canonical repairs, so their diverged commit histories are not deployment
targets. Compare their unique capabilities and tests individually. Do not
overwrite current chat custody, file-tree parity or safety gates with
historical files.

**Completion condition:** GitHub merge receipt + current exact SHA +
on-host two-checkout parity receipt + runtime image/model/service readback.
Without the latter two, report **VM parity unverified**, never complete.
