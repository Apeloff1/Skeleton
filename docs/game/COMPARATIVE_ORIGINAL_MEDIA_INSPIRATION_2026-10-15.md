# Evidence-linked original game inspiration: vector assets, music, cutscenes, mechanics — 2026-10-15

The comparative emulator learning studio can now generate **real original media artifacts**, distinct from the protected games used as input observations. The separately operator-invoked `game_comparison_inspiration.py` accepts an intact native comparative-study result, **2–30 explicitly selected successfully observed games**, an original user-authored creative brief, a genre and a deterministic seed. It validates exact source report/step-evidence identity and emits **three creative stages** (earlier, middle, after). It does not read input ROMs, source screenshots, PCM, story, character graphics or protected music.

Each stage generates:
- **Original vector assets:** one editable standalone 512×288 SVG geometric illustration/scene, composed from seed and original palette with no source-game pixel or asset sampling.
- **Original synthesized music:** one actual playable 16-bit mono PCM WAV file (16 kHz, 3–5 seconds), synthesized from a generated pitch sequence, tempo, harmonics and envelope. It is not a remake or transcription of another game's melody.
- **Original cinematic director:** one JSON storyboard with 4/6/9 shots; camera types include high crane, low tracking, wide establishing, side dolly, orbit, shoulder angle, detail insert, reveal pan and top-down. Each shot carries start/duration, pan direction, zoom start/end, focal keyframes and transitions; it is not a rendered video.
- **Original gameplay and mechanics:** one typed, editable JSON proposal for stage-appropriate generic genre mechanics (platforming, physics, strategy, racing, dialogue, ecosystem, rhythm etc.) with movement, input, reactions, environment, NPC, consequences and audio integration axes. It is not compiled gameplay nor reverse-engineered source code.

The output creates twelve new artifacts, one full-source provenance graph, 12 original-file SHA receipts, linked source-game observation hashes and an **independent adversarial review queue** for input ergonomics, originality, cutscene pacing, audio timing, world continuity, mechanics, accessibility, human outcomes, regression and weight generalization. It also writes a standalone, local **HTML media gallery** with actual SVG images, playable generated WAV audio, links to cutscene/mechanics JSON and visible pending review tasks.

## Operator example

```bash
python3 scripts/generate_game_comparison_inspiration.py \
  --result /srv/studies/genre-evolution.result.json \
  --game homebrew_a --game homebrew_b \
  --genre exploration \
  --brief "An original luminous sky-garden with shifting paths" \
  --seed 418 \
  --output-dir /srv/studies/original-inspiration
```

The game names/paths are illustrative; an actual successfully completed native comparative report and selected game IDs are required. Files generated under `assets/`, `music/`, `cutscenes/`, `mechanics/` and a bounded `original_inspiration_receipt.json` share source identity. Open `original_inspiration_gallery.html` to inspect original graphics and music without launching a ROM or sending data to the network.

**Claims and limits:** No source-game art/audio or ROM is copied, but legal originality/rights and artistic quality still need independent review. Camera data is an editable shot *plan*, not a rendered movie. Mechanical JSON is a design *specification*, not a functioning playable game. Source-observation receipts are trace provenance, not automatic evidence of gained AI parameters or model-weight improvement. No neural model was trained or production weight promoted. Native video/music style recognition is not inferred from PCM hashes.

Tests: `tests/test_game_comparison_inspiration.py` validates generated SVG, WAV, shot and mechanics bytes and digest receipts using synthetic contract fixtures, but native emulation or trained model gains have not been verified by this repository patch.
