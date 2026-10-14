# Compile

The volume plane is complete when the clip tests pass and the shard census is a wc, not a slogan.

```bash
python volume_forge/test_clip.py
python volume_forge/skeleton_x100.py emit_x100 1
wc -l emit_x100/shard_000.py
python volume_forge/slice_verify.py emit_x100/shard_000.py
```

Expected test line: volume-ok.
Expected wc: 7650009.
Expected slice mass: 1.0392.

Do not add emit_x100 to git. Do not import the shard. Do not rewrite the deck.
The 200-shard figure 1530001800 is a projection. The header gap is 30200.
