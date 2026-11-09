# Configure local AI chat

From the repository root, generate a new private Compose environment. The command writes configuration and startup instructions; it does not install dependencies, launch services, call a provider, load model weights or run tests.

For hosted chat, supply a real key through an existing environment variable:

```sh
python scripts/configure_ai_chat.py --env-file .env.chat --provider openai --openai-key-env OPENAI_API_KEY
```

The key stays out of command arguments and terminal output. `--model` optionally selects a hosted model; otherwise the canonical engine chooses its configured default. Omitting the key option allows configuration without a key, and the summary clearly reports hosted credentials as absent.

For a governed model artifact that already exists on this Docker host:

```sh
python scripts/configure_ai_chat.py --env-file .env.chat --provider local --local-artifact ./artifacts/local-model.json
```

Use your actual export path. The generator binds that artifact read-only at `/app/data/local-model.json`; it creates no placeholder model. The engine validates model format and identity when it starts. Its container user is UID 10001, so the generated instructions include a private read-access step for a mode-0600 Linux artifact.

Each configuration creates three mode-0600 files:

- `.env.chat`: fresh engine, MongoDB and signing secrets, plus the selected provider configuration.
- `.env.chat.compose.json`: forwards the actual authenticated backend settings and mounts a local artifact when selected.
- `.env.chat.README.md`: complete commands using the repository’s actual Compose services and paths.

Read the generated instructions before starting the stack. The default web address is `http://localhost:3000`; the backend is `http://localhost:8001`, and the engine host port is 8010. Use `--public-host` with a reachable hostname/IP for another computer or phone. Host ports are configurable and must differ.

Authentication is enforced with a persistent generated `GAMEFORGE_JWT_SECRET`. Register or sign in through the application. The default engine grant allows tenant `default` and the existing `assistant.chat`/`assistant.compat` capabilities; repeat `--tenant` for other explicit tenant IDs. The authenticated `/api/ai/models` catalog reports current runtime readiness after startup.

`--dry-run` reports presence only and writes nothing. An existing output is refused unless `--force` is explicitly supplied. Replacement generates fresh credentials but does not rotate users in existing MongoDB volumes or delete data. Keep a private copy of the old environment before replacing a configuration used by a persistent stack; use a fresh stack or handle database credential rotation separately.

Keep generated files private and out of version control. Configuration presence does not establish provider access, artifact readability, service readiness, model quality or production promotion. A local reference/neural model is a development baseline.
