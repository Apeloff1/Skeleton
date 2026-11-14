"""Repository-source compatibility entry point for the packaged game-project CLI.

The executable logic resides in skeleton.ai.runtime.game_project_cli, which is
included in the installed wheel; no production package depends on scripts/.
"""
from __future__ import annotations

from skeleton.ai.runtime.game_project_cli import *  # noqa: F401,F403
from skeleton.ai.runtime.game_project_cli import (
    MAX_INPUT_BYTES, MAX_RESULT_BYTES, _pairs, _nonfinite, _read_json,
    _write_new, _demo, _parser, main,
)

if __name__ == "__main__":
    raise SystemExit(main())
