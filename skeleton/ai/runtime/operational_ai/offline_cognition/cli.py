"""Complete offline cognition source corpus qualification, not device certification."""
from __future__ import annotations
import json
import sys
from .catalog import FAMILIES
from .core.casebook import run_all
def main(argv=None):
    try:
        if argv:raise ValueError("unexpected arguments")
        rows=run_all(FAMILIES)
        print(json.dumps({"schema":"offline-cognition-source-qualification.v1",
            "domains":len(rows),"cases":sum(x["cases"] for x in rows),
            "admitted":sum(x["admitted"] for x in rows),
            "rejected":sum(x["rejected"] for x in rows),
            "native_inference_tested":False,"release_certified":False},sort_keys=True))
        return 0
    except BaseException as exc:
        print(json.dumps({"status":"held","error_class":type(exc).__name__}),file=sys.stderr)
        return 2
if __name__=="__main__":raise SystemExit(main())
