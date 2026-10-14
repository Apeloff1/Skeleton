"""Privacy-scoped watch history and idle video discovery proposals.

No browsing or ingestion occurs in this module. A caller must obtain explicit
consent before recording history, requesting recommendations, or processing media.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
import json,math,sqlite3,ipaddress

@dataclass(frozen=True)
class VideoVisit:
    video_id:str
    canonical_url:str
    title:str
    watched_at:float
    duration_ms:int
    watched_ms:int
    tags:tuple[str,...]

def canonical_video_url(url:str)->str:
    parsed=urlsplit(url.strip())
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('video history requires public HTTPS URL')
    if parsed.port not in (None,443):raise ValueError('unsupported video URL port')
    host=parsed.hostname.lower()
    if host in ('localhost',) or host.endswith(('.localhost','.local','.internal','.test','.invalid')) or '.' not in host:
        raise ValueError('private or unqualified hostname')
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not address.is_global:raise ValueError('nonpublic address')
    # Never persist trackers or embedded tokens in watch history.
    safe_query=urlencode(sorted((k,v) for k,v in parse_qsl(parsed.query,keep_blank_values=True)
                              if k in ('v','id','list')))
    return urlunsplit(('https',host,parsed.path or '/',safe_query,''))

class DragonVideoHistory:
    def __init__(self,db:sqlite3.Connection):
        self.db=db
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_video_history(
          owner TEXT NOT NULL, video_id TEXT NOT NULL, canonical_url TEXT NOT NULL,
          title TEXT NOT NULL, watched_at REAL NOT NULL, duration_ms INTEGER NOT NULL,
          watched_ms INTEGER NOT NULL, tags_json TEXT NOT NULL,
          PRIMARY KEY(owner,video_id))""")
        self.db.commit()
    def record(self,owner:str,url:str,title:str,*,watched_at:float,
               duration_ms:int,watched_ms:int,tags:tuple[str,...]=(),
               consent:bool=False)->VideoVisit:
        if not consent:raise PermissionError('watch history requires explicit opt-in')
        if not owner or len(owner)>128:raise ValueError('invalid owner')
        canonical=canonical_video_url(url)
        if not title.strip() or len(title)>300 or not math.isfinite(watched_at):
            raise ValueError('invalid video metadata')
        if not 0<=watched_ms<=duration_ms<=86_400_000:raise ValueError('invalid viewing interval')
        if len(tags)>32 or any(not isinstance(x,str) or not x.strip() or len(x)>64 for x in tags):
            raise ValueError('invalid tags')
        normalized=tuple(sorted(set(x.casefold().strip() for x in tags)))
        video_id=sha256(canonical.encode()).hexdigest()
        with self.db:
            self.db.execute("""INSERT INTO dragon_video_history VALUES(?,?,?,?,?,?,?,?)
             ON CONFLICT(owner,video_id) DO UPDATE SET title=excluded.title,
             watched_at=excluded.watched_at,duration_ms=excluded.duration_ms,
             watched_ms=excluded.watched_ms,tags_json=excluded.tags_json""",
             (owner,video_id,canonical,title,watched_at,duration_ms,watched_ms,json.dumps(normalized)))
        return VideoVisit(video_id,canonical,title,watched_at,duration_ms,watched_ms,normalized)
    def recent(self,owner:str,*,limit:int=50)->tuple[VideoVisit,...]:
        if not owner or not 1<=limit<=500:raise ValueError('invalid history query')
        rows=self.db.execute("""SELECT video_id,canonical_url,title,watched_at,
          duration_ms,watched_ms,tags_json FROM dragon_video_history WHERE owner=?
          ORDER BY watched_at DESC,video_id LIMIT ?""",(owner,limit)).fetchall()
        return tuple(VideoVisit(*r[:6],tuple(json.loads(r[6]))) for r in rows)
    def prune(self,owner:str,*,older_than:float)->int:
        if not owner or len(owner)>128 or not math.isfinite(older_than):
            raise ValueError('invalid retention boundary')
        with self.db:
            cursor=self.db.execute('DELETE FROM dragon_video_history WHERE owner=? AND watched_at<?',
                                   (owner,older_than))
        return cursor.rowcount

    def erase(self,owner:str)->int:
        with self.db:
            cursor=self.db.execute('DELETE FROM dragon_video_history WHERE owner=?',(owner,))
        return cursor.rowcount
