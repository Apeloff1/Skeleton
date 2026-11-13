"""Backend scanners with explicit access to canonical repository scripts.

Backend CI executes from `backend/`, whereas aggregate gates execute from the
repository root. Keep the local backend scanners authoritative in either
environment while exposing root-only contract validators when running from
the backend working directory.
"""

from pathlib import Path

_root_scripts = Path(__file__).resolve().parents[2] / "scripts"
if _root_scripts.is_dir():
    __path__.append(str(_root_scripts))
