"""Release readiness is an exact, complete check set; no inferred passes."""
from __future__ import annotations
import argparse,json,sys
from ...orchestration.execution_spine.failure_matrix import evaluate

def main(argv=None):
    p=argparse.ArgumentParser(description='Read exact-head AI release evidence JSON')
    p.add_argument('checks_json')
    a=p.parse_args(argv)
    try:
        with open(a.checks_json,encoding='utf8') as f:values=json.load(f)
        report=evaluate(values)
        print(json.dumps(report,sort_keys=True))
        return 0 if report['release_accepted'] else 3
    except Exception as exc:
        print(json.dumps({'status':'held','error_class':type(exc).__name__}),file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())
