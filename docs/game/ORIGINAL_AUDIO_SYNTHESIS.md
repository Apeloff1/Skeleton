# Original offline PCM sound assets

This existing audio-plane extension synthesizes **original, deterministic** mono
16-bit PCM WAV sound effects without a model, network request, audio sample pack,
licensed recording or third-party synthesis library. It is not speech synthesis,
music generation, spatial audio, a real-time mixer, or device audio qualification.

```sh
python -m scripts.game.synthesize_original_sound skeleton/audio/fixtures/harbor_chime.json --inspect
python -m scripts.game.synthesize_original_sound skeleton/audio/fixtures/harbor_chime.json --out chime.wav
python -m unittest skeleton.testing.test_original_synthesis -v
```

Original CC0 examples are `harbor_chime.json` (triangle) and `footstep.json`
(seeded noise). Every patch explicitly carries author, CC0-1.0 rights declaration,
version, waveform, sample rate, frequency in milli-Hz, duration, gain,
attack/release envelope and deterministic seed. The rendered WAV receipt binds
the source manifest digest to WAV SHA-256 and the canonical `AudioAsset` envelope.
A rights declaration is **not** independent verification of an imported asset.

Supported waveforms: square, triangle, saw, seeded xorshift32 noise.
PCM uses fixed-point phase and integer envelope math for byte-identical output
across Python platforms. A WAV file is at most 3 MB; duration at most 30 s;
sample rates 8, 16, 22.05, 44.1, or 48 kHz; frequency is bounded below
Nyquist. Invalid JSON, oversized files, unsupported fields, illegal envelope,
invalid provenance and existing output destinations fail closed. CLI writes use
exclusive creation, restrictive permissions and fsync. The operator must choose
a trusted parent directory; no race-free parent-dir traversal or cryptographic
asset signing is asserted. `--inspect` computes an in-memory digest without
writing. Outputs are original synthetic audio, not borrowed media.
