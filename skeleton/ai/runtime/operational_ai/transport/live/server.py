"""Authenticated loopback HTTP extension: exact durable journal event pages.

The endpoint is replay-only; no speculative model token bytes are published as
committed stream events. Clients poll with signed continuation cursors.
"""
from __future__ import annotations
from urllib.parse import urlsplit,parse_qs
import json
from ..http import LocalHTTPServer,RequestHandler
from .cursor import CursorSigner,CursorError
from .replay import EventReplay

class LiveEventHTTPServer(LocalHTTPServer):
    def __init__(self,address,dispatcher,token:str,*,cursor_key:bytes):
        super().__init__(address,dispatcher,token)
        self.replay=EventReplay(dispatcher.service.journal,CursorSigner(cursor_key))
        self.RequestHandlerClass=LiveEventHandler

class LiveEventHandler(RequestHandler):
    server:LiveEventHTTPServer

    def do_GET(self):
        route=urlsplit(self.path)
        if route.path!='/v2/events':return super().do_GET()
        if not self._authorize():return
        try:
            if len(self.path)>2048:raise CursorError('query too long')
            args=parse_qs(route.query,keep_blank_values=True,strict_parsing=True,max_num_fields=4)
            if set(args)-{'session','cursor','limit'}:raise CursorError('unknown replay parameters')
            if not 'session' in args or any(len(x)!=1 for x in args.values()):
                raise CursorError('invalid replay query')
            session=args['session'][0]
            from ...authority.identity import require_id
            require_id(session,field='session')
            # The service enforces actor-bound model and conversation identity.
            self.server.dispatcher.service.history(session)
            limit=int(args.get('limit',['32'])[0])
            cursor=args['cursor'][0] if 'cursor' in args else None
            actor=self.server.dispatcher.service.actor
            page=self.server.replay.page(session=session,tenant=actor.tenant,user=actor.user,
                                          cursor=cursor,limit=limit)
            self._write(200,'ok',{'events':list(page.events),'next_cursor':page.next_cursor,
                                  'has_more':page.has_more,'latest_seq':page.latest_seq})
        except (CursorError,ValueError,KeyError):
            self._write(400,'bad-request',{'reason':'replay-cursor-rejected'})
        except Exception:
            self._write(403,'denied',{'reason':'session-not-accessible'})
