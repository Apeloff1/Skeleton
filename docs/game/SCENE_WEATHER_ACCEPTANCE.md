# Source-bound weather gameplay acceptance

`python -m skeleton scene-weather-accept demo` runs the original authored
weather journey through the canonical reducer, every-action replay, midpoint
save/restart, portable export/import, editor preview, and actual interactive
JSON-line play. All stages must agree on the final state digest.

For authored sources, use `scene-weather-accept accept --source-json JSON
--actions-json JSON`; verify a returned receipt with
`scene-weather-accept verify --source-json JSON --receipt-json JSON`.
A winning authored action list is required. Invalid source, terminal failure,
stale editor preview, mismatched checkpoint, missing terminal event, extra
interactive input or altered receipt fail closed.

The acceptance path is bounded to 32 actions, 64 KiB of source and 512 KiB
of interactive output. The digest is an integrity witness, not an
authentication signature. No untrusted package is executed or installed.
