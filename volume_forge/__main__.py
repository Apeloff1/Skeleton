"""python -m volume_forge. Close is the exit."""

from pathlib import Path
import json

from volume_forge.close import close

if __name__ == "__main__":
    body = close(Path("."))
    print(json.dumps({"files_ok": body["files_ok"], "stored_prose": 0}))
    if not body["files_ok"]:
        raise SystemExit(2)
