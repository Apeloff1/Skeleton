"""No-download operator CLI for verified AI model install, inspection and repair.

Production package size requirements are never relaxed by CLI flags.
Usage:
  python -m skeleton.ai.runtime.operational_ai.deployment.install.cli install \\
    --archive /private/skeleton-ai.tar --install-root /private/models \\
    --model-id mymodel --install-id mymodel-v1
  python -m skeleton.ai.runtime.operational_ai.deployment.install.cli doctor \\
    --model-root /private/models/mymodel-v1
  python -m skeleton.ai.runtime.operational_ai.deployment.install.cli reconcile-audit \\
    --model-root /private/models/mymodel-v1 --state-dir /private/ai \\
    --session conversation_id --tenant local --user operator --approve
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from .installer import InstallError,install_approved_model
from .doctor import inspect_installed_model


def main(argv: list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description='Approved GGUF install and recovery; no network')
    actions=parser.add_subparsers(dest='action',required=True)
    installer=actions.add_parser('install',help='verify ordered 1.9GB bundle and install selected model')
    installer.add_argument('--archive',type=Path,required=True)
    installer.add_argument('--install-root',type=Path,required=True)
    installer.add_argument('--model-id',required=True)
    installer.add_argument('--install-id',required=True)
    doctor=actions.add_parser('doctor',help='read-only hash verification (not a quality test)')
    doctor.add_argument('--model-root',type=Path,required=True)
    recover=actions.add_parser('reconcile-audit',help='repair only missing audit from committed chat receipts')
    recover.add_argument('--model-root',type=Path,required=True)
    recover.add_argument('--state-dir',type=Path,required=True)
    recover.add_argument('--session',required=True)
    recover.add_argument('--tenant',required=True)
    recover.add_argument('--user',required=True)
    recover.add_argument('--approve',action='store_true',default=False)
    recover.add_argument('--dry-run',action='store_true',default=False)
    args=parser.parse_args(argv)
    try:
        if args.action=='install':
            result=install_approved_model(args.archive,args.install_root,
                 model_id=args.model_id,install_id=args.install_id)
            output=result.to_record()
        elif args.action=='doctor':
            output=inspect_installed_model(args.model_root).to_record()
            output['status']='content-verified-not-release-qualified'
        elif args.action=='reconcile-audit':
            # Model identity is verified without loading weights or allocating GPU/RAM.
            # Existing chat DB is a prerequisite; never initialize a new history.
            model=inspect_installed_model(args.model_root)
            state=args.state_dir.absolute()
            # Recovery can disclose or mutate private transcripts indirectly.
            # It must never bypass the principal/model binding enforced by
            # the real GGUF launcher, even in read-only --dry-run mode.
            from ..boot.identity import PrincipalBinding, inspect_binding
            inspect_binding(state, PrincipalBinding(args.tenant,args.user,
                model.model_sha256,model.model_sha256))
            from ...model.gguf.file_guard import open_trusted_root
            import os
            fd=open_trusted_root(state)
            try:
                if os.fstat(fd).st_mode&0o077:
                    raise InstallError('state directory is not private')
                os.stat('chat.sqlite',dir_fd=fd,follow_symlinks=False)
            finally:
                os.close(fd)
            from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
            from ...persistence.journal import EventJournal
            from ...authority.identity import Actor
            from ...orchestration.recovery import inspect,reconcile
            with ExitStack() as stack:
                store=stack.enter_context(OfflineChatStore(state/'chat.sqlite'))
                journal=stack.enter_context(EventJournal(state/'audit.sqlite'))
                actor=Actor(args.tenant,args.user,model.model_sha256,model.model_sha256)
                service=SimpleNamespace(store=store,journal=journal,actor=actor)
                if args.dry_run:
                    report=inspect(service,args.session)
                else:
                    report=reconcile(service,args.session,approved=args.approve)
                output={'status':report.status,'session':report.session,'turns':report.turns,
                        'missing_audits':report.missing_audits,'journal_head':report.audit_head,
                        'native_model_executed':False,'release_certified':False}
        else:
            raise InstallError('unknown operator action')
        print(json.dumps(output,sort_keys=True,ensure_ascii=False))
        return 0
    except (InstallError,ValueError,RuntimeError,OSError) as exc:
        # Do not echo paths, private content or raw exception strings to stdout.
        print(json.dumps({'status':'blocked','reason':type(exc).__name__}),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
