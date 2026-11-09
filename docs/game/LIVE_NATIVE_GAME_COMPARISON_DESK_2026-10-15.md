# Operator live comparative emulator desk — October 15, 2026

## What is implemented

An **explicit, locally run dual-screen browser desk** backed by the existing sandboxed libretro emulator host. This is not the earlier static after-the-fact HTML comparison. The operator selects one cohort from an existing 2–30-game study and launches **2–10 currently approved native games** at once. The browser can display any two of those sessions side by side, with its controller panel physically **below** the corresponding game image, never over it. It can advance either game, both, or **all active lanes concurrently**, using exact approved multiport raw input through the actual `EmulatorEnvironment.input_step` worker API.

An authenticated local HTTP server binds to **127.0.0.1 only** and serves a self-contained responsive page. The browser sends controls rather than paths, code, emulator binaries or network URLs; inputs are validated by the existing libretro host. Supports joypad, keyboard, analog (4 axes), mouse button/delta and pointer touch/coordinates where the installed core permits them. A known hardware-style controller legend is a UI convenience, **not** proof of physical pad mapping. Unmapped systems retain a visibly generic RetroPad panel; special peripherals still require implementation and native qualification.

The native viewer includes frame screenshots, current image/audio SHA-256, per-game event charts, collapsible exact step receipts, four-port draft controls, local notes export, per-game resets and full evidence JSON export. Different selected games have independent control maps. Up to ten native games are active, but only two are rendered simultaneously; operators can switch the visible pair without restarting the others.

### Explicit local command

```bash
python3 scripts/live_game_comparison.py \
  --manifest /srv/studies/my_comparison.json \
  --registry /srv/skeleton-emulators/cores.json \
  --batch 0 --rights-acknowledged \
  --max-steps 256 --idle-seconds 900 \
  --port 8765
```

For a subset in the same cohort, add `--game first_id --game second_id` (or up to ten total). Then **on the same machine** open `http://127.0.0.1:8765/`. If the port is busy, choose another operator-approved port; `--port 0` requests an OS-selected free loopback port, which is printed by the command. Closing the terminal with Ctrl+C or pressing **Stop & close workers** disposes of the underlying native sessions; an explicit idle cutoff also closes the server and workers.

Running a live emulator requires operator-confirmed rights to the actual local source media. That acknowledgment is not a legal opinion. Registry cores must already be installed and approved and file authority is rechecked by the existing host. The server does **not** download or bundle ROMs, BIOS, native cores, models or source media.

## Limits and native safety

- Exactly one valid selected study batch; **2–10 native lanes**, never an implicit 30-simultaneous-session run.
- Up to **256 native input steps per game over the whole live desk lifetime**, up to four explicit native resets per game; bounded HTTP input and retained evidence; no unbounded background training.
- Games must pass the existing disk-budget preflight and fit **in a single concurrent wave**. Insufficient temporary disk space rejects startup rather than silently launching partial results.
- Loopback-only binding, strict Host and same-origin POST checks, random process token, no cross-origin sharing, CSP nonces, no caches and no untrusted arbitrary command/path endpoints. The token is embedded in the local operator page, so **other processes on the same host are within the local machine trust boundary**. Do not bind it to a public interface or reverse proxy.
- Every step passes through the existing isolated worker. Unsupported device or core behavior fails as native evidence, not fabricated replay success. Multi-lane input is concurrent but not perfectly frame-synchronized across unrelated core clocks.
- No new training or production weights are automatically updated. User notes are local until exported for separate review.

## Verifying exported input and comparing fresh runs

From the local desk choose **Export native evidence**. Each exported game includes exact normalized input vectors, native frame/audio/transition SHA-256, input step count, reset generations, approved core and content identities, and a chained SHA-256 receipt for each step **and reset**.

Check the chain without launching any ROM:

```bash
python3 scripts/qualify_live_game_comparison.py \
  --evidence /srv/studies/live_native_evidence.json \
  --output-dir /srv/studies/review
```

To **actually run 2–10 fresh approved native workers** for one recorded game and epoch (up to 64 steps per epoch):

```bash
python3 scripts/qualify_live_game_comparison.py \
  --evidence /srv/studies/live_native_evidence.json \
  --manifest /srv/studies/my_comparison.json \
  --registry /srv/skeleton-emulators/cores.json \
  --game first_id --episode 0 --runs 3 \
  --rights-acknowledged \
  --output-dir /srv/studies/review
```

The qualifier checks native ROM/core/source digests against the live evidence and **runs fresh native workers** using the exact saved controller tape. It reports both internal mirror consistency and whether the resulting frame/audio hashes match the original live session. A session with more than 64 steps in one reset epoch is **not quietly truncated**: native replay qualification requires an independently bounded <=64-step episode, while offline receipt-chain verification still covers all 256 steps. Actual core/session execution can vary if a game has nondeterministic state or a native reset does not restore all hidden behavior; such mismatches remain explicit.

The baseline qualification runner also received a necessary bug fix: when only a raw multiport tape is supplied, it now correctly sets `max_steps=tape_length` rather than evaluating `len(actions)` when `actions` is None.

### Current qualification boundary

This pass adds concrete runtime and HTTP paths plus tests using synthetic fake workers. **Actual native libretro game play, exact physical controller compatibility, hardware accuracy, performance of ten real concurrent disc cores, and measured training/LLM-weight improvements have not been demonstrated by this code-editing session.** Source-level unit/HTTP tests were added but not executed in this session. The user must use the approved installed core registry, lawful game sources and available local disk/CPU to qualify live operation.

## Held controller input bursts

The live browser now supports **1, 2, 4 or 8 native steps per press**. The selected controller chord is held through every actual `input_step` in the burst, for one game or all eligible active games. Each step has its **own frame/PCM and exact-controller SHA-256 record** and is included in the reset-aware export. Only the final native preview of the burst is encoded as PNG, avoiding repeated image encoding overhead. The server preflights the *entire requested burst* against every lane's 256-step lifetime limit before executing any of the lanes, so an over-limit burst is rejected without partial execution.

This is bounded operator-driven multi-step playback, not a claimed 60 FPS streaming engine, real-time audio streaming, or physical-controller latency qualification. The browser preserves its below-screen controller placement and clearly shows what was or was not actually executed.
