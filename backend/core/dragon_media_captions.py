"""Immutable owner-scoped VTT/SRT tracks bound to exact retained media bytes."""
from __future__ import annotations

import hashlib
import re
import time

from core.dragon_game_corpus import _id,digest
from core.dragon_hoarder_bulk import owner_key,StorageHeld
from core.dragon_media_archive import MediaArchive

MAX_BYTES=4*1024*1024
MAX_CUES=20000
MAX_TEXT=2048
MAX_TRACKS=64
MAX_TIME=7*86400*1000
LANG=re.compile(r"[a-z]{2,8}(?:-[a-z0-9]{1,8}){0,3}|und")
STAMP=re.compile(r"(?:(\d{1,3}):)?([0-5]\d):([0-5]\d)[.,](\d{3})")
TIMING=re.compile(r"^(\S+)\s+-->\s+(\S+)(?:\s+.*)?$")
SCHEMA="""
CREATE TABLE IF NOT EXISTS media_tracks(
 owner TEXT NOT NULL,media TEXT NOT NULL,id TEXT NOT NULL,language TEXT NOT NULL,
 format TEXT NOT NULL,digest TEXT NOT NULL,media_sha TEXT NOT NULL,
 created INTEGER NOT NULL,cues INTEGER NOT NULL,PRIMARY KEY(owner,media,id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS media_cues(
 owner TEXT NOT NULL,media TEXT NOT NULL,track TEXT NOT NULL,ordinal INTEGER NOT NULL,
 start_ms INTEGER NOT NULL,end_ms INTEGER NOT NULL,text TEXT NOT NULL,
 PRIMARY KEY(owner,media,track,ordinal),
 FOREIGN KEY(owner,media,track) REFERENCES media_tracks(owner,media,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS media_cue_time ON media_cues(owner,media,track,start_ms,ordinal);
CREATE VIRTUAL TABLE IF NOT EXISTS media_cue_fts USING fts5(
 owner,media,track,ordinal UNINDEXED,text,tokenize='unicode61'
);
"""


def _ms(value):
    match=STAMP.fullmatch(value)
    if not match:raise ValueError("caption timestamp")
    h,m,s,ms=map(int,(x or 0 for x in match.groups()))
    result=((h*60+m)*60+s)*1000+ms
    if result>MAX_TIME:raise ValueError("caption duration")
    return result


def parse_captions(raw,format):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_BYTES or format not in {"vtt","srt"}:
        raise ValueError("caption bounds")
    text=raw.decode("utf-8-sig").replace("\r\n","\n").replace("\r","\n")
    if any(ord(c)<32 and c not in "\t\n" for c in text):
        raise ValueError("control characters")
    if format=="vtt":
        head,sep,text=text.partition("\n")
        if not sep or not (head=="WEBVTT" or head.startswith("WEBVTT ")):
            raise ValueError("VTT header")
    result=[]
    for block in re.split(r"\n[ \t]*\n",text.strip()):
        if not block.strip():continue
        lines=block.splitlines()
        if format=="vtt" and (lines[0]=="NOTE" or lines[0].startswith("NOTE ")):
            continue
        if lines[0] in {"STYLE","REGION"}:raise ValueError("unsupported presentation block")
        timing=TIMING.fullmatch(lines[0])
        if timing is None and len(lines)>=2:
            if format=="srt" and not lines[0].isdigit():raise ValueError("SRT cue identity")
            timing=TIMING.fullmatch(lines[1]);lines=lines[1:]
        if not timing:raise ValueError("caption timing missing")
        start,end=map(_ms,timing.groups())
        value="\n".join(lines[1:]).strip()
        if not value or len(value)>MAX_TEXT or not 0<=start<end<=MAX_TIME:
            raise ValueError("caption cue bounds")
        if result and start<result[-1][0]:raise ValueError("caption time order")
        result.append((start,end,value))
        if len(result)>MAX_CUES:raise ValueError("caption cue quota")
    if not result:raise ValueError("empty caption track")
    return result


def erase_media_captions(db,owner,mid):
    """Invoke under the same catalogue transaction as media withdrawal."""
    db.execute("DELETE FROM media_cue_fts WHERE owner=? AND media=?",(owner,mid))
    db.execute("DELETE FROM media_cues WHERE owner=? AND media=?",(owner,mid))
    db.execute("DELETE FROM media_tracks WHERE owner=? AND media=?",(owner,mid))


