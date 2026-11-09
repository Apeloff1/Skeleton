# Milestone: source-bound native multispectral audiovisual evidence — October 15, 2026

The comparative emulator lab already recorded actual native video/PCM SHA-256 and decimated texture statistics. This pass adds **time-local and coarse spatial/spectral descriptors** for controlled experimental reasoning without copying original video frames, music, or game art into user-facing knowledge packages.

## Actual measurement

`skeleton/jeeves/game_comparison_multispectral.py` calculates:

- **Native 4×4 spatial-change grid:** per-tile mean normalized RGB change and percentage of sampled pixels changing above a fixed threshold. Up to 8,192 RGB24 positions are read per pair. Reports total changed ratio, normalized change magnitude and signed mean luminance shift. These are measurements, **not** optical flow, player location, animation classification, or camera-motion understanding.
- **Native PCM spectral texture:** short stereo samples from the emulator's real s16le output are Hann-windowed and summarized as 8 non-reconstructive DFT-bin relative energies, approximate bin-index spectral centroid and activity. Up to 512 decimated stereo frames are sampled. Does not transcribe a melody, identify a song, claim emotional context or generate licensed music.
- **SHA provenance:** Before features are computed, exact source RGB/PCM buffer SHA-256 must match the native host's frame metadata. A different frame size yields `spatial=None` with a stated geometry-change limit, rather than inventing a motion vector.

## Connected uses

The **live multi-game desk** attaches these abstract features to every actually captured controller-step receipt when real native bytes are available. The source-contract fake worker deliberately yields `None` instead of fabricated multispectral measurements.

The **controlled A/B experiment runner** now measures features for each recorded native step, includes their values under the step's hash chain, and calculates abstract deltas at the modified-action checkpoint, subject to the pre-intervention and repeatability gates. The **offline dashboard** shows available spatial energy/frequency statistics alongside the observed video/audio traces. The **Dragon knowledge review bridge** receives numerical, rights-pending evidence only; no image/PCM payloads or trained model weights are promoted.

The 16 coarse movement tiles may describe where frame intensity changed, but they do not disclose the original pixels or identify which game event caused a change. Likewise, spectral bins are simple signal processing, not audio/music understanding.

Synthetic tests in `tests/test_game_comparison_multispectral.py` validate finite audio, empty/silent spectra, spatial RGB transitions, original data-hash binding, resolution changes and descriptive-only comparison. Included in the manual focused qualification workflow to avoid adding push-trigger CI congestion.

**No actually installed emulator or rights-cleared ROM was run by this GitHub edit.** Source-code changes and unit fixtures are not evidence of measured AI improvement.
