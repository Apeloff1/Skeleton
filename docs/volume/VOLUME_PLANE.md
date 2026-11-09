# Volume plane

Direct on Skeleton main. The deck is not this plane.

## Seals

| Stratum | Files | Lines | Census |
|---|---:|---:|---|
| organ | 2368 | 3329408 | census.py |
| masterplan | 200 | 15302600 | wc |
| x10 | 200 | 153003200 | wc |
| x100 shard 0 | 1 | 7650009 | wc |

x100 bindings are 850000 per shard, ten times 85000. Shard 0 is 303339093 bytes. First binding mass 1.0392. stored_prose 0. clip 1.1.

Two hundred shards project to 1530001800 lines. Header does not scale, so the projection sits 30200 under a naive 10x of 153003200. Bindings scaled exactly.

## Law

Mass may rise by at most prior times 1.1 per binding. A stamped mass with no trajectory is illegal. Pointer clauses only. No stored sentence. No coin.

## Disk

The full x100 tree is about 60 GB. This disk held one shard. The tree is not in git.

## Compile

```bash
python volume_forge/skeleton_x100.py emit_x100 1
wc -l emit_x100/shard_000.py
python volume_forge/slice_verify.py emit_x100/shard_000.py
```

Do not import the shard. 850000 functions exhaust the process.
