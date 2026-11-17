# Emerald original binary transport without Git history bloat

The original 706132984-byte asset set is recovered and locally SHA-256 verified. Dedicated custody branch `asset-custody/emerald-20261117-r1-lfs`, pinned commit `d82d61541bc7ae3cb4bd2599b5836431828f79d7`, holds standard LFS pointers for three files. **The pointers are not proof that LFS objects exist.** Never merge the custody branch to publish artifacts. No application release, main write, or hardware certification.

With Python 3, Git LFS, and a GitHub write-authorized Git credential helper configured, put the three original files (or the two verified model parts and the two original archives) in one directory. Do not include an older model under the same name. Run:

```sh
python scripts/emerald_lfs_transfer.py --directory /path/to/downloads
python scripts/emerald_lfs_transfer.py --directory /path/to/downloads --upload
```

The first command verifies bytes offline; the second stages only three pinned objects in a temporary Git repository, uploads by object ID, and then independently reads back every byte from the immutable pointer commit. No repository clone, ordinary Git push, credential capture, or release API. Git LFS limits and account quotas apply; if upload or public media readback is unavailable, no remote success receipt is emitted. The remote operation may incur LFS storage/bandwidth usage. A failed readback does not roll back already uploaded LFS objects; rerun verification independently.

```sh
python scripts/emerald_lfs_transfer.py --verify-remote
python scripts/emerald_lfs_transfer.py --directory /trusted/empty-folder --download
```

Downloads are explicit, not automatic. Complete verified sets only, no overwrites, and hardlink support is required for exclusive local publication. The destination and temporary disk must be trusted. The exact repository admission pin is unchanged; installation remains through the existing offline installers. Source-only synthetic tests do not establish remote or hardware acceptance.
