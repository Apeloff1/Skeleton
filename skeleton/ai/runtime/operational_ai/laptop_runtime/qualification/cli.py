"""Complete real-input-gate fixture execution; cannot certify device or model quality."""
import json
import sys
from .runner import run_all

def main(argv=None):
    try:
        if argv:raise ValueError("fixture runner accepts no arguments")
        observations=run_all()
        print(json.dumps({"schema":"laptop-qualification-run.v1",
            "domains":len(observations),"cases":sum(x["cases"] for x in observations),
            "accepted":sum(x["accepted"] for x in observations),
            "rejected":sum(x["rejected"] for x in observations),
            "redacted":sum(x["redacted"] for x in observations),
            "status":"real-python-contract-cases-not-model-certified",
            "native_model_inference_tested":False,"release_certified":False},sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status":"blocked","error_class":type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=="__main__":raise SystemExit(main())