class MediaCaptions:
    def __init__(self,archive=None):
        self.media=archive or MediaArchive()

    def import_track(self,scope,mid,*,language,format,raw,rights_acknowledged):
        if rights_acknowledged is not True or not isinstance(language,str) or not LANG.fullmatch(language):
            raise ValueError("caption rights and language")
        cues=parse_captions(raw,format)
        owner=owner_key(scope);mid=_id(mid)
        fingerprint=hashlib.sha256(raw).hexdigest()
        track=digest([owner,mid,language,format,fingerprint])
        with self.media._db() as db:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            try:
                media=self.media._row(db,scope,mid,("sealed",))
                if not media["mime"].startswith(("video/","audio/")):raise ValueError("caption media type")
                old=db.execute("SELECT * FROM media_tracks WHERE owner=? AND media=? AND id=?",(owner,mid,track)).fetchone()
                if old:
                    if old["digest"]!=fingerprint or old["media_sha"]!=media["sha256"] or old["cues"]!=len(cues):
                        raise StorageHeld("caption replay witness")
                else:
                    if db.execute("SELECT COUNT(*) FROM media_tracks WHERE owner=? AND media=?",(owner,mid)).fetchone()[0]>=MAX_TRACKS:
                        raise StorageHeld("caption track quota")
                    db.execute("INSERT INTO media_tracks VALUES(?,?,?,?,?,?,?,?,?)",
                        (owner,mid,track,language,format,fingerprint,media["sha256"],int(time.time()),len(cues)))
                    db.executemany("INSERT INTO media_cues VALUES(?,?,?,?,?,?,?)",
                        [(owner,mid,track,i,start,end,value) for i,(start,end,value) in enumerate(cues)])
                    db.executemany("INSERT INTO media_cue_fts(owner,media,track,ordinal,text) VALUES(?,?,?,?,?)",
                        [(owner,mid,track,i,value) for i,(_,_,value) in enumerate(cues)])
                self.media._row(db,scope,mid,("sealed",))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return {"track_id":track,"media_id":mid,"sha256":fingerprint,"cues":len(cues),
                "replayed":bool(old),"user_supplied":True,"training_allowed":False}

    def tracks(self,scope,mid):
        owner=owner_key(scope);mid=_id(mid)
        with self.media._db() as db:
            db.executescript(SCHEMA)
            media=self.media._row(db,scope,mid,("sealed",))
            rows=db.execute("""SELECT id AS track_id,language,format,digest AS sha256,cues,created
                FROM media_tracks WHERE owner=? AND media=? AND media_sha=? ORDER BY language,created DESC,id LIMIT ?""",
                (owner,mid,media["sha256"],MAX_TRACKS)).fetchall()
            self.media._row(db,scope,mid,("sealed",))
        return {"media_id":mid,"tracks":[dict(x) for x in rows],"valid_until":media["expires_at"],
                "user_supplied":True,"training_allowed":False}

    def query(self,scope,mid,track,*,q=None,after=None,limit=32):
        if type(limit) is not int or not 1<=limit<=64:raise ValueError("caption limit")
        if after is not None and (type(after) is not int or not 0<=after<MAX_CUES):
            raise ValueError("caption cursor")
        owner=owner_key(scope);mid,track=map(_id,(mid,track))
        with self.media._db() as db:
            db.executescript(SCHEMA)
            media=self.media._row(db,scope,mid,("sealed",))
            meta=db.execute("SELECT * FROM media_tracks WHERE owner=? AND media=? AND id=? AND media_sha=?",
                (owner,mid,track,media["sha256"])).fetchone()
            if not meta:raise LookupError("track unavailable")
            lower=after if after is not None else -1
            if q is None:
                rows=db.execute("""SELECT ordinal,start_ms,end_ms,text FROM media_cues WHERE owner=? AND media=?
                    AND track=? AND ordinal>? ORDER BY ordinal LIMIT ?""",(owner,mid,track,lower,limit+1)).fetchall()
            else:
                if not isinstance(q,str) or not 1<=len(q)<=256:raise ValueError("caption query")
                terms=re.findall(r"[^\W_]+",q,flags=re.UNICODE)[:16]
                if not terms:raise ValueError("caption query tokens")
                fts='owner:"'+owner+'" AND media:"'+mid+'" AND track:"'+track+'" AND text:('+" AND ".join('"'+w+'"' for w in terms)+')'
                deadline=time.monotonic()+2
                db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
                try:
                    rows=db.execute("""SELECT c.ordinal,c.start_ms,c.end_ms,c.text FROM media_cue_fts f
                        JOIN media_cues c ON c.owner=f.owner AND c.media=f.media AND c.track=f.track AND c.ordinal=f.ordinal
                        WHERE media_cue_fts MATCH ? AND c.owner=? AND c.media=? AND c.track=? AND c.ordinal>?
                        ORDER BY c.ordinal LIMIT ?""",(fts,owner,mid,track,lower,limit+1)).fetchall()
                finally:db.set_progress_handler(None,0)
            self.media._row(db,scope,mid,("sealed",))
        return {"media_id":mid,"track_id":track,"cues":[dict(x) for x in rows[:limit]],
                "next_cursor":rows[limit-1]["ordinal"] if len(rows)>limit else None,
                "valid_until":media["expires_at"],"as_of_unix":time.time(),
                "user_supplied":True,"source_verified":False,"training_allowed":False}

    def revoke_track(self,scope,mid,track):
        owner=owner_key(scope);mid,track=map(_id,(mid,track))
        with self.media._db() as db:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            try:
                self.media._row(db,scope,mid,("sealed",))
                db.execute("DELETE FROM media_cue_fts WHERE owner=? AND media=? AND track=?",(owner,mid,track))
                db.execute("DELETE FROM media_cues WHERE owner=? AND media=? AND track=?",(owner,mid,track))
                result=db.execute("DELETE FROM media_tracks WHERE owner=? AND media=? AND id=?",(owner,mid,track))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return {"revoked":result.rowcount==1,"secure_erasure":False}
