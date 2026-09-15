#!/bin/sh
# Pod-local webhook-cron dispatcher: one crontab line per enabled cron, run by
# crond inside the preview/env pod. The full endpoint URL is substituted at
# render time; this fires a single request with the .env secret and exits 0.
set -eu

: "${CRON_NAME:?}" "${METHOD:?}" "${ENDPOINT_URL_B64:?}"
JOB_ID="${JOB_ID:-}"
WEBHOOK_ENV_FILE="${WEBHOOK_ENV_FILE:-/app/backend/.env}"
AT_DATE="${AT_DATE:-}"
END_DATE="${END_DATE:-}"

# AT_DATE (one-time trigger): crond can't express the year, so the "M H D Mo *"
# line re-fires this minute every year. Fire only when the current UTC minute
# (first 16 chars of RFC3339) matches AT_DATE's minute.
if [ -n "$AT_DATE" ]; then
	now_min="$(date -u +%Y-%m-%dT%H:%M)"
	at_min="$(printf '%s' "$AT_DATE" | cut -c1-16)"
	[ "$now_min" = "$at_min" ] || exit 0
fi

# END_DATE (recurring cutoff): both sides use the same fixed %Y-%m-%dT%H:%M:%SZ
# layout, so comparing their digit-only forms numerically preserves chronological
# order. Stop firing once now is strictly past END_DATE.
if [ -n "$END_DATE" ]; then
	now_num="$(date -u +%Y%m%d%H%M%S)"
	end_num="$(printf '%s' "$END_DATE" | tr -cd '0-9')"
	[ "$now_num" -le "$end_num" ] || exit 0
fi

ENDPOINT="$(printf '%s' "$ENDPOINT_URL_B64" | base64 -d)"

strip_quotes() {
	# Strip a single matching pair of surrounding quotes.
	v="$1"
	case "$v" in
		\"*\") v="${v#\"}"; v="${v%\"}" ;;
		\'*\') v="${v#\'}"; v="${v%\'}" ;;
	esac
	printf '%s' "$v"
}

# Return the authority for a simple absolute HTTPS URL. Cron endpoints are
# generated preview hostnames, so reject userinfo, IPv6 literals, malformed
# ports, and non-HTTPS schemes rather than trying to be permissive around a
# credential-bearing request.
https_authority() {
	url="$1"
	case "$url" in
		https://*) rest="${url#https://}" ;;
		*) return 1 ;;
	esac
	authority="${rest%%/*}"
	authority="${authority%%\?*}"
	authority="${authority%%\#*}"
	[ -n "$authority" ] || return 1
	case "$authority" in
		*@*|\[*\]) return 1 ;;
	esac
	host="${authority%%:*}"
	[ -n "$host" ] || return 1
	port_suffix="${authority#"$host"}"
	case "$port_suffix" in
		"") ;;
		:*)
			port="${port_suffix#:}"
			[ -n "$port" ] || return 1
			case "$port" in *[!0-9]*) return 1 ;; esac
			;;
		*) return 1 ;;
	esac
	printf '%s' "$authority"
}

ORIGIN_AUTHORITY="$(https_authority "$ENDPOINT")" || {
	echo "dispatch blocked (cron=$CRON_NAME reason=invalid_endpoint)"
	exit 0
}
ORIGIN_HOST="${ORIGIN_AUTHORITY%%:*}"
ORIGIN_PORT_SUFFIX="${ORIGIN_AUTHORITY#"$ORIGIN_HOST"}"
INTERNAL_AUTHORITY="internal.${ORIGIN_HOST}${ORIGIN_PORT_SUFFIX}"

redirect_allowed() {
	candidate_authority="$(https_authority "$1")" || return 1
	[ "$candidate_authority" = "$ORIGIN_AUTHORITY" ] || \
		[ "$candidate_authority" = "$INTERNAL_AUTHORITY" ]
}

# Read the per-app secret from the dotenv at dispatch time (never from cron env).
read_secret() {
	[ -f "$WEBHOOK_ENV_FILE" ] || return 0
	line="$(grep -E '^WEBHOOK_CRON_SECRET=' "$WEBHOOK_ENV_FILE" | tail -n 1 || true)"
	value="$(strip_quotes "${line#WEBHOOK_CRON_SECRET=}")"
	printf '%s' "$value"
}
WEBHOOK_CRON_SECRET="$(read_secret)"

# RUN_ID is the idempotency key: cron name + fire time (minute granularity
# matches the schedule floor).
RUN_ID="${CRON_NAME}-$(date -u +%Y%m%dT%H%M)"
DISPATCH_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
ENVELOPE="{\"event\":\"schedule.triggered\",\"schedule_id\":\"$CRON_NAME\",\"run_id\":\"$RUN_ID\",\"dispatch_time\":\"$DISPATCH_TIME\",\"job_id\":\"$JOB_ID\",\"data\":null}"

# Fire-and-forget with a bounded, explicit redirect policy. curl's
# --location-trusted forwards Authorization across arbitrary hosts; do not use it
# for this credential-bearing request. The platform's expected cross-host 307 is
# allowed only from <preview-host> to internal.<preview-host>. Every hop remains
# HTTPS and is revalidated before the Bearer token is sent again.
CURRENT_ENDPOINT="$ENDPOINT"
HTTP_STATUS="000"
REDIRECT_COUNT=0
while :; do
	CURL_RESULT="$(curl -sS -o /dev/null -w '%{http_code}\n%{redirect_url}' \
		--max-time 10 \
		--proto '=https' \
		-X "$METHOD" \
		-H "Authorization: Bearer $WEBHOOK_CRON_SECRET" \
		-H "Content-Type: application/json" \
		-H "X-Webhook-Id: $RUN_ID" \
		-H "X-Webhook-Timestamp: $DISPATCH_TIME" \
		-d "$ENVELOPE" \
		"$CURRENT_ENDPOINT" 2>/dev/null || true)"
	HTTP_STATUS="$(printf '%s\n' "$CURL_RESULT" | sed -n '1p')"
	REDIRECT_URL="$(printf '%s\n' "$CURL_RESULT" | sed -n '2p')"

	case "$HTTP_STATUS" in
		307|308)
			if [ -n "$REDIRECT_URL" ] && [ "$REDIRECT_COUNT" -lt 2 ] && redirect_allowed "$REDIRECT_URL"; then
				REDIRECT_COUNT=$((REDIRECT_COUNT + 1))
				CURRENT_ENDPOINT="$REDIRECT_URL"
				continue
			fi
			# Fail closed on an unexpected or excessive redirect rather than
			# forwarding the Bearer token to a new authority.
			HTTP_STATUS="000"
			;;
	esac
	break
done

echo "dispatch complete (cron=$CRON_NAME http=${HTTP_STATUS:-000})"
exit 0
