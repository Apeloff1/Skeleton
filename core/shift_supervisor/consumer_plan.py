"""Compatibility shim; canonical implementation lives in skeleton.automation.shift_supervisor.consumer_plan."""
from skeleton.automation.shift_supervisor.consumer_plan import *  # noqa: F401,F403
from skeleton.automation.shift_supervisor.consumer_plan import main as _canonical_main


if __name__ == "__main__":
    raise SystemExit(_canonical_main())
