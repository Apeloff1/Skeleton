"""Repository validation and operator scripts exposed as an importable package.

The backend retains historical ``backend/scripts`` scanner modules.  Mixed
repository/backend validation suites import both script families in one Python
process, so expose that legacy directory as a secondary package search path.
Repository-root modules remain authoritative because this package directory is
searched first.
"""

from pathlib import Path

_backend_scripts = Path(__file__).resolve().parents[1] / "backend" / "scripts"
if _backend_scripts.is_dir():
    __path__.append(str(_backend_scripts))
