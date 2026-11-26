# Original Emerald binary publication

The original 706,132,984 bytes have been split and reassembled with exact SHA-256 verification in the operator session. The checked-in manifest records 22 raw binary chunks, each no larger than 33,554,432 bytes. Five sibling payload drafts target this integration branch. Their initial marker files are **not binary publication**. Missing or mismatched chunks fail their exact-head custody check.

| Group | Raw bytes | Parts |
| --- | ---: | ---: |
| web | 48,249,605 | 2 |
| source | 194,733,639 | 6 |
| model-a | 167,772,160 | 5 |
| model-b | 167,772,160 | 5 |
| model-c | 127,605,420 | 4 |

Download the five separately supplied publication ZIPs into one directory, unchanged. In an existing authenticated checkout with this infrastructure branch checked out, run:

```sh
python scripts/publish_emerald_binary_drafts.py verify-bundles --bundles /path/to/bundles
python scripts/publish_emerald_binary_drafts.py publish --bundles /path/to/bundles
python scripts/publish_emerald_binary_drafts.py collect --output /path/to/new-original-assets
```

Use --group to resume individual pushes. Optionally use --sign for configured signed Git commits. The publisher checks the original pins, all selected bundles, both origin URLs, the remote manifest and chunk contents; pushes only fast-forward exact-byte commits to the five existing payload branch names. It uses a temporary index rather than disturbing the active worktree. The collector fetches those exact draft branches without merging and reconstructs the three original files only after their complete SHA-256 checks. Existing output directories are not replaced. Use a trusted checkout and output directory; configure Git authentication beforehand. No token is requested by the script.

This is bulk binary transport, not an Unreal build, artistic approval, physical RTX qualification, merge or release. The connector used for the initial drafts cannot transfer container binary files into GitHub. Actual bytes remain in the verified operator bundles until an authenticated push succeeds. Do not mark delivery complete until all five remote checks and full reassembly pass.
