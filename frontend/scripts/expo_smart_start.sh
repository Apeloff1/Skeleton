#!/usr/bin/env bash
# =============================================================================
# expo_smart_start.sh — self-healing wrapper around `expo start --tunnel`.
#
# Why: in the preview environment ngrok flaps for many reasons (cold pool,
# DNS hiccups, the upstream "TypeError: Cannot read properties of undefined
# (reading 'body')" bug). supervisor's default autorestart=true bashes
# ngrok with back-to-back retries — the second retry usually fails because
# the previous tunnel hasn't released its lease yet.
#
# This wrapper interposes a *smart* restart policy:
#
#   • Exponential cool-off between restarts (1, 2, 4, 8, 16, 30, 30, …).
#   • Resets the cool-off back to 1 s after a stable run (>180 s alive).
#   • Detects ngrok-specific failure strings and applies a longer
#     cool-off (NGROK_COOLOFF_S, default 20s) so the upstream API can
#     fully release the previous tunnel.
#   • Hard exit after MAX_FLAPS in FLAP_WINDOW_S so supervisor backs off
#     and `health/tunnel` reports the situation up the stack.
#   • Writes structured restart-event lines (TAB-separated) to FLAP_LOG
#     so /api/health/tunnel can ingest them later.
# =============================================================================
set -u

cd /app/frontend

# Load .env so our mode-detection sees EXPO_PACKAGER_HOSTNAME etc.
if [ -f /app/frontend/.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /app/frontend/.env
  set +a
fi

FLAP_LOG="${EXPO_FLAP_LOG:-/var/log/supervisor/expo_flaps.log}"
NGROK_COOLOFF_S="${EXPO_NGROK_COOLOFF_S:-60}"
STABLE_RUN_S="${EXPO_STABLE_RUN_S:-180}"
MAX_FLAPS="${EXPO_MAX_FLAPS:-30}"
FLAP_WINDOW_S="${EXPO_FLAP_WINDOW_S:-900}"

# ── Metro/Node heap ─────────────────────────────────────────────────────────
# This app's module graph is very large (1700+ modules), so Metro's web bundle
# + static-render passes blow past the inherited 4GB V8 heap and the process
# V8-aborts ("JavaScript heap out of memory", exit 134) — which drops the dev
# server and makes Expo Go / the preview look like an on-device crash.
# Raise the old-space limit to 6GB: comfortably under the 8GB container cgroup
# while leaving headroom for the transform workers. (Overrides the value
# inherited from supervisor's environment.)
export NODE_OPTIONS="--max-old-space-size=6144"

# Kill any lingering ngrok agents so the reserved subdomain lease is released
# between retries. Without this, the second attempt always fails because the
# previous tunnel hasn't released.
cleanup_ngrok() {
  pkill -f '@expo/ngrok' 2>/dev/null || true
  pkill -f 'ngrok start' 2>/dev/null || true
  pkill -f 'bin/ngrok'   2>/dev/null || true
  # Metro/Expo can also be lingering after a tunnel timeout
  pkill -f 'expo start' 2>/dev/null || true
  pkill -f 'metro'      2>/dev/null || true
  sleep 1
}

# Sliding window of recent restart timestamps.
declare -a FLAPS=()

# Exponential backoff state (resets on stable run).
backoff=1

# Detect tunnel-class errors in the last log to decide which cool-off to apply.
detect_tunnel_error() {
  local tail="$1"
  case "$tail" in
    *"ngrok"*|*"tunnel"*|*"reading 'body'"*|*"PluginError"*|*"ngrok-related"*|*"took too long"*|*"Ngrok"*)
      return 0 ;;
  esac
  return 1
}

# Record a flap, evict stale entries, return current count.
record_flap() {
  local now=$(date +%s)
  FLAPS+=("$now")
  # Evict entries older than FLAP_WINDOW_S.
  local cutoff=$((now - FLAP_WINDOW_S))
  local new=()
  for t in "${FLAPS[@]}"; do
    if [ "$t" -ge "$cutoff" ]; then new+=("$t"); fi
  done
  FLAPS=("${new[@]}")
  echo "${#FLAPS[@]}"
}

log_event() {
  local ts=$(date +%s)
  local kind="$1"
  local detail="${2:-}"
  printf '%s\t%s\t%s\n' "$ts" "$kind" "$detail" >> "$FLAP_LOG" 2>/dev/null || true
  printf '[expo_smart] %s — %s %s\n' "$(date '+%H:%M:%S')" "$kind" "$detail" >&2
}

log_event start "wrapper-up backoff=${backoff}s max_flaps=${MAX_FLAPS}/${FLAP_WINDOW_S}s"

# Trap so a SIGTERM from supervisor propagates cleanly.
child_pid=0
on_sig() {
  log_event sig "received signal, forwarding to child PID=$child_pid"
  if [ "$child_pid" -gt 0 ]; then
    kill -TERM "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
  fi
  exit 0
}
trap on_sig TERM INT

