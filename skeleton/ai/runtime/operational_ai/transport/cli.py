"""Executable local-first AI CLI, no game engine or hosted model required.

Example:
 python -m skeleton.ai.runtime.operational_ai.transport.cli \\
   --checkpoint ./my-model.json --sha256 <verified_sha> --license <license> \\
   --database ./private/chat.sqlite3 --memory-db ./private/memory.sqlite3 \\
   --journal-db ./private/audit.sqlite3 --message 'Hello'

The checkpoint is always operator-supplied and digest-pinned. No models are
silently downloaded, and the test backend is never available from this CLI.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
from contextlib import ExitStack
from ..authority.budgets import Limits
from ..authority.canonical import ContractViolation,require_digest
from ..authority.identity import Actor
from ..context.memory import MemoryStore
from ..model.catalog import ModelCatalog,ModelArtifact
from ..model.native import from_checkpoint
from ..model.gateway import ModelGateway
from ..orchestration.service import OfflineAIService
from ..persistence.journal import EventJournal
from ..tools.builtins import register_builtins
from ..tools.catalog import ToolCatalog
from ..deployment.boot.identity import PrincipalBinding,establish_binding
from ..model.gguf.file_guard import open_trusted_root
from ..orchestration.custody.session import ProcessSessionFence


def build_service(args:argparse.Namespace,stack:ExitStack)->OfflineAIService:
    # All persistent stores MUST share one owner-private directory. This
    # prevents an independent CLI path from bypassing principal custody.
    locations=(args.database.absolute(),args.memory_db.absolute(),args.journal_db.absolute())
    state=locations[0].parent
    if any(path.parent!=state or path.name in ('.','..') for path in locations):
        raise ContractViolation("AI stores must share one private state directory")
    root_fd=open_trusted_root(state)
    try:
        if os.fstat(root_fd).st_mode&0o077:
            raise ContractViolation("AI state directory must be private")
    finally:
        os.close(root_fd)
    from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
    checkpoint=Path(args.checkpoint).absolute()
    artifact=ModelArtifact(args.model_name,checkpoint.name,args.sha256,checkpoint.stat().st_size,
                           args.license,tokenizer_sha256=args.tokenizer_sha256)
    backend=from_checkpoint(ModelCatalog(checkpoint.parent,[artifact]),artifact.name)
    # Pin both actor and model identities *before* any SQLite file is opened.
    establish_binding(state,PrincipalBinding(args.tenant,args.user,
                       backend.model_digest,backend.tokenizer_digest))
    root_fd=open_trusted_root(state)
    try:
        try:os.mkdir('session_locks',mode=0o700,dir_fd=root_fd)
        except FileExistsError:pass
    finally:os.close(root_fd)
    process_fence=stack.enter_context(ProcessSessionFence(state/'session_locks'))
    store=stack.enter_context(OfflineChatStore(locations[0]))
    memory=stack.enter_context(MemoryStore(locations[1]))
    journal=stack.enter_context(EventJournal(locations[2]))
    actor=Actor(args.tenant,args.user,backend.model_digest,backend.tokenizer_digest)
    catalog=ToolCatalog()
    register_builtins(catalog)
    runtime_limit=backend.engine.runtime.limits.max_context
    safe_context=min(runtime_limit,args.context_tokens)
    if safe_context<=args.max_new_tokens:
        raise ContractViolation("model context too small for requested completion")
    limits=Limits(context_tokens=safe_context,output_tokens=args.max_new_tokens,
                  input_bytes=args.input_bytes,output_bytes=args.output_bytes)
    return OfflineAIService(actor=actor,gateway=ModelGateway(backend),chat_store=store,
                            memory=memory,journal=journal,catalog=catalog,limits=limits,
                            process_fence=process_fence)


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description="Skeleton offline AI functional product")
    parser.add_argument("--checkpoint",required=True,type=Path)
    parser.add_argument("--sha256",required=True)
    parser.add_argument("--license",required=True)
    parser.add_argument("--tokenizer-sha256")
    parser.add_argument("--model-name",default="native")
    parser.add_argument("--tenant",default="local")
    parser.add_argument("--user",default="operator")
    parser.add_argument("--database",required=True,type=Path)
    parser.add_argument("--memory-db",required=True,type=Path)
    parser.add_argument("--journal-db",required=True,type=Path)
    parser.add_argument("--session")
    parser.add_argument("--request-id")
    parser.add_argument("--system")
    parser.add_argument("--max-new-tokens",type=int,default=64)
    parser.add_argument("--context-tokens",type=int,default=8192)
    parser.add_argument("--input-bytes",type=int,default=4096)
    parser.add_argument("--output-bytes",type=int,default=16384)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--message")
    mode.add_argument("--history",action="store_true")
    mode.add_argument("--status",action="store_true")
    mode.add_argument("--serve",action="store_true")
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--bearer-env",default="SKELETON_LOCAL_AI_BEARER")
    args=parser.parse_args(argv)
    if args.session and args.system:
        parser.error("system instruction can only be supplied when creating a session")
    if args.serve:
        candidate=os.environ.get(args.bearer_env,'')
        if not 32<=len(candidate)<=512 or any(ord(c)<33 or ord(c)>126 for c in candidate):
            print(json.dumps({'status':'blocked','reason':'InvalidBearerSecret'}),file=sys.stderr)
            return 2
    try:
        require_digest(args.sha256)
        with ExitStack() as stack:
            service=build_service(args,stack)
            if args.serve:
                from .http import LocalHTTPServer
                token=os.environ.get(args.bearer_env,"")
                from .dispatch import Dispatcher
                with LocalHTTPServer(("127.0.0.1",args.port), Dispatcher(service), token) as server:
                    print(json.dumps({"listen":"127.0.0.1","port":server.server_port,
                                      "mode":"private-loopback-bearer"}))
                    server.serve_forever(poll_interval=0.2)
                return 0
            session=args.session or service.create(system=args.system)
            if args.history:
                print(json.dumps(service.history(session),sort_keys=True));return 0
            if args.status:
                print(json.dumps(service.status(session),sort_keys=True));return 0
            result=service.turn(session=session,request_id=args.request_id or "req_"+secrets.token_hex(12),
                                question=args.message)
            print(json.dumps(result.to_record(),ensure_ascii=False,sort_keys=True))
            return 0
    except (ContractViolation,OSError,ValueError,RuntimeError) as exc:
        print(json.dumps({"status":"blocked","reason":type(exc).__name__}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
