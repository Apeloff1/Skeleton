# Browser-only original asset deposit — no Git LFS

This is a second, opt-in binary custody route, not an application release. The exact original set is compressed reversibly into 32 files (539,395,530 bytes total); each compressed file is below 25 decimal MB. Dedicated branch `emerald-original-deposit-r1` was created at `92b869149dc16190e658e6cb8d950ce460135859` with metadata only. **No compressed payload has been uploaded at creation.**

Extract all three delivery packages into one folder. On the signed-in GitHub [upload page](https://github.com/Apeloff1/Skeleton/upload/emerald-original-deposit-r1/artifacts/emerald/deposit-r1), select the 32 `.bin` files, not the ZIP containers. Commit directly to that isolated branch. If GitHub rejects a large combined upload, use several smaller batches on the same branch. Do not merge it into main. This route stores about 539 MB in ordinary Git history (unlike LFS); that cost is the tradeoff for no LFS client. No CI or release hold is overridden.

After upload, copy the final exact commit SHA and verify every byte:

```sh
python scripts/emerald_browser_deposit.py --commit <40-character-upload-commit>
python scripts/emerald_browser_deposit.py --commit <40-character-upload-commit> --output /trusted/empty-folder
```

Verify or reconstruct locally without any GitHub authentication:

```sh
python scripts/emerald_browser_deposit.py --local /path/to/extracted-shards --output /trusted/empty-folder
```

The independent pinned manifest and original full-file hashes are checked before publication; decompression is bounded to 24 MB per shard. No execution of archive contents, overwrite, automatic network transfer, release or claim of Unreal/RTX qualification. The output directory must be trusted and support hardlinks. Use existing offline web and native installers after reconstruction. An exact immutable remote readback receipt, not the mere presence of a manifest, establishes remote byte custody.
