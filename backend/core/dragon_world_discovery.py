"""Operator-authorized worldwide feed subscriptions, separate from crawl grants.

One durable lease per feed and origin, no cookies, credentials, proxy, redirects
or generated network targets. Results enter the existing metadata import queue;
a discovered link never grants authority to fetch it. Public feed permissions
must be explicitly renewed and expired subscriptions stop by default.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from uuid import uuid4
from urllib.parse import urlsplit
from xml.etree import ElementTree

from core.dragon_game_corpus import GameCorpus,source_url,digest,clean
from core.dragon_hoarder_bulk import owner_key
from core.dragon_release_queue import ReleaseQueue
from core.dragon_release_discovery import PROVIDERS,MAX_FEED_BYTES
from skeleton.ai.webcrawler.core import RobotsCache
from skeleton.ai.webcrawler.http import SafeHttpFetcher

AGENT="SkeletonAI-DragonDiscovery/1.0"
MAX_SUBSCRIPTIONS=100_000
MAX_LEASE=90
MIN_INTERVAL=900
MAX_INTERVAL=7*86400
MAX_GRANT=30*86400
MAX_ROBOTS=256*1024
MAX_LARGE_FEED=4_000_000  # canonical pinned transport's hard response cap
MAX_SITEMAP_URLS=50_000
MAX_STEAM_APPS=250_000
PAGES_PER_PULSE=4
SCHEMA="""
CREATE TABLE IF NOT EXISTS world_subscriptions(
 owner TEXT NOT NULL,id TEXT NOT NULL,scope_json TEXT NOT NULL,url TEXT NOT NULL,
 origin TEXT NOT NULL,adapter TEXT NOT NULL,provider TEXT,game_external_id TEXT,title TEXT,
 interval_seconds INTEGER NOT NULL,expires_at INTEGER NOT NULL,enabled INTEGER NOT NULL,
 due INTEGER NOT NULL,lease TEXT,lease_until INTEGER NOT NULL DEFAULT 0,
 failures INTEGER NOT NULL DEFAULT 0,last_digest TEXT,last_batch TEXT,reason TEXT,
 pending_digest TEXT,pending_page INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(owner,id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS world_discovery_due ON world_subscriptions(enabled,due,owner,id);
CREATE TABLE IF NOT EXISTS world_origin_guard(
 origin TEXT PRIMARY KEY,ready INTEGER NOT NULL,lease TEXT,lease_until INTEGER NOT NULL
) WITHOUT ROWID;
"""


def _hex(value):
    if not isinstance(value,str) or len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("subscription identity")
    return value


class DiscoveryHeld(RuntimeError):
    pass


def fetch_public_feed(url, *, fetcher=None,max_bytes=MAX_FEED_BYTES):
    """Fail closed on robots, origin change and private/cache-sensitive responses."""
    if type(max_bytes) is not int or not 1<=max_bytes<=MAX_LARGE_FEED:raise ValueError('feed byte cap')
    url=source_url(url)
    parsed=urlsplit(url)
    origin="https://"+parsed.hostname
    transport=fetcher or SafeHttpFetcher(timeout_seconds=8,max_redirects=0,
        allowed_hosts=frozenset({parsed.hostname}),bind_dns_to_socket=True,respect_environment_proxy=False)
    robots=transport.fetch_once(origin+"/robots.txt",user_agent=AGENT,max_bytes=MAX_ROBOTS)
    if robots.status!=200 or robots.url!=origin+"/robots.txt":
        raise DiscoveryHeld("robots unavailable")
    cache=RobotsCache(AGENT)
    cache.install(origin,robots.body.decode("utf-8","strict"),fetched_at=time.time())
    if not cache.allowed(url):
        raise DiscoveryHeld("robots denied")
    # Respect delay by declining policies that require a longer hold than this
    # single bounded operation. Cross-pulse origin pacing is durable.
    delay=cache.crawl_delay(url) or 0
    request_rate=cache.request_rate(url)
    if delay>5 or request_rate is not None:
        raise DiscoveryHeld("robots rate requires external scheduling review")
    time.sleep(max(1.0,float(delay)))
    response=transport.fetch_once(url,user_agent=AGENT,max_bytes=max_bytes)
    if response.status!=200 or response.url!=url:
        raise DiscoveryHeld("feed response not exact")
    headers={str(k).lower():str(v).lower() for k,v in response.headers.items()}
    control=headers.get("cache-control","")
    directives=headers.get("x-robots-tag","")
    if any(x in directives for x in ("noarchive","noindex","none","nosnippet")):
        raise DiscoveryHeld("response retention denied")
    if any(x in control for x in ("private","no-store")) or headers.get("vary","")=="*" or any(
        x in headers.get("vary","") for x in ("cookie","authorization")) or "set-cookie" in headers:
        raise DiscoveryHeld("private or sensitive response")
    if not response.body or len(response.body)>max_bytes:
        raise DiscoveryHeld("feed size")
    return response.body


def sitemap_pages(raw,provider,external,title):
    """Partition a standards-size sitemap into stable bounded candidate batches."""
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_LARGE_FEED:
        raise ValueError("sitemap bounds")
    text=raw.decode("utf-8")
    if __import__("re").search(r"<!\s*(DOCTYPE|ENTITY)",text,__import__("re").IGNORECASE) or "\x00" in text:
        raise ValueError("unsafe sitemap")
    root=ElementTree.fromstring(text)
    local=lambda tag:tag.rsplit("}",1)[-1]
    if local(root.tag)!="urlset":
        raise ValueError("sitemap index requires separate child subscriptions")
    urls=[]
    scanned=0
    for child in root:
        if local(child.tag)!="url":continue
        scanned+=1
        if scanned>MAX_SITEMAP_URLS:raise ValueError("sitemap entry cap")
        loc=next((x.text for x in child if local(x.tag)=="loc"),None)
        if loc:
            try:urls.append(source_url(loc.strip()))
            except ValueError:continue
    urls=sorted(set(urls))
    if not urls:raise ValueError("empty sitemap")
    # Limit 512 links/page, even worst-case 2K-character URLs fit the
    # normalized import queue's 2 MiB bound. Split further if encoded bytes
    # (Unicode or JSON escaping) exceed the cap.
    def encode(group):
        entries=[{"id":external,"title":title,"links":[{"url":x,"kind":"reference_database","language":"und"} for x in group[i:i+8]]}
                 for i in range(0,len(group),8)]
        raw=json.dumps({"schema":"dragon.game-feed.v1","provider":provider,"entries":entries},ensure_ascii=False).encode()
        if len(raw)<=MAX_FEED_BYTES:return [raw]
        if len(group)<=1:raise ValueError("oversize sitemap locator")
        mid=len(group)//2
        return encode(group[:mid])+encode(group[mid:])
    for i in range(0,len(urls),512):
        yield from encode(urls[i:i+512])


def steam_pages(raw):
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_LARGE_FEED:raise ValueError("catalogue size")
    data=json.loads(raw)
    entries=data.get("applist",{}).get("apps")
    if not isinstance(entries,list) or not 1<=len(entries)<=MAX_STEAM_APPS:raise ValueError("catalogue bounds")
    accepted={}
    for item in entries:
        if not isinstance(item,dict) or type(item.get("appid")) is not int or not 0<item["appid"]<2**63:
            continue
        name=item.get("name")
        if not isinstance(name,str) or not name.strip() or len(name)>256:continue
        accepted[item["appid"]]={"appid":item["appid"],"name":name}
    values=[accepted[k] for k in sorted(accepted)]
    for i in range(0,len(values),500):
        yield json.dumps({"applist":{"apps":values[i:i+500]}},ensure_ascii=False).encode()


def eve_sde_manifest(raw):
    """Read the official SDE latest-build JSONL pointer as discovery metadata.

    The _key=sde record publishes buildNumber in an object. Accept only an
    integral positive build identity, never a URL or path from the response.
    Neither the ZIP nor authenticated ESI routes are automatically fetched.
    """
    if not isinstance(raw,bytes) or not 1<=len(raw)<=64*1024:
        raise ValueError("SDE pointer size")
    rows=raw.splitlines()
    if not 1<=len(rows)<=64:raise ValueError("SDE pointer rows")
    matches=[]
    for line in rows:
        if not line.strip():continue
        row=json.loads(line)
        if not isinstance(row,dict):raise ValueError("SDE record")
        if row.get("_key")=="sde":
            value=row.get("buildNumber")
            if value is None and isinstance(row.get("_value"),dict):
                value=row["_value"].get("buildNumber")
            if type(value) is not int or not 1<=value<2**53:
                raise ValueError("SDE build identity")
            matches.append(value)
    if len(matches)!=1:raise ValueError("SDE build pointer must be unique")
    build=str(matches[0])
    base="https://developers.eveonline.com/static-data/tranquility/"
    entry={"id":"eve-online","title":"EVE Online","stage":"updated","version":build,
        "links":[
            {"url":base+"eve-online-static-data-"+build+"-jsonl.zip","kind":"static_data_export","language":"und"},
            {"url":base+"eve-online-static-data-"+build+"-yaml.zip","kind":"static_data_export","language":"und"},
            {"url":base+"changes/"+build+".jsonl","kind":"static_data_changelog","language":"und"},
            {"url":base+"latest.jsonl","kind":"public_update_feed","language":"und"},
            {"url":base+"schema-changelog.yaml","kind":"static_data_schema","language":"und"}]}
    return json.dumps({"schema":"dragon.game-feed.v1","provider":"developer","entries":[entry]},
                      sort_keys=True,separators=(",",":")).encode()


def partition_feed(row,raw):
    adapter=row["adapter"]
    if adapter=="sitemap":
        return "manifest",sitemap_pages(raw,row["provider"],row["game_external_id"],row["title"]),{}
    if adapter=="steam":return "steam",steam_pages(raw),{}
    if adapter=="eve_sde":return "manifest",iter([eve_sde_manifest(raw)]),{}
    options={"provider":row["provider"],"external_id":row["game_external_id"],"title":row["title"]} if adapter=="rss_atom" else {}
    return adapter,iter([raw]),options


class WorldDiscovery:
    def __init__(self,path):
        self.corpus=GameCorpus(path)
        self.queue=ReleaseQueue(path)

    def _db(self):
        return self.corpus._db()

    def configure(self,scope,*,url,adapter,provider=None,external_id=None,title=None,
                  interval_seconds=3600,grant_seconds=86400,rights_acknowledged=False):
        if rights_acknowledged is not True:
            raise ValueError("explicit public feed rights required")
        if not MIN_INTERVAL<=interval_seconds<=MAX_INTERVAL or type(interval_seconds) is not int:
            raise ValueError("interval")
        if type(grant_seconds) is not int or not MIN_INTERVAL<=grant_seconds<=MAX_GRANT:
            raise ValueError("grant duration")
        url=source_url(url)
        if adapter in {"rss_atom","sitemap"}:
            if provider not in PROVIDERS:
                raise ValueError("unknown provider")
            from core.dragon_game_corpus import key
            external_id=key(external_id)
            title=clean(title,256)
        elif adapter in {"manifest","steam","eve_sde"}:
            if any(x is not None for x in (provider,external_id,title)):
                raise ValueError("unexpected adapter fields")
        else:raise ValueError("adapter")
        if adapter=="eve_sde" and url!="https://developers.eveonline.com/static-data/tranquility/latest.jsonl":
            raise ValueError("EVE SDE subscription requires the exact official public latest-build locator")
        owner=owner_key(scope)
        sid=digest([owner,url,adapter,provider,external_id,title])
        now=int(time.time())
        with self._db() as db:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            try:
                prior=db.execute("SELECT lease_until FROM world_subscriptions WHERE owner=? AND id=?",(owner,sid)).fetchone()
                if prior and prior[0]>now:raise DiscoveryHeld("active subscription lease")
                if not prior and db.execute("SELECT COUNT(*) FROM world_subscriptions WHERE owner=?",(owner,)).fetchone()[0]>=MAX_SUBSCRIPTIONS:
                    raise DiscoveryHeld("subscription quota")
                db.execute("""INSERT INTO world_subscriptions(owner,id,scope_json,url,origin,adapter,provider,game_external_id,title,
                    interval_seconds,expires_at,enabled,due) VALUES(?,?,?,?,?,?,?,?,?,?,?,1,?)
                    ON CONFLICT(owner,id) DO UPDATE SET interval_seconds=excluded.interval_seconds,
                    expires_at=excluded.expires_at,enabled=1,due=excluded.due,failures=0,reason=NULL,lease=NULL,lease_until=0""",
                    (owner,sid,json.dumps(scope,sort_keys=True),url,urlsplit(url).hostname,adapter,provider,external_id,title,interval_seconds,now+grant_seconds,now))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return {"subscription_id":sid,"expires_at":now+grant_seconds,"network_executed":False,"capture_granted":False}

    def revoke(self,scope,sid):
        with self._db() as db:
            db.executescript(SCHEMA)
            row=db.execute("UPDATE world_subscriptions SET enabled=0,expires_at=0,reason='revoked' WHERE owner=? AND id=?",
                (owner_key(scope),_hex(sid)))
        return {"revoked":row.rowcount==1,"inflight_may_finish":True,"capture_granted":False}

    def status(self,scope,*,limit=32,after=None):
        if type(limit) is not int or not 1<=limit<=100:raise ValueError("page")
        after=_hex(after) if after else ""
        with self._db() as db:
            db.executescript(SCHEMA)
            rows=db.execute("""SELECT id,url,adapter,interval_seconds,expires_at,enabled,due,failures,last_batch,reason
                FROM world_subscriptions WHERE owner=? AND id>? ORDER BY id LIMIT ?""",
                (owner_key(scope),after,limit+1)).fetchall()
        return {"subscriptions":[dict(x) for x in rows[:limit]],
            "next_cursor":rows[limit-1]["id"] if len(rows)>limit else None,"capture_granted":False}

    def _claim(self):
        now=int(time.time());lease=uuid4().hex
        with self._db() as db:
            db.executescript(SCHEMA)
            db.execute("BEGIN IMMEDIATE")
            try:
                row=db.execute("""SELECT s.* FROM world_subscriptions s LEFT JOIN world_origin_guard g ON g.origin=s.origin
                    WHERE s.enabled=1 AND s.expires_at>? AND s.due<=? AND s.lease_until<=?
                    AND COALESCE(g.ready,0)<=? AND COALESCE(g.lease_until,0)<=?
                    ORDER BY s.due,s.owner,s.id LIMIT 1""",(now+MAX_LEASE,now,now,now,now)).fetchone()
                if row:
                    db.execute("UPDATE world_subscriptions SET lease=?,lease_until=? WHERE owner=? AND id=?",
                        (lease,now+MAX_LEASE,row["owner"],row["id"]))
                    db.execute("""INSERT INTO world_origin_guard VALUES(?,?,?,?)
                        ON CONFLICT(origin) DO UPDATE SET ready=excluded.ready,lease=excluded.lease,lease_until=excluded.lease_until""",
                        (row["origin"],now+60,lease,now+MAX_LEASE))
                db.execute("COMMIT")
                return {**dict(row),"lease":lease} if row else None
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise

    def _finish(self,row,raw,reason):
        now=int(time.time())
        batch=None; fingerprint=None
        if raw is not None:fingerprint=hashlib.sha256(raw).hexdigest()
        # Hold the same corpus write lock only for permission check and final
        # state; queue admission uses its own connection. Revocation during
        # enqueue can leave metadata candidates, never a capture grant.
        with self._db() as db:
            live=db.execute("""SELECT 1 FROM world_subscriptions WHERE owner=? AND id=? AND enabled=1
                AND expires_at>? AND lease=? AND lease_until>?""",(row["owner"],row["id"],now,row["lease"],now)).fetchone()
        if not live:reason="superseded"
        elif raw is not None and fingerprint!=row["last_digest"]:
            scope=json.loads(row["scope_json"])
            if owner_key(scope)!=row["owner"]:raise DiscoveryHeld("scope mismatch")
            import itertools
            adapter,pages,options=partition_feed(row,raw)
            cursor=row["pending_page"] if row["pending_digest"]==fingerprint else 0
            window=list(itertools.islice(pages,cursor,cursor+PAGES_PER_PULSE+1))
            if not window and cursor==0:raise DiscoveryHeld("feed partition unavailable")
            for page_idx,page in enumerate(window[:PAGES_PER_PULSE],cursor):
                now=int(time.time())
                with self._db() as db:
                    still=db.execute("""SELECT 1 FROM world_subscriptions WHERE owner=? AND id=? AND enabled=1
                        AND expires_at>? AND lease=? AND lease_until>?""",(row["owner"],row["id"],now,row["lease"],now)).fetchone()
                if not still:reason="superseded";break
                try:
                    batch=self.queue.enqueue(scope,raw=page,adapter=adapter,
                        operation=digest([row["id"],fingerprint,page_idx]),**options)["batch_id"]
                except (ValueError,TypeError,KeyError,RuntimeError,sqlite3.Error):
                    reason="import_held";break
                cursor=page_idx+1
                with self._db() as db:
                    changed=db.execute("""UPDATE world_subscriptions SET pending_digest=?,pending_page=?,last_batch=?
                        WHERE owner=? AND id=? AND lease=? AND enabled=1""",(fingerprint,cursor,batch,row["owner"],row["id"],row["lease"]))
                if not changed.rowcount:reason="superseded";break
            if reason is None and len(window)>PAGES_PER_PULSE:reason="partition_pending"
        failures=0 if reason in (None,"partition_pending") else min(20,row["failures"]+1)
        delay=row["interval_seconds"] if reason is None else 60 if reason=="partition_pending" else min(86400,max(900,300*2**min(8,failures)))
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("""UPDATE world_subscriptions SET lease=NULL,lease_until=0,due=?,failures=?,reason=?,
                    last_digest=COALESCE(?,last_digest),last_batch=COALESCE(?,last_batch),
                    pending_digest=CASE WHEN ? IS NULL THEN NULL ELSE pending_digest END,
                    pending_page=CASE WHEN ? IS NULL THEN 0 ELSE pending_page END
                    WHERE owner=? AND id=? AND lease=? AND enabled=1""",
                    (now+delay,failures,reason,fingerprint if reason is None else None,batch,reason,reason,row["owner"],row["id"],row["lease"]))
                db.execute("UPDATE world_origin_guard SET lease=NULL,lease_until=0,ready=? WHERE origin=? AND lease=?",
                    (now+60,row["origin"],row["lease"]))
                db.execute("COMMIT")
            except BaseException:
                if db.in_transaction:db.execute("ROLLBACK")
                raise
        return reason or "accepted"

    def pulse(self,*,fetcher=None):
        if os.getenv("SKL_DRAGON_WORLD_DISCOVERY")!="1":
            return {"enabled":False,"network_executed":False}
        row=self._claim()
        if row is None:return {"enabled":True,"outcome":"idle","network_executed":False}
        try:
            raw=fetch_public_feed(row["url"],fetcher=fetcher,max_bytes=MAX_LARGE_FEED if row["adapter"] in {"steam","sitemap"} else 64*1024 if row["adapter"]=="eve_sde" else MAX_FEED_BYTES)
        except Exception:
            return {"enabled":True,"outcome":self._finish(row,None,"fetch_held"),"network_attempted":True}
        try:
            outcome=self._finish(row,raw,None)
        except (ValueError,TypeError,KeyError,RuntimeError,sqlite3.Error):
            outcome=self._finish(row,None,"import_held")
        return {"enabled":True,"outcome":outcome,"network_attempted":True,"capture_granted":False}
