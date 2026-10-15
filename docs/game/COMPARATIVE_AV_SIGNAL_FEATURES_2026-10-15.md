# Comparative non-reconstructive visual and audio features — 2026-10-15

The comparative studio previously showed actual native PNG previews, RGB frame hashes, PCM hashes, brightness and audio RMS. It now derives **bounded numeric signal-texture features** from real libretro RGB24 frames and s16le stereo callbacks, at the earlier, middle and after checkpoint of every successfully observed game.

**Visual evidence:** sixteen-bin luminance histogram, luminance entropy (bits), bright/dark/occupied fractions, sampled scanline edge-change ratio, normalized mean RGB and sampled channel range. At most **8,192 pixels** are sampled for each checkpoint to avoid scanning full high-resolution emulator frames.

**Audio evidence:** mono and per-channel RMS, stereo energy imbalance, near-silence fraction, sign-change ratio, normalized mean sample change and peak fraction from at most **4,096 stereo PCM frames**. An empty audio buffer is explicitly marked `audio_emitted: false`. Unavailable sample rates are not guessed.

These features are **non-reconstructive aggregates**. Neither the user-facing Dragon knowledge cards nor the synthesis object stores copies of protected source-game frames, PCM waveforms or audio recordings. They cannot establish actual sound/music style, emotional tone, game logic, camera behavior, video timing accuracy or comparative quality on their own.

For two fully observed games, the comparison report now includes the absolute differences of these normalized measurements for each of the three timepoints. The standalone HTML viewer shows individual feature values and differences. Jeeves/Dragon synthesis gets the same measured fields with original stage source receipts; locally authored notes remain distinct from these objective metrics.

Tests were added in `tests/test_game_comparison_signal_features.py` using synthetic RGB/PCM numerical fixtures only; no proprietary media or native emulator was executed in this repository change.

This is a measurement enhancement, not a model training pass. Production weights, legal rights, user judgments, and quality rankings remain separate and unverified.
