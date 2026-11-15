"""Bounded MMO entity graph and patch-to-patch dataset comparison.

Uses the immutable version-seal and owner shard authority already exposed by
DatasetShard. Relations are imported statements, not live game-state facts.
No live game action, private player API, instrumented game client or executable
external tool is called.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
import time

from core.dragon_game_corpus import _id,key,CatalogueHeld
from core.dragon_game_datasets import DatasetShard

MAX_NODES=256
MAX_EDGES=512
MAX_DEPTH=6
MAX_PAGE=64
MAX_RESPONSE_BYTES=2*1024*1024


def verified_record(row):
    if row is None:return None
    raw=row["data_json"]
    if hashlib.sha256(raw.encode()).hexdigest()!=row["row_hash"]:
        raise CatalogueHeld("dataset row witness differs")
    value=json.loads(raw)
    return {"key":row["record_key"],"record":value,"sha256":row["row_hash"]}


class DatasetExplorer:
    def __init__(self,scope,game,*,shard=None):
        self.shard=shard or DatasetShard(scope,game)
        self.owner=self.shard.owner;self.game=self.shard.game

    def _get_record(self,db,version,record):
        return verified_record(db.execute("""SELECT record_key,data_json,row_hash FROM dataset_records
            WHERE owner=? AND game=? AND version=? AND record_key=?""",
            (self.owner,self.game,version,record)).fetchone())

    def record(self,version,record):
        version=_id(version);record=key(record)
        with self.shard._db() as db:
            meta=self.shard._get(db,version)
            value=self._get_record(db,version,record)
            if value is None:raise LookupError("dataset record unavailable")
            self.shard._get(db,version)
        return {**value,"version":version,"valid_until":meta["expires_at"],"source_verified":False,"training_allowed":False}

    @staticmethod
    def _budget(db):
        deadline=time.monotonic()+2
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)

    def graph(self,version,record,*,direction="both",relation=None,max_depth=3,node_limit=128,edge_limit=256):
        """Cycle-safe, breadth-first graph window with explicit truncation.

        Scan bounded index-backed adjacency lists, not the entire entity table.
        Missing targets remain unresolved; they are never synthesized or loaded
        from other versions. Returned node IDs have independently verified rows.
        """
        version=_id(version);record=key(record)
        if direction not in {"out","in","both"}:raise ValueError("graph direction")
        if relation is not None:relation=key(relation)
        if (type(max_depth) is not int or not 0<=max_depth<=MAX_DEPTH
                or type(node_limit) is not int or not 1<=node_limit<=MAX_NODES
                or type(edge_limit) is not int or not 1<=edge_limit<=MAX_EDGES):
            raise ValueError("graph budget")
        with self.shard._db() as db:
            meta=self.shard._get(db,version);self._budget(db)
            try:
                root=self._get_record(db,version,record)
                if root is None:raise LookupError("graph root unavailable")
                nodes={record:{"key":record,"depth":0,"present":True,"sha256":root["sha256"]}}
                queue=deque([(record,0)])
                seen_edges=set();edges=[];truncated=False;unresolved=0
                while queue and len(edges)<edge_limit:
                    current,depth=queue.popleft()
                    if depth>=max_depth:continue
                    for mode in (("out","in") if direction=="both" else (direction,)):
                        field="record_key" if mode=="out" else "target"
                        args=[self.owner,self.game,version,current]
                        clause=""
                        if relation is not None:clause=" AND relation=?";args.append(relation)
                        # Bounded per-node examination even when the same edges
                        # are encountered in both directions.
                        remaining=edge_limit-len(edges)
                        args.append(remaining+1)
                        rows=db.execute("""SELECT record_key,relation,target FROM dataset_edges
                            WHERE owner=? AND game=? AND version=? AND """+field+"=?"+clause+
                            " ORDER BY relation,record_key,target LIMIT ?",args).fetchall()
                        if len(rows)>remaining:truncated=True
                        for row in rows[:remaining]:
                            edge=(row["record_key"],row["relation"],row["target"])
                            if edge in seen_edges:continue
                            next_id=edge[2] if mode=="out" else edge[0]
                            if next_id not in nodes:
                                if len(nodes)>=node_limit:
                                    truncated=True
                                    continue
                                found=self._get_record(db,version,next_id)
                                nodes[next_id]={"key":next_id,"depth":depth+1,"present":found is not None,
                                    "sha256":found["sha256"] if found else None}
                                if found:queue.append((next_id,depth+1))
                                else:unresolved+=1
                            seen_edges.add(edge)
                            edges.append({"from":edge[0],"relation":edge[1],"to":edge[2]})
                            if len(edges)>=edge_limit:
                                truncated=True;break
                        if len(edges)>=edge_limit:break
                if queue:truncated=True
                self.shard._get(db,version)
            finally:db.set_progress_handler(None,0)
        return {"version":version,"root":record,"nodes":list(nodes.values()),"edges":edges,
                "unresolved_nodes":unresolved,"truncated":truncated,"max_depth":max_depth,
                "valid_until":meta["expires_at"],"source_verified":False,"training_allowed":False}

    def compare(self,left,right,*,after=None,limit=32,changes_only=True):
        """Index-backed ordered merge of two immutable dataset versions.

        Pagination advances by examined key, not emitted differences. Empty
        changed windows may still provide a next cursor. No claim of a global
        count until the caller has walked every window.
        """
        left,right=map(_id,(left,right))
        if left==right:raise ValueError("distinct versions required")
        if type(limit) is not int or not 1<=limit<=MAX_PAGE or type(changes_only) is not bool:
            raise ValueError("comparison bounds")
        after=key(after) if after is not None else ""
        with self.shard._db() as db:
            a=self.shard._get(db,left);b=self.shard._get(db,right)
            if (a["dataset"],a["source"])!=(b["dataset"],b["source"]):
                raise ValueError("comparison requires same dataset and source")
            self._budget(db)
            try:
                def window(version):
                    return db.execute("""SELECT record_key,row_hash FROM dataset_records
                        WHERE owner=? AND game=? AND version=? AND record_key>?
                        ORDER BY record_key LIMIT ?""",
                        (self.owner,self.game,version,after,limit+1)).fetchall()
                aa={r["record_key"]:r["row_hash"] for r in window(left)}
                bb={r["record_key"]:r["row_hash"] for r in window(right)}
                keys=sorted(set(aa)|set(bb))
                output=[];counts={"added":0,"removed":0,"changed":0,"unchanged":0}
                scanned=0;size=0;last=None
                for k in keys[:limit]:
                    ah,bh=aa.get(k),bb.get(k)
                    state="added" if ah is None else "removed" if bh is None else "unchanged" if ah==bh else "changed"
                    item={"key":k,"change":state,"before_sha256":ah,"after_sha256":bh}
                    # Compare canonical hash values, not arbitrary merged text.
                    # Read actual record bytes on demand via exact key endpoint.
                    if state!="unchanged" or not changes_only:
                        for version,expected in ((left,ah),(right,bh)):
                            if expected is not None:
                                found=self._get_record(db,version,k)
                                if found is None or found["sha256"]!=expected:raise CatalogueHeld("comparison witness")
                        encoded=len(json.dumps(item,ensure_ascii=False).encode())
                        if size+encoded>MAX_RESPONSE_BYTES:break
                        size+=encoded;output.append(item)
                    counts[state]+=1;scanned+=1;last=k
                self.shard._get(db,left);self.shard._get(db,right)
            finally:db.set_progress_handler(None,0)
        return {"left":left,"right":right,"changes":output,"window_counts":counts,"scanned":scanned,
                "next_cursor":last if scanned<len(keys) else None,
                "complete":scanned==len(keys),"valid_until":min(a["expires_at"],b["expires_at"]),
                "source_verified":False,"training_allowed":False}

    def compare_record(self,left,right,record):
        """Exact per-record patch comparison, bounded to two witnessed rows."""
        left,right=map(_id,(left,right));record=key(record)
        if left==right:raise ValueError("distinct versions required")
        with self.shard._db() as db:
            a=self.shard._get(db,left);b=self.shard._get(db,right)
            if (a["dataset"],a["source"])!=(b["dataset"],b["source"]):
                raise ValueError("comparison requires same dataset and source")
            before=self._get_record(db,left,record);after=self._get_record(db,right,record)
            if before is None and after is None:raise LookupError("record unavailable")
            state="added" if before is None else "removed" if after is None else "unchanged" if before["sha256"]==after["sha256"] else "changed"
            aa=before["record"] if before else {}
            bb=after["record"] if after else {}
            fields=[]
            for name in sorted(set(aa)|set(bb)):
                if name not in aa:kind="added"
                elif name not in bb:kind="removed"
                elif json.dumps(aa[name],sort_keys=True,ensure_ascii=False,separators=(",",":"))!=json.dumps(bb[name],sort_keys=True,ensure_ascii=False,separators=(",",":")):kind="changed"
                else:continue
                fields.append({"field":name,"change":kind})
            self.shard._get(db,left);self.shard._get(db,right)
        return {"left":left,"right":right,"key":record,"change":state,"before":before,"after":after,
                "fields":fields,"valid_until":min(a["expires_at"],b["expires_at"]),
                "source_verified":False,"training_allowed":False}
