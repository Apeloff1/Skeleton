# Archived dependency manifests

This directory is historical branch evidence, not a supported install/build surface.

The following dependency manifests were removed from their conventional active filenames during security hardening. Their exact historical bytes remain recoverable from Git by blob SHA and from repository history:

- `requirements.txt` — `fc7b3939d1f54f1ce5ae1e0cf734bab708c8ee2b`
- `requirements-dev.txt` — `774fe94377a6d7c56f353407faa02452df4f2a99`
- `requirements-frontier.txt` — `432c0110e92baac76f6ea03d70936c5defbd7d43`
- `pyproject.toml` — `0a2f1324a72aa2cd0e613e32795000f21f215c31`
- `frontend/package.json` — `a1d95bbad5d9cc78754eb552ed98cd894700fa63`
- `frontend/yarn.lock` — `88b129eedf9e73c825dabf35975feac52d37c8c6`

The historical backend dependency list is retained in-tree as `backend/requirements.snapshot` because it is small and useful for provenance. Promote code out of this snapshot and create a fresh maintained manifest before executing or shipping it.
