# Game-building reference corpora

Optional generated design-reference text: planning patterns, game mathematics,
mechanics, assets, UX, music direction and improvement process notes. These are
text references, not audio/art files, executable games or measured gameplay evidence.

All original records are retained in deterministic `.gz` files. `manifest.json`
records the original path, source PR/commit, compressed/decoded SHA-256, byte count
and newline count. Old split-part names now have a `.gz` suffix. Existing compressed
expanded variants remain available. Parts and expanded variants can overlap; counts
do not establish unique ideas or content quality.

## Read a bounded sample

```python
import gzip
import itertools
import json
from pathlib import Path

root = Path("data/game_building")
manifest = json.loads((root / "manifest.json").read_text())
relative = manifest["entries"][0]["path"]
with gzip.open(relative, "rt", encoding="utf-8") as stream:
    for line in itertools.islice(stream, 5):
        print(line.rstrip())
```

Stream selected files instead of expanding every variant into memory. A full
verification compares both compressed and decoded digests with the manifest.
Reference-only corpus files are excluded from the application image source allowlists.
No startup, model training, native execution, rights approval or quality promotion is
granted by merely installing these files. Admission uses the existing dataset/source
and rights owners. Repository-authored content follows the root MIT license;
external inputs retain their own required rights review.
