# Bounded collision-aware tile routes

`python -m skeleton scene-tiles-route --demo` searches the original
Lantern Hollow tile game for a real playable victory. A route witness
contains only legal movement, canonical pickups and canonical exits; the
player must physically reach the brass key before using the locked gate.

`--target won|lost` selects the authored ending. `--source-json JSON`
searches an original authored map; `--session-json JSON` resumes search
from a verified checkpoint. `--max-states` and `--max-depth` bound work.
A budget-limited search returns `inconclusive`, not a false impossibility
claim. The default limits are 512 states and 24 actions; hard caps are
2048 states and 64 actions.

`--verify-json JSON` recomputes the bounded search and replays the
complete witness through canonical tile collision, pickup, exit and
portable export/import verification. Digests detect corruption but do not
authenticate authorship.

Focused validation:

```sh
python -m pytest skeleton/testing/test_scene_tile_route.py -q
python -m skeleton scene-tiles-route --demo
```
