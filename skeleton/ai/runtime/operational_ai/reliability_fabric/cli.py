"""Source-only AI fabric qualification; actual model and device remain held."""
import json
import sys
from .fixtures import run_all
from .contracts import Rejected
def main(argv=None):
    if argv is None: argv=sys.argv[1:]
    if argv:raise Rejected("unrecognized qualification arguments")
    try:
        output=run_all()
        print(json.dumps({"status":"source-gates-executed-not-device-certified",
             "domains":len(output),"cases":sum(x["cases"] for x in output),
             "accepted":sum(x["accepted"] for x in output),
             "rejected":sum(x["rejected"] for x in output),
             "real_model_e2e":False,"release_certified":False},sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status":"held","error_class":type(exc).__name__}),file=sys.stderr)
        return 2
if __name__=="__main__":
    raise SystemExit(main())
