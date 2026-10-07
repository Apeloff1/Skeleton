# Backend Production Environment — SOTA Hardening Notes (Feb 2026)

Drop the following keys into the deployment environment (e.g. Emergent
publish > Environment variables, or `.env.production`) to switch on the
production-grade hardening that ships disabled in dev.

## Structured JSON logging
```
LOG_FORMAT=json
```

When set, `core/structured_log.install_json_adapter()` attaches a JSON
sink to loguru. Every emitted line becomes a single-line JSON blob with
header redaction (Authorization, X-Admin-Token, Cookie, X-API-Key are
all replaced with `"***"`) and payload truncation at 8 kB.

Log shippers that work out of the box:
* **Loki**: configure `parsers: [json]` on the scrape target.
* **Datadog**: enable `source: python` + auto-detect JSON.
* **Google Cloud Logging**: `severity` is mapped from the `level` field.

Per-route sampling (helps reduce log volume on high-RPS routes):
```
LOG_SAMPLE_PATHS=/api/feature-flags=1/10,/api/health/tunnel=1/20
```
The format is comma-separated `<path>=1/N`. The route is sampled at 1/N.

## Feature-flag admin lockdown
```
FEATURE_FLAGS_ADMIN_TOKEN=<long-random-string>
FEATURE_FLAGS_ADMIN_RPM=20      # per-IP rate limit for POST/DELETE (default 10)
FEATURE_FLAGS_CACHE_TTL_S=120   # default 60
```

Once `FEATURE_FLAGS_ADMIN_TOKEN` is set, every POST/DELETE on
`/api/feature-flags` requires the `X-Admin-Token` header to match. Plain
GETs remain open. Frontend admin UI stores the token in AsyncStorage
when the QA user types it on `/feature-flags` and auto-injects it on
every mutation via `adminHeaders()`.

## Expo smart-launcher (ngrok flap mitigation)

The expo program is launched via `scripts/expo_smart_start.sh` which
exponentially backs off after every crash and applies a longer cool-off
when an ngrok-class error is detected. Tunables:

```
EXPO_NGROK_COOLOFF_S=20    # cool-off after a tunnel-class error
EXPO_STABLE_RUN_S=180      # alive longer than this → reset backoff
EXPO_MAX_FLAPS=15          # exit wrapper after this many in WINDOW
EXPO_FLAP_WINDOW_S=600     # sliding window for MAX_FLAPS
EXPO_FLAP_LOG=/var/log/supervisor/expo_flaps.log
```

The wrapper writes a TAB-separated event stream to `EXPO_FLAP_LOG`; the
backend exposes the rolling window via `/api/health/expo-flaps`.

## Production deploy verification
Once deployed, smoke-test:

```
curl https://<prod>/api/health
curl https://<prod>/api/health/runtime
curl https://<prod>/api/health/boot/score
curl https://<prod>/api/health/tunnel
curl https://<prod>/api/health/expo-flaps?limit=5
```

A healthy production stack returns `boot_score: 100.0` and
`critical_ok: true` within ~30 s of pod ready.
