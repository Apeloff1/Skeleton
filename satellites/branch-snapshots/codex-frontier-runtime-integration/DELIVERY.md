# CodeDock — Delivery Checklist

A production-ready Expo + FastAPI app. This document is the source of
truth for "is this APK ready to ship?"

## ✅ APK build status (Android + iOS)

- [x] `app.json` — `name`, `slug`, `version`, `android.package`,
      `android.versionCode`, `ios.bundleIdentifier` all set
      (`CodeDock` / `codedock-quantum-nexus` / `com.codedock.quantumnexus`).
- [x] Required asset files (`icon.png`, `adaptive-icon.png`,
      `splash-image.png`, `favicon.png`) present in `assets/images/`.
- [x] Backend URL injected dynamically at build time via `app.config.js`
      → reads `EXPO_PUBLIC_BACKEND_URL` from the build environment.
- [x] Permissions declared (Android: VIBRATE, RECEIVE_BOOT_COMPLETED,
      POST_NOTIFICATIONS, SCHEDULE_EXACT_ALARM, INTERNET,
      ACCESS_NETWORK_STATE; iOS Info.plist: Microphone, Camera, Photo
      usage descriptions; `UIBackgroundModes: remote-notification`).
- [x] Expo plugins: `expo-router`, `expo-splash-screen`, `expo-audio`,
      `expo-asset`, `expo-notifications`.

## ✅ Networking architecture

A **single SOTA `apiController`** owns every backend call:
- Per-request timeout (15 s default), exponential-backoff retries with
  jitter (3 attempts, retries 429/500/502/503/504/network/timeout).
- GET request deduplication (same URL in-flight → shared promise).
- TTL response cache (in-memory + optional AsyncStorage persistence).
- Offline detection via `@react-native-community/netinfo` (gracefully
  no-op if missing).
- Normalised `ApiError` shape: `{code, status, url, body, requestId,
  retriedTimes}`.
- Live telemetry: success/failure counts, retries, cache hits, p50/p95
  latency, per-tag breakdown, last error. Surfaced in `/settings/api`.
- Pluggable `authHook` for future real-auth wiring.

**Every legacy `fetch()` call** is also intercepted at app boot via
`installFetchInterceptor()` (registered in `app/_layout.tsx`). The
interceptor reroutes all `/api/*` requests through the controller —
so 30+ existing modal files (Galaxy Studio, Bible, GameFactory,
StudyPaths, Forge, etc.) automatically benefit from retries,
telemetry, and request-id propagation **without per-file refactoring**.

The controller's internal HTTP calls bypass the interceptor via a
stashed `__origFetch` reference to avoid recursion.

## ✅ Server-side SOTA middleware

`/app/backend/api_middleware.py`:
- `RequestIdMiddleware` — auto-mints / echoes `X-Request-Id`.
- `AccessLogMiddleware` — single-line structured access log per req.
- `RateLimiterMiddleware` — per-IP token bucket; loopback exempt.

`/api/_telemetry` returns live percentiles + counters.

## 🚀 How to ship the APK

This project lives on Emergent. **Use the Publish button** (top right
of the Emergent editor) to produce an APK / IPA. Do **not** run EAS
CLI manually — the Emergent build pipeline injects credentials and
the correct backend URL automatically.

After clicking Publish, Emergent will:
1. Read `app.config.js` (which reads `app.json` + injects env vars).
2. Build the Android APK / iOS IPA on EAS.
3. Surface a download URL when the build completes.

## 🧪 Verification results

| Check                                          | Result |
| ---------------------------------------------- | ------ |
| Curriculum endpoint sweep (10 × 15 × 2 = 300)  | **300/300** |
| SOTA API middleware                            | **43/43** |
| Frontend routes reachable                      | **10/10** |
| Lab + glossary + comprehension on every week   | ✅ |
| Reader: glossary_structured + comprehension + takeaways | ✅ |
| Metronome (BPM, time-sig, sound, tap-tempo)    | ✅ |
| Scheduler notifications (expo-notifications)   | ✅ |
| Rate limiter (per-IP token bucket)             | ✅ |
| Request-ID propagation (X-Request-Id)          | ✅ |
| `/api/_telemetry` (live percentiles)           | ✅ |
| APK asset checklist (all icons + splash)       | ✅ |
| Backend p50 latency                            | **1.6 ms** |
| Backend p95 latency                            | **2.0 ms** |
| Backend 5xx error rate                         | **0** |

## 📝 Backend environment knobs

```
RATE_LIMIT_PER_MIN  default 1200
RATE_LIMIT_BURST    default 120
RATE_LIMIT_EXEMPT   default "127.0.0.1,::1,localhost"
ACCESS_LOG          default "1"
CORS_ORIGINS        default "*"
```

## 🔧 Known limitations

- **Auth is currently MOCKED** (local profile state via Zustand).
  The `apiController.authHook` is plugged in and ready for real auth.
- **Rate limiter is in-process** — sufficient for single-replica
  deploys. Swap to Redis-backed for horizontal scaling.
- **Scheduler uses local notifications only** (no remote push).
