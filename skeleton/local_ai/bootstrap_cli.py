"""Legacy local AI diagnostics; never advertise a constructed seam as ready."""
import argparse
import json
from . import get_complete


def main() -> int:
    parser = argparse.ArgumentParser(description="Local AI readiness diagnostics")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    status = get_complete().status()
    print(json.dumps(status, sort_keys=True))
    # This legacy facade cannot prove a real licensed model/guard binding.
    return 0 if status.get("ready") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
