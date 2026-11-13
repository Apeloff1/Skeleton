# Read-only original-game installer preflight

Use `python -m skeleton app studio-journey --preflight-install` with
`--archive`, `--expected-archive-sha256`,
`--expected-manifest-sha256`, `--output`, and
`--trusted-local-operator`.

This verifies an independently pinned canonical source archive, an
owner-controlled installation parent, and that the destination name is
unoccupied. It does not reserve a directory, install source, execute
gameplay, certify a device, sign packages, or authorize consumer release.
A successful preflight is advisory only: the separate `--install-archive`
operation repeats verification and reserves atomically with no-clobber
`mkdir`. A concurrent writer can occupy the destination between calls;
the installer must reject rather than overwrite.

Focused acceptance:
`python -m pytest -q skeleton/testing/test_app_offline_install_preflight.py`
