"""Operator-only GGUF qualification. No model-extracted prompts in output."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .contracts import QualificationInput
from .runner import probe_first_boot
from .paths import publish_private_report


def main(argv=None):
    parser=argparse.ArgumentParser(description='Run a real, private GGUF first-boot and replay probe')
    parser.add_argument('--model-root',type=Path,required=True)
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--tenant',required=True)
    parser.add_argument('--subject',required=True)
    parser.add_argument('--report-dir',type=Path,required=True)
    parser.add_argument('--report-name',required=True)
    parser.add_argument('--context-tokens',type=int,default=2048)
    parser.add_argument('--max-new-tokens',type=int,default=64)
    parser.add_argument('--threads',type=int,default=2)
    parser.add_argument('--gpu-layers',type=int,default=0)
    args=parser.parse_args(argv)
    try:
        plan=QualificationInput(model_root=args.model_root,state_dir=args.state_dir,
            tenant=args.tenant,subject=args.subject,n_ctx=args.context_tokens,
            max_new_tokens=args.max_new_tokens,n_threads=args.threads,gpu_layers=args.gpu_layers)
        report=probe_first_boot(plan)
        publish_private_report(args.report_dir,args.report_name,report)
        print(json.dumps({'status':report['status'], 'proof_sha256':report['proof_sha256']},sort_keys=True))
        return 0
    except BaseException as exc:
        # Never print model paths, prompts, model output, keys, credentials,
        # evidence passages or exception payloads from untrusted backends.
        print(json.dumps({'status':'qualification-held','error_class':type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
