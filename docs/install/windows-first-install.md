# Windows first install (native, no Docker)

This guide takes a Windows 10/11 PC from nothing to building and playing a game with
Skeleton. It uses one PowerShell bootstrap and one launcher. It needs no Docker,
no MongoDB and no administrator rights.

| You get | How |
| --- | --- |
| The Skeleton API on `http://127.0.0.1:8710` (loopback only) | `skeleton.cmd start` |
| A playable Godot project from one sentence | `skeleton.cmd build "..."` |
| The game in a Godot window, or a headless proof that it plays | `skeleton.cmd play`, or `skeleton.cmd play -Check` |

The full studio, with the web UI, Jeeves chat, the crawler and Mongo-backed memory,
still runs through Docker Desktop and `scripts/install_app.py`. See
[Full studio (Docker Desktop)](#full-studio-docker-desktop). The native path here is
the quickest way to build and play games, and it is what the
`windows-first-install.yml` workflow checks on `windows-latest`.

## Requirements

- Windows 10 22H2 or Windows 11, 64-bit (x64).
- About 4 GiB free disk space.
- Internet access for the first install (Python packages and the Godot engine).
- Git, or a downloaded ZIP of the repository.
- Python 3.11 or newer. The bootstrap can install Python 3.11 for you with `winget`.

## Install (one command)

Open **PowerShell** (not as administrator) and run:

```powershell
git clone https://github.com/Apeloff1/Skeleton.git
cd Skeleton
scripts\windows\bootstrap.cmd -Start
```

`bootstrap.cmd` runs `bootstrap.ps1 -InstallMissing` with `-ExecutionPolicy Bypass` for
that one process. Your machine's execution policy is not changed. If you prefer to run
the script directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\bootstrap.ps1 -InstallMissing -Start
```

What the bootstrap does, in order:

1. **Checks the computer:** 64-bit Windows, PowerShell 5.1 or 7+, free disk space,
   and whether long paths are enabled (optional).
2. **Finds Python 3.11+.** It tries the `py` launcher (newest first), then `python` on
   `PATH`. With `-InstallMissing` it installs `Python.Python.3.11` (and `Git.Git`) for
   your user with `winget`.
3. **Installs Godot 4.6** (`Godot_v4.6-stable_win64.exe.zip`) from the official
   GitHub release into `%LOCALAPPDATA%\Skeleton\tools\godot-4.6-stable`. It checks the
   archive's SHA-512 against the pinned value before extracting. A mismatched download
   is deleted and the install stops.
4. **Creates `.venv`** in the checkout and installs Skeleton (`pip install -e .`). The
   exact versions in `backend/requirements.txt` are used as constraints.
5. **Writes your configuration** under `%LOCALAPPDATA%\Skeleton\config`. That folder is
   readable only by your Windows account (inheritance removed). Secrets are stored
   separately in `secrets.json`, encrypted with Windows DPAPI for your user:
   - a freshly generated 256-bit request-seal secret (`GF_SEAL_SECRET`)
   - your hosted API key, only if you choose a hosted provider
6. **Runs the doctor.** With `-Start` it starts the API. With `-Smoke` it also builds
   and plays a sample game.

Re-running the bootstrap is safe. It keeps your existing seal secret, provider choice
and games. Pass `-RotateSeal` to generate a new secret.

### Choosing an AI provider

Building games does **not** need a model. The game builder is a deterministic
compiler, and a model can only propose bounded design changes.

| Provider | When to pick it | Setup |
| --- | --- | --- |
| `none` (default) | Build and play games right away | Nothing else needed |
| `openai` | Hosted model for chat and design help | `-Provider openai -Model <model>`. The key is read from `OPENAI_API_KEY` or asked for (hidden input). Add `-OpenAIBaseUrl https://...` for an OpenAI-compatible endpoint. |
| `local` | Guarded local GGUF model | Advanced. It needs the trusted guard bootstrap. See [FIRST_INSTALL_AI_AND_CRAWLER.md](../ai/FIRST_INSTALL_AI_AND_CRAWLER.md). |

Change it later with:

```powershell
scripts\windows\skeleton.cmd config -Provider openai -Model gpt-5.5
scripts\windows\skeleton.cmd stop; scripts\windows\skeleton.cmd start
```

API keys are never accepted as plain command-line text. Use `OPENAI_API_KEY`, the
hidden prompt, or `-ApiKey (Read-Host -AsSecureString)`.

## Skeleton Studio (in your browser)

```powershell
scripts\windows\skeleton.cmd studio
```

`studio` starts Skeleton if it is not already running and opens **Skeleton Studio** in
your default browser at `http://127.0.0.1:8710/studio/`. Studio covers the whole
journey without a terminal:

1. **Welcome / My games**: first-run guidance, then every game on this computer with
   its genre, proof and last playtest.
2. **New game**: describe the idea (or start from an example) and choose whether the
   build must pass a headless playtest. Empty and over-long briefs are explained inline.
3. **Building**: live progress, the current stage and elapsed time. A failed build
   shows the reason and a one-click way back to edit the brief.
4. **Game**: *Play in Godot* opens a real Godot window, *Run playtest* proves the core
   loop and the scripted win again, *Download project (.zip)* exports it, and the file
   browser lets you read every file and edit scripts, scenes and data (Ctrl+S saves;
   Tab indents, Escape releases the Tab key, Ctrl+M toggles it back).
5. **Settings**: the same checks as `doctor`, the provider and model, and where files
   live.

Studio is keyboard-first and targets WCAG 2.2 AA: a skip link, visible focus, focus
moved to each page's heading, 44-pixel targets, live regions for progress, and
support for reduced motion, Windows high-contrast (forced colours) and narrow windows.

The link `studio` opens contains a per-launch token. Studio stores it only in that
browser tab, and it changes every time Skeleton starts. If you see **Open Studio from
Skeleton**, run `skeleton.cmd studio` again. Use `serve --no-studio` to run the API
without Studio.

## Build and play from the terminal

```powershell
scripts\windows\skeleton.cmd start
scripts\windows\skeleton.cmd build "A small platformer. Fantasy: a fox on rainy rooftops. Core loop: run and jump to the far gate. Scope: small prototype."
scripts\windows\skeleton.cmd play
```

- `build` sends the brief to `POST /api/v1/game/build`. The canonical builder compiles
  the brief, generates content, writes the Godot project and **plays it headlessly**
  (`playtest=require`) before it reports success. The proven files are saved under
  `%LOCALAPPDATA%\Skeleton\games\<title>-<timestamp>`.
- `play` opens the newest game in a normal Godot window. `play <folder>` opens a
  specific one.
- `play -Check` proves a game without a window. The main scene must print
  `CORE_LOOP_OK`, and the bundled input replay must print `FORGE_INTERACTIVE_OK` after
  a real win, pause and restart.
- `games` opens the games folder in Explorer. Each game is a normal Godot project you
  can open and edit in the Godot editor.

Briefs work best with a genre (platformer, top-down shooter, roguelike RPG), a
fantasy, a core loop and a small scope.

## Launcher reference

| Command | What it does |
| --- | --- |
| `skeleton.cmd studio` | Start the API if needed and open Skeleton Studio in your browser. The tokenised link is also stored in `run\studio.url` (owner-only). |
| `skeleton.cmd start` | Start the API in the background, bound to 127.0.0.1 only. The PID goes in `run\api.pid`, logs in `logs\api-*.log`. |
| `skeleton.cmd start -Foreground` | Run the API in this window. Press Ctrl+C to stop it. |
| `skeleton.cmd stop` / `status` | Stop the API, or show whether it is running (exit code 3 when stopped). |
| `skeleton.cmd doctor [-Json]` | Check Python, imports, Godot, the games folder, the seal secret and the provider. |
| `skeleton.cmd build "<idea>"` | Build a game. Starts the API if needed. |
| `skeleton.cmd play [folder] [-Check]` | Open or prove a game. |
| `skeleton.cmd smoke` | Build the sample game, then `play -Check` it. This is the CI acceptance check. |
| `skeleton.cmd logs` | Show the newest API logs. |
| `skeleton.cmd config ...` | Change the provider or model, or `-RotateSeal`. |

Every command accepts `-DataRoot <folder>` (or the `SKELETON_HOME` variable) to keep
data somewhere other than `%LOCALAPPDATA%\Skeleton`.

## Where things live

| Path | Contents |
| --- | --- |
| `<checkout>\.venv` | Python environment |
| `%LOCALAPPDATA%\Skeleton\config\config.json` | Non-secret settings: provider, model, port, Godot path, games folder |
| `%LOCALAPPDATA%\Skeleton\config\secrets.json` | DPAPI-encrypted secrets (only your account can decrypt them) |
| `%LOCALAPPDATA%\Skeleton\tools\godot-4.6-stable` | Pinned Godot engine |
| `%LOCALAPPDATA%\Skeleton\games` | Generated games |
| `%LOCALAPPDATA%\Skeleton\logs` | Bootstrap transcripts and API logs |

To uninstall, run `skeleton.cmd stop`, then delete the checkout and
`%LOCALAPPDATA%\Skeleton`. Move your `games` folder somewhere else first if you want
to keep your games. Python and Git, if the bootstrap installed them, can be removed
with `winget uninstall Python.Python.3.11` and `winget uninstall Git.Git`.

## Security model

- The API listens on loopback only. `serve` refuses a non-loopback address unless you
  pass `--allow-remote` explicitly.
- Protected routes need an HMAC request seal (`x-gf-seal`). The launcher signs each
  request with your per-user secret. Without a secret, the API fails closed.
- Secrets are passed to the Python process through its environment. They are never
  printed, written to the transcript or stored in the repository. `doctor` reports
  only whether each one is present.
- Studio is served from the same loopback port. Its `/studio/api/*` routes need the
  per-launch token (constant-time compare). Requests with a non-loopback `Host`
  (DNS rebinding) or a foreign `Origin` are refused. Pages are sent with a strict
  Content-Security-Policy (no inline script, no framing), `nosniff` and
  `no-referrer`. Studio builds go through the same sealed `POST /api/v1/game/build`.
  The seal secret never reaches the browser. `--allow-remote` cannot be combined with
  Studio.
- Godot is downloaded only from the official release URL and checked against the
  pinned SHA-512.
- Generated project files are written through a path check. Absolute paths, drive
  letters, `..` and an existing non-empty folder are refused.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `running scripts is disabled on this system` | Use `scripts\windows\bootstrap.cmd` / `skeleton.cmd`, or `powershell -ExecutionPolicy Bypass -File ...`. These apply Bypass only to that process. |
| `Python 3.11 or newer was not found` | Re-run with `-InstallMissing`, or install Python from python.org and tick **Add python.exe to PATH**. Typing `python` and getting the Microsoft Store means the Store alias is on: turn off **App execution aliases → python.exe** in Settings, or rely on the `py` launcher. |
| `winget is not available` | Install **App Installer** from the Microsoft Store (https://aka.ms/getwinget), or install Python and Git yourself and re-run without `-InstallMissing`. |
| `Godot archive SHA-512 mismatch` | The download was corrupted or intercepted (proxy or antivirus) and has been deleted. Re-run. If you are behind a TLS-inspecting proxy, download `Godot_v4.6-stable_win64.exe.zip` from https://github.com/godotengine/godot/releases/tag/4.6-stable yourself and pass `-GodotArchive <path>`. The hash is still enforced. |
| Already have Godot 4.x | `-GodotPath C:\path\Godot_v4.x-stable_win64_console.exe`. Use the `_console` build so headless proofs can read its output. |
| `pip install failed` | Check the transcript in `%LOCALAPPDATA%\Skeleton\logs\bootstrap-*.log`. Behind a proxy, set `HTTPS_PROXY` first. A path-too-long error means you should enable long paths (see the doctor warning) or clone to a shorter folder such as `C:\src\Skeleton`. |
| `skeleton_import: import failed` in the doctor | The `.venv` is incomplete. Delete `.venv` and re-run the bootstrap. |
| `The API did not start` / `is not answering on port 8710` | Run `skeleton.cmd logs`. If another program uses port 8710, re-run the bootstrap with `-Port 8711`. If Windows Defender Firewall asks about Python, you can choose **Cancel**: the API only listens on 127.0.0.1. |
| `invalid seal` / `did not become healthy` | The API and launcher disagree about the secret. Usually an old API from before `-RotateSeal` is still running. Run `skeleton.cmd stop`, then `start`. |
| `game build failed` | Run `skeleton.cmd doctor`. With `playtest=require` a working Godot 4 is mandatory. Make the brief more specific: name the genre, the core loop and a small scope. |
| `play -Check` reports `NOT PLAYABLE` | The step's `log_tail` (shown with `-Json`) contains the Godot error. Report it with the game folder attached. |
| Antivirus quarantines `Godot_*.exe` | Restore it and add an exclusion for `%LOCALAPPDATA%\Skeleton\tools`, or point `-GodotPath` at a Godot you installed yourself. |
| Studio says **Open Studio from Skeleton** | The tab has no valid token, for example after a restart or in a new tab. Run `skeleton.cmd studio`. |
| Studio shows **Disconnected** | The API stopped. Run `skeleton.cmd status`, then `skeleton.cmd studio`. |
| Studio link opens the wrong browser | Copy the link from `%LOCALAPPDATA%\Skeleton\run\studio.url` into the browser you prefer. Treat it like a password until Skeleton restarts. |
| Secrets unreadable after moving to a new PC or user | DPAPI secrets only work for the account that created them. Re-run the bootstrap, and re-enter your API key if you use a hosted provider. |

## Full studio (Docker Desktop)

For the complete studio web app (`/setup`, `/product`, Jeeves chat, crawler), install
Docker Desktop with the WSL 2 backend and follow
[README → Windows with WSL 2](../../README.md#windows-with-wsl-2). The native install
above can run alongside it. They use different ports: 8710 for native, and 3000, 8001,
8010 and 27017 for Compose.

## Continuous verification

`.github/workflows/windows-first-install.yml` runs on `windows-latest`. It can be
started manually or called from another workflow, which keeps it out of the paused
automatic queue (`scripts/check_ci_workflow_tiers.py`). It:

1. starts from an empty data root and no `.venv`
2. runs `bootstrap.ps1 -NonInteractive -Provider none -Start`
3. checks `config.json`, DPAPI-protected secrets and the owner-only ACL
4. runs `status`, `doctor -Json`, `smoke`, a second `build` and `play -Check`
5. runs `skeleton/testing/test_windows_first_install.py` and `test_local_studio.py`, plus
   the Pester suite
6. drives the Studio journey in Microsoft Edge with Playwright and axe
   (`tests/e2e/local-studio`): locked state, validation, keyboard, a full
   prompt → build → edit → playtest → export run, and a phone-sized layout
7. uploads the logs and generated games as an artifact

To run it for a branch after it lands on `main`:
`gh workflow run windows-first-install.yml -f ref=<branch-or-sha>`.
