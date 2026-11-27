# Install and run the verticals draft

This source delivery follows draft [PR #6004](https://github.com/Apeloff1/Skeleton/pull/6004).
The accompanying delivery receipt pins the exact source commit and archive
SHA-256. The archive contains tracked source, not dependencies, model weights,
operator credentials or a preconfigured production installation.

Use Python 3.11+ on Linux for the commands below. Install dependencies with
internet access; run inference locally with your own compatible model and
llama.cpp executable. Godot is additionally required to build and verify native
games. The current qualification does not establish Windows or macOS readiness.

## Obtain the exact draft

Verify the delivered archive before extracting it into a new directory:

```sh
sha256sum -c skeleton-source-20261127.tar.gz.sha256
tar -xzf skeleton-source-20261127.tar.gz
cd Skeleton-verticals-20261127
```

Alternatively, clone the current draft branch:

```sh
git clone --branch integration/verticals-functional-20261127 \
  https://github.com/Apeloff1/Skeleton.git Skeleton-verticals
cd Skeleton-verticals
```

From the extracted or cloned source root:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[local-inference]'
python -m skeleton app check --json
```

The branch may advance; use the delivery receipt's full commit when reproducing
that particular artifact. Keep the full source tree: a Python wheel alone does
not contain the assembled frontend, backend and deployment contracts.

## Start the local Jeeves game workspace

Prepare an existing trained GGUF with an existing compatible llama.cpp CLI. A
deployment manifest pins the actual files; it does not download or qualify a
model. Choose the runtime profile that matches your model and executable. This
example uses the completion-chat profile; Qwen3 uses its explicit
`qwen3-completion-chat` profile. `--model-id jeeves` is required by the existing
game builder, and does not change or certify the model's weights.

```sh
mkdir -m 700 runtime-private
python -m skeleton app prepare-local-model \
  --executable /absolute/path/to/llama-cli \
  --model /absolute/path/to/model.gguf \
  --model-id jeeves --context-size 4096 --gpu-layers 0 \
  --runtime-profile llama-completion-chat \
  --output "$PWD/runtime-private/jeeves.json"

SKELETON_GODOT_BIN=/absolute/path/to/godot4 \
python -m skeleton.app.offline_http \
  --gguf-deployment "$PWD/runtime-private/jeeves.json" \
  --database "$PWD/runtime-private/jeeves.sqlite3" \
  --token-file "$PWD/runtime-private/launch-1.secret" \
  --port 8766 --open-browser
```

The server binds to loopback and prints its address and private token-file path.
Paste the token locally into the connection panel. Manifest and token files are
create-only: choose a new token filename on each launch, retaining the same
database for history. Do not overwrite a live credential to force startup.

Open **Game builder**, review a brief and explicitly request a build. Review the
result and quality details before downloading the ZIP. Extract it, read
`PLAY.md`, and open `project.godot` in Godot. Model unavailability, insufficient
structured-output support, native-engine failure or a quality rejection must
remain visible; the workspace does not substitute a successful generated game.

No pretrained GGUF or llama.cpp executable was available in the delivery
environment. Browser/state and strict Godot checks are recorded separately from
trained-model generation. Supplying an arbitrary model does not establish its
quality, compatibility or readiness.

## Assembled Jeeves, Dragon and Skeleton application

The existing installer owns the four-service Compose deployment. Install Docker
with Compose v2 and allow at least 6 GiB free, preferably 12 GiB, for image builds.
Host Node is unnecessary for that path. Use the setup and owner-bootstrap steps
in the [main installation instructions](../../README.md#first-install):

```sh
python scripts/install_app.py --production --start
python -m skeleton app doctor --live --studio --json
```

This draft's default Compose local-AI configuration requires trusted guard
components not supplied by ordinary Compose startup. Provisioned model files
alone do not make that provider ready. The optional full-profile Chroma startup
also remains blocked. Preserve these readiness failures; do not disable guards,
invent credentials or use `--full` to claim a complete production installation.

Dragon's saved projects and immutable revision comparison, Jeeves authoring and
the game workspace have separate recorded qualification. A live backend probe
does not establish that every service, model or optional vertical is available.
Use the live doctor report to inspect the installed configuration.

## Rebuild the browser package

For an operator building outside Docker, install Node 24+ and the repository's
pinned Yarn, then use the frozen lockfile, reviewed patches and guarded exporter
from [frontend/Dockerfile](../../frontend/Dockerfile). The exporter requires a
new `frontend/dist`; preserve an existing export before rebuilding. Production
uses the existing nginx ingress and same-origin API routes. Serving exported
HTML alone provides a static preview, not the database or AI services.

Keep model files, private runtime data and credentials outside the delivered
source/archive. Before upgrading, back up the SQLite database consistently
together with its referenced immutable game archives; see the existing
[workspace operations](../plan/JEEVES_NATIVE_BUILDER_WORKSPACE_2026_11_13.md#l11--backup-restore-and-deployment).
