# Studio installation, practice and native prerequisites

The application uses the existing Mongo, engine, backend and frontend services.
Native SDKs and approved cores remain operator installations, separate from
application accounts and source rights. No installer downloads commercial games,
ROMs, BIOS images or proprietary console SDKs.

## Dragon practice and reviewed knowledge

A normal Compose start supplies `SKL_DRAGON_RUNTIME_BOOTSTRAP=1` and stores the
existing practice and reviewed-knowledge schemas in `backend_data` at
`/app/data/dragon_practice.sqlite` and `/app/data/dragon_knowledge.sqlite`.
Bootstrap initializes empty schemas. It does not manufacture knowledge, approve
crawler captures, award promotion, invoke a model or start an automatic training
scheduler. An empty reviewed store is a valid initialized store.

Set `SKL_DRAGON_RUNTIME_BOOTSTRAP=0` to disable initialization. Existing unsafe,
corrupt or identity-replaced stores are rejected; deleting or replacing them is
not an automatic repair. Preserve the volume and use the original owner's
recovery procedure. For a host deployment, explicitly configure both existing
`SKL_DRAGON_*_DB_PATH` values in a private writable state directory and set the
bootstrap flag before starting the backend as the same operator.

After signing in, `/api/dragon-academy/runtime/readiness` reports the actual
practice/knowledge checks and actionable failures. Raw web capture still belongs
to CORE_DB Mongo and remains unreviewed until the existing review authority
accepts it. SQLite schema availability is not reviewed knowledge availability.

## Read the actual readiness states

```bash
python -m skeleton app doctor --studio --json
python -m skeleton app doctor --studio --live --json
```

`studio.local_host` inspects only the machine running the CLI. It uses the
canonical build, desktop-export, learning and core-registry owners in a bounded,
credential-free subprocess. It does not execute a compiler, core, model or game.
The original doctor exit status describes application prerequisites/configuration
and probed services; optional per-target studio blockers remain explicit fields.

To inspect the configured backend with your existing authenticated account, save
its current bearer token in a private operator-owned regular file (`chmod 600`)
and pass only the filename:

```bash
python -m skeleton app doctor --studio --live --auth-token-file /absolute/private/token --json
```

This performs read-only calls to `/api/game-studio-health`,
`/api/dragon-academy/runtime/readiness` and
`/api/dragon-academy/crawler/readiness`. The authenticated crawler observation also
updates the top-level doctor crawler status; without the token it remains unknown. It does not create an account, elevate a
role or invoke work. HTTP authentication is limited to loopback; remote endpoints
require HTTPS, and redirects are rejected. Never place a token in a shell command,
a public environment variable, a source file or a support report.

The default Alpine backend image does not contain the glibc native toolchains or
a qualified nested native sandbox. Installing tools on your host does not make
that container ready. Use the supported Linux host deployment as the same
operator, or a separately qualified operator runtime. Do not disable the existing
sandbox or substitute unsandboxed compilation when a check fails.

## Install only selected public build tools

The existing installer supports Linux x86-64 and requires `prlimit`; compiling
cc65/RGBDS also requires the host C/C++ toolchain, Git and Make. RGBDS and SDL
header extraction require `dpkg-deb`. Missing prerequisites produce an actionable
failure; the script does not install privileged system packages.

Explicit acquisition of the pinned NES/6502 and Game Boy tools:

```bash
python scripts/install_game_desktop_toolchains.py --root /absolute/operator/tools --tool cc65 --tool rgbds --download
```

Go browser-launcher exports and SDL development headers are separate selections:

```bash
python scripts/install_game_desktop_toolchains.py --root /absolute/operator/tools --tool go --tool sdl2 --download
```

With no `--download`, only the local `--cache-root` is consulted. It accepts the
pinned archive filenames and local `cc65-source`/`rgbds-source` Git repositories
containing the exact declared commits. The compiler uses a verified Git archive
of that commit, rather than the mutable checkout or its untracked build files.

```bash
python scripts/install_game_desktop_toolchains.py --root /absolute/operator/tools --cache-root /absolute/offline/cache --tool cc65 --tool rgbds
python scripts/install_game_desktop_toolchains.py --root /absolute/operator/tools --tool cc65 --tool rgbds --inspect
```

Every SDK publishes atomically after bounded private staging, a complete file,
mode and SHA-256 inventory, copied license notices and compiler/source receipts.
An existing unreceipted or changed SDK is rejected; select a fresh destination
instead of overwriting it. Logs are private and bounded. Failed operations clean their staging without
changing completed SDKs. A host crash or forced termination can leave private
staging directories; these are never reused as completed installations. `--cc65` and `--rgbds` remain
selection aliases; selecting them no longer implicitly acquires Go or SDL.

Copy the reported configuration into the **host backend's** private environment
and restart it. `SKL_GAME_CONSOLE_SDK_ROOTS` is a JSON **list** of the exact SDK
roots. Optional `SKL_GAME_GO_ROOT` and `SKL_GAME_SDL2_SDK_ROOT` identify their
corresponding installations. The canonical build owner rechecks tooling before
each build. SDL headers alone do not supply the host SDL runtime library.

## Install and approve only requested emulator cores

The existing core installer already requires explicit source acquisition. Inspect
its pinned recipes and target/firmware limits first:

```bash
python scripts/install_game_emulator_cores.py --list-cores
python scripts/install_game_emulator_cores.py --coverage-matrix
```

A bounded original Game Boy/NES installation uses the actual existing cores:

```bash
python scripts/install_game_emulator_cores.py --source-root /absolute/operator/core-sources --install-root /absolute/operator/cores --core gambatte --core fceumm --fetch-sources --jobs 1 --timeout 600
python scripts/install_game_emulator_cores.py --installed-audit --install-root /absolute/operator/cores
```

Omit `--fetch-sources` for a complete matching local source cache. Configure the
reported `SKL_GAME_EMULATOR_REGISTRY` in the host backend's private environment.
Only current approved library/firmware identities can reach the existing isolated
worker. Missing firmware and deferred candidate recipes remain unavailable.
Installed approvals do not prove hardware accuracy or commercial-title support.

Source export, installed prerequisites, successful compilation, actual native
play, game-policy learning and measured model improvement are distinct stages.
Upload only material you are authorized to use and retain its current source
consent. The installer does not grant application source rights or training
approval and does not turn a design simulation into hardware emulation.
