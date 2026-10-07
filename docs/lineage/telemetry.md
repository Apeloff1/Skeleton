# Telemetry SSE (GB-30)

Parent #80. Optional stream. Default off.

## Public card

- Path constant `GET /api/v1/events/stream`.
- Not mounted on operator `api/server.py`.
- Event frames are kind + seq. No payload prose.
- Mobile skips.
- Test client reads 2 events when enabled.

## Accept

`python -m unittest tests.test_gb30_telemetry -v`

`python scripts/check_telemetry.py` exits 0.
