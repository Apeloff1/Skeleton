"""Persistent, private, fully offline GGUF conversation product.

Unlike `gguf_cli` one-shot model checks, this composes the authenticated
operational AI session service: hash-pinned real model, persisted chat,
scoped memory, integrity journal and no automatic tool execution.
"""
from __future__ import annotations
import argparse,json,os,secrets,sys
from contextlib import ExitStack
from pathlib import Path
from ..model.gguf.service import load_approved_manifest,activate_model
from ..model.gguf.manifest import GGUFManifestError
from ..model.gateway import ModelGateway
from ..authority.identity import Actor
from ..authority.budgets import Limits
from ..context.sealed_memory.keys import load_key_file
from ..context.sealed_memory.store import SealedMemoryStore
from ..persistence.journal import EventJournal
from ..orchestration.service import OfflineAIService
from ..orchestration.custody.session import ProcessSessionFence
from ..model.gguf.file_guard import open_trusted_root
from ..deployment.boot.identity import PrincipalBinding, establish_binding
from ..deployment.install.doctor import inspect_installed_model


def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(description='Real offline GGUF + durable AI conversation')
    p.add_argument('--model-root',type=Path,required=True)
    p.add_argument('--manifest',default='model.manifest.json')
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--memory-key-file',type=Path,required=True)
    p.add_argument('--tenant',default='local')
    p.add_argument('--user',default='operator')
    p.add_argument('--session')
    p.add_argument('--request-id')
    p.add_argument('--message')
    p.add_argument('--system')
    p.add_argument('--serve',action='store_true')
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--context-tokens',type=int,default=2048)
    p.add_argument('--max-new-tokens',type=int,default=256)
    p.add_argument('--threads',type=int,default=4)
    p.add_argument('--gpu-layers',type=int,default=0)
    args=p.parse_args(argv)
    if (args.message is None)==(not args.serve):
        p.error('specify exactly one of --message or --serve')
    if args.session and args.system:p.error('system can only be set on new session')
    if args.serve:
        candidate=os.environ.get('SKELETON_LOCAL_AI_BEARER','')
        if not 32<=len(candidate)<=512 or any(ord(c)<33 or ord(c)>126 for c in candidate):
            print(json.dumps({'status':'blocked','reason':'InvalidBearerSecret'}),file=sys.stderr)
            return 2
    try:
        state=args.state_dir.absolute()
        if not state.is_dir() or state.is_symlink() or state.stat().st_mode&0o077:
            raise GGUFManifestError('private state directory must exist, non-symlink, mode 0700')
        # Never serve a model staged outside the source-bound approved installer.
        installed=inspect_installed_model(args.model_root)
        manifest=load_approved_manifest(args.model_root,args.manifest)
        key_material=load_key_file(args.memory_key_file)
        if installed.model_sha256!=manifest.model_sha256:
            raise GGUFManifestError('installed model receipt does not bind activated model')
        # The chat store itself binds model/tokenizer, not tenant/user. Refuse
        # any unbound legacy database instead of implicitly adopting it.
        establish_binding(state,PrincipalBinding(args.tenant,args.user,
                           manifest.model_sha256,manifest.model_sha256))
        root_fd=open_trusted_root(state)
        try:
            try:
                os.mkdir('session_locks',0o700,dir_fd=root_fd)
            except FileExistsError:
                pass
        finally:
            os.close(root_fd)
        with ExitStack() as stack:
            backend=stack.enter_context(activate_model(args.model_root,manifest,
                n_ctx=args.context_tokens,n_threads=args.threads,n_gpu_layers=args.gpu_layers))
            from skeleton.ai.model_runtime.offline_chat import OfflineChatStore
            store=stack.enter_context(OfflineChatStore(state/'chat.sqlite'))
            memory=stack.enter_context(SealedMemoryStore(state/'memory.sqlite',
                key_material))
            journal=stack.enter_context(EventJournal(state/'audit.sqlite'))
            process_fence=stack.enter_context(ProcessSessionFence(state/'session_locks'))
            actor=Actor(args.tenant,args.user,backend.model_digest,backend.tokenizer_digest)
            limits=Limits(input_bytes=32768,output_bytes=262144,
                context_tokens=args.context_tokens,output_tokens=args.max_new_tokens,
                tool_calls=0,retrieval_hits=8,deadline_ms=120000)
            service=OfflineAIService(actor=actor,gateway=ModelGateway(backend),chat_store=store,
                                      memory=memory,journal=journal,limits=limits,process_fence=process_fence)
            if args.serve:
                from .http import LocalHTTPServer
                from .dispatch import Dispatcher
                token=os.environ.get('SKELETON_LOCAL_AI_BEARER','')
                with LocalHTTPServer(('127.0.0.1',args.port),Dispatcher(service),token) as server:
                    print(json.dumps({'mode':'private-offline-gguf','bind':'127.0.0.1',
                        'port':server.server_port,'model_sha256':backend.model_digest}))
                    server.serve_forever(poll_interval=.2)
                return 0
            session=args.session or service.create(system=args.system)
            result=service.turn(session=session,request_id=args.request_id or 'req_'+secrets.token_hex(12),
                                question=args.message)
            print(json.dumps(result.to_record(),sort_keys=True,ensure_ascii=False))
        return 0
    except (GGUFManifestError,ValueError,RuntimeError,OSError) as exc:
        print(json.dumps({'status':'blocked','reason':type(exc).__name__}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
