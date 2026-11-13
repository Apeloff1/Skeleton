# Partial offline install quarantine inspection

A failed source installation intentionally leaves the reserved directory
unqualified for operator quarantine. Never automatically delete or overwrite
it. Use the read-only `--inspect-install-quarantine` app mode with
`--output` (existing directory), `--archive`,
`--expected-archive-sha256`, `--expected-manifest-sha256`, and
`--trusted-local-operator`.

The inspector validates a canonical independently pinned archive and a
descriptor-safe existing source directory. It reports bounded counts of
missing, extra and mismatched regular files without changing any source
files. Unexpected symlinks, nonregular entries, changing directory identities,
or archive substitutions fail closed. If the inventory is complete and matches
the archive, the original world is replay-verified; even then quarantine is
not cleared and the installer, security gates, signed package, rights and
device qualifications remain independent holds.

Focused acceptance:
`python -m pytest -q skeleton/testing/test_app_offline_install_quarantine.py`
