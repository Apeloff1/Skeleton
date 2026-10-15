# Below-view controller, input capture, native graphs and receipts — 2026-10-15

The comparative studio's two emulator images now keep their entire image unobscured. A separately bordered physical-style controller panel is **bolted immediately below each game view**, never overlaid on the rendered frame. Each panel is constructed from one of the 169 canonical emulator hardware target identities and the exact selected libretro input-port topology.

The button/control wiring uses the existing verified **RetroPad abstract button masks** (including B/Y/Select/Start, directions, A/X, shoulders and triggers), libretro key codes and the existing mouse/pointer vectors. The UI supports 1–4 host controller ports; the native emulator worker independently validates controller type and bound data. Familiar console-style labels exist for NES/SNES, Sega, Nintendo handheld, PlayStation, Dreamcast, Saturn, Atari and selected others. Unsupported or uncertain historical physical schemes fall back **visibly** to a generic libretro RetroPad; no physical-controller fidelity is claimed. Core-specific descriptors and unusual peripherals need further device integration and actual core testing.

## Offline interactive controller workflow

The offline HTML comparison report is not a network server and cannot directly press a button inside a running native sandbox. Instead, touch/click the separate lower-panel virtual controls, choose a port, select one or more buttons for a chord, then choose **Record input frame** (up to 64). Export a JSON controller tape. The operator can pass it to the existing native qualification tool:

```bash
python3 scripts/qualify_game_emulator.py \
  --registry /srv/approved/cores.json \
  --target nes --core fceumm \
  --source /srv/homebrew/game.nes \
  --controller-device joypad \
  --controller-tape-json /srv/studies/my_tape.json \
  --runs 3
```

Analog axes, mouse displacements and pointer coordinates currently default to neutral in viewer drafts and must be edited in typed JSON if required. Core/native-device correctness and replay performance are separately verified. This is not a promise that every special controller is mapped or that browser controls drive a live core.

## Actual evidence display

Each real comparative native run appends one bounded receipt per actual policy action: input action, native frame SHA-256, native PCM SHA-256, frame/audio counters, chained transition receipt, objective brightness/audio/visual-change metrics and a linked provenance hash. Evidence remains a capped 64-step chain. The offline viewer shows an objective two-signal graph for each compared game, with independent scales and a collapsible per-step evidence log. The graph is measured telemetry, **not** a score for how enjoyable, playable or accurate a game is.

Tests: `tests/test_game_comparison_controllers.py` confirms catalog coverage, exact RetroPad mask bridging, supported port families, fallback honesty and invalid-target rejection. Unit source added, not executed on a real emulator in this patch.

References: https://docs.libretro.com/guides/input-and-controls/ and https://docs.libretro.com/development/input-api/.
