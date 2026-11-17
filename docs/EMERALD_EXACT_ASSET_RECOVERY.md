# Recover original Emerald bytes from retained downloads

Run on the machine that received the three original files:
```sh
python scripts/recover_emerald_assets.py --root /path/to/downloads --root /path/to/backup
```
Names are not trusted: discovery filters exact pinned sizes, opens regular files and compares full SHA-256. Renamed original files are eligible. It never follows directory links or Windows reparse points; directory, candidate, depth and hashed-byte limits are explicit. Unreadable or truncated results are not evidence of absence. No files are copied by default.

For a complete exact match, create a trusted empty destination yourself, then rerun with `--recover-to /path/to/empty-directory`. Existing files are never overwritten. Filesystem hardlink support is required for exclusive publication; source digest is rechecked while copying. Then use the offline preflight and existing installers. This does not retrieve files from ChatGPT's remote storage or certify rendering, artistic quality or hardware.