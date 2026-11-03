# Cinder Ridge: retry-aware portable save backups

The ordinary campaign `export` remains a compact source-bound replay bundle.
It cannot reconstruct the chronology of retries after failed chapters. The
new `backup` command preserves the **complete transactional action ledger**,
including genuine retry events, in a versioned digest-checked portable file.

    python -m skeleton.game.gameplay.ridge_rescue consumer backup --slot adventure
    python -m skeleton.game.gameplay.ridge_rescue consumer verify-backup --file /path/to/backup.json
    python -m skeleton.game.gameplay.ridge_rescue consumer restore-backup --slot restored --file /path/to/backup.json
    python -m skeleton.game.gameplay.ridge_rescue consumer audit --slot restored

On Windows, pipe UTF-8 backup bytes through `--file -` to avoid unqualified
arbitrary-path/reparse behavior. The standalone `.pyz` supports the same
commands. A backup is bounded to 1,000,000 bytes and cannot overwrite an
existing save. Every historical action is replayed against the bundled
original campaign; both previous and next CAS heads must match, including
retry transitions. Session and history must reconstruct the exact same
canonical bytes before a new slot is admitted.

The consumer process smoke now verifies backup, restore and audit from
separate processes. The focused backup regression additionally forces a
legitimate failed chapter, retries it, earns both campaign endings, and
checks that the retry survives backup and restoration. Tests are authored,
not executed evidence; Windows device and release qualification remain held.