# Probe ngrok cloud egress. In the Emergent preview environment the pod
# usually has its OWN public ingress (via EXPO_PACKAGER_HOSTNAME), so the
# ngrok tunnel is redundant — and in fact ngrok's API endpoints are often
# unreachable from inside the pod, which causes endless flapping. When egress
# is missing we fall back to plain LAN mode.
detect_tunnel_mode() {
  # Manual override:
  #   EXPO_TUNNEL_MODE=tunnel  → force ngrok
  #   EXPO_TUNNEL_MODE=lan     → force LAN (no ngrok)
  if [ "${EXPO_TUNNEL_MODE:-auto}" = "tunnel" ]; then
    echo "tunnel"; return
  fi
  if [ "${EXPO_TUNNEL_MODE:-auto}" = "lan" ]; then
    echo "lan"; return
  fi
  # Auto-detect: when the preview environment provides its own public
  # ingress via EXPO_PACKAGER_HOSTNAME (Emergent preview), there is no need
  # for ngrok and its outbound session servers are usually unreachable from
  # inside the pod anyway. Prefer LAN mode in that case.
  if [ -n "${EXPO_PACKAGER_HOSTNAME:-}" ] || [ -n "${EXPO_PACKAGER_PROXY_URL:-}" ]; then
    echo "lan"; return
  fi
  echo "tunnel"
}

TUNNEL_MODE="$(detect_tunnel_mode)"
log_event mode "selected=${TUNNEL_MODE} (override=${EXPO_TUNNEL_MODE:-auto})"

# ── Memory watchdog ──────────────────────────────────────────────────────────
# Metro can slowly accumulate heap over a long session and hit V8's ceiling,
# aborting hard (exit 134, "JavaScript heap out of memory"). This background
# watchdog samples the Metro main-process RSS every 60s and writes it to the
# flap log — emitting a WARN once it crosses 80% of the heap cap — so we get an
# early signal instead of a silent crash. Read it via: grep $'\tmem' FLAP_LOG.
HEAP_CAP_MB="${EXPO_HEAP_CAP_MB:-6144}"
mem_watchdog() {
  local warn_mb=$(( HEAP_CAP_MB * 80 / 100 ))
  while true; do
    sleep 60
    # Among all matches (a `sh -c` shim + the real node proc), pick the node
    # process with the largest RSS — the shim is only ~1MB and skews readings.
    local best_pid=0 best_rss=0 p rss comm
    for p in $(pgrep -f 'node_modules/.bin/expo start' 2>/dev/null); do
      comm=$(ps -o comm= -p "$p" 2>/dev/null)
      [ "$comm" = "node" ] || continue
      rss=$(ps -o rss= -p "$p" 2>/dev/null | tr -d ' ')
      [ -z "$rss" ] && continue
      if [ "$rss" -gt "$best_rss" ]; then best_rss=$rss; best_pid=$p; fi
    done
    [ "$best_pid" -eq 0 ] && continue
    local rss_mb=$(( best_rss / 1024 ))
    if [ "$rss_mb" -ge "$warn_mb" ]; then
      log_event mem_warn "metro_rss_mb=${rss_mb} cap=${HEAP_CAP_MB} (>=80% — abort risk)"
    else
      log_event mem "metro_rss_mb=${rss_mb} cap=${HEAP_CAP_MB}"
    fi
  done
}
mem_watchdog &

while true; do
  cleanup_ngrok
  start_ts=$(date +%s)
  # Capture both stdout AND stderr from yarn so we can categorise the failure
  # after the child exits. Earlier versions only captured stderr, but
  # `CommandError: ngrok tunnel took too long to connect` is written to stdout.
  tmp_err=$(mktemp /tmp/expo_smart.XXXXXX.err)

  # Stream both stdout+stderr through tee → tmp_err while also forwarding to
  # supervisor's stderr (so the log files keep working).
  if [ "$TUNNEL_MODE" = "tunnel" ]; then
    yarn expo start --tunnel --port 3000 > >(tee "$tmp_err" >&2) 2>&1 &
  else
    yarn expo start --port 3000 > >(tee "$tmp_err" >&2) 2>&1 &
  fi
  child_pid=$!
  wait "$child_pid"
  exit_code=$?
  child_pid=0

  end_ts=$(date +%s)
  run_dur=$((end_ts - start_ts))

  # Tail the last 50 lines for keyword detection.
  err_tail="$(tail -n 50 "$tmp_err" 2>/dev/null || true)"
  rm -f "$tmp_err"

  if [ "$run_dur" -ge "$STABLE_RUN_S" ]; then
    log_event stable "ran ${run_dur}s; resetting backoff"
    backoff=1
  fi

  count=$(record_flap)
  log_event exit "code=${exit_code} dur=${run_dur}s flaps=${count}/${MAX_FLAPS}"

  if [ "$count" -ge "$MAX_FLAPS" ]; then
    log_event giveup "too many flaps (${count}) in ${FLAP_WINDOW_S}s — exiting wrapper"
    sleep 5
    exit 1
  fi

  # Decide the cool-off.
  if detect_tunnel_error "$err_tail"; then
    sleep_s="$NGROK_COOLOFF_S"
    log_event ngrok_cooloff "detected tunnel-class error; waiting ${sleep_s}s"
  else
    sleep_s="$backoff"
    log_event backoff "generic exit; waiting ${sleep_s}s"
    if [ "$backoff" -le 30 ]; then backoff=$((backoff * 2)); fi
    if [ "$backoff" -gt 30 ]; then backoff=30; fi
  fi

  sleep "$sleep_s"
done
