"""Bounded opt-in public game-title announcement monitor.

A trusted curator supplies integer Steam app IDs. Only the fixed official
Steam News JSON endpoint is requested, over HTTPS with no redirects/proxies.
The fetcher extracts IDs, source URLs and hashes, NOT third-party prose.
Nothing fetched is accepted as a reviewed feature claim or model training.
Official news absence/fetch errors never imply a competitive weakness.

The per-run snapshot can be archived as a CI artifact. Sources stay
UNREVIEWED until a separate authenticated operator supplies PublicSignal
features and evidence receipts to rival_convergence_observatory.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime,timezone
from hashlib import sha256
import json
import re
from urllib.parse import urlsplit
from urllib.request import build_opener, ProxyHandler, HTTPSHandler, HTTPRedirectHandler, Request

from .contracts import canonical_digest,canonical_json
from .rival_convergence_observatory import (
    CompetitorTitle, PublicSignal, CompetitiveError,
)

_MAX_RESPONSE=512_000
_MAX_TITLES=64
_MAX_PER_TITLE=12
_STEAM_API="https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/"
_NEWS_HOSTS=frozenset({"steamcommunity.com","store.steampowered.com"})


class MonitoringError(CompetitiveError):
    pass


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        raise MonitoringError("external monitoring redirects are forbidden")


def _safe_news_url(raw):
    if not isinstance(raw,str) or len(raw)>1024 or not raw.startswith("https://"):
        raise MonitoringError("Steam news must carry bounded HTTPS public URL")
    p=urlsplit(raw)
    if (p.hostname not in _NEWS_HOSTS or p.port not in (None,443)
            or p.username is not None or p.password is not None or p.fragment):
        raise MonitoringError("untrusted Steam news source host or credentials")
    return raw


def _utc(timestamp):
    if type(timestamp) is not int or not 0<=timestamp<=4_102_444_800:
        raise MonitoringError("invalid bounded Steam publication epoch")
    return datetime.fromtimestamp(timestamp,tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True,slots=True)
class NewsBatch:
    observed_at: str
    title_ids: tuple[str,...]
    signals: tuple[PublicSignal,...]
    errors: tuple[str,...]

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(
            schema="skeleton.game_builder.public_competitor_snapshot.v1",
            observed_at=self.observed_at,title_ids=list(self.title_ids),
            signals=[s.payload() for s in self.signals],errors=list(self.errors),
            only_whitelisted_steam_news_api_polled=True,
            no_news_content_copied=True,no_competitor_game_artifacts_scraped=True,
            no_source_automatically_marked_reviewed=True,
            no_competitor_feature_asserted_without_independent_review=True,
            no_automatic_enemy_label_or_model_training=True,
            source_rights_recheck_required_for_later_wisdom_use=True,
        )


def _parse_news(title: CompetitorTitle,blob:bytes,*,observed_at:str)->tuple[PublicSignal,...]:
    if len(blob)>_MAX_RESPONSE:
        raise MonitoringError("Steam news JSON exceeds bounded input")
    try:
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise MonitoringError("ambiguous duplicate Steam JSON key")
                result[key]=value
            return result
        root=json.loads(blob.decode("utf-8","strict"),object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(
                            MonitoringError("nonfinite Steam data")))
        news=root["appnews"]
        if (type(news) is not dict or news.get("appid")!=title.steam_app_id
                or type(news.get("newsitems")) is not list
                or len(news["newsitems"])>_MAX_PER_TITLE):
            raise MonitoringError("Steam reply mismatched app ID or exceeds item budget")
    except (ValueError,TypeError,KeyError,UnicodeDecodeError) as exc:
        raise MonitoringError("Steam news JSON invalid or ambiguous") from exc
    seen=set()
    signals=[]
    for item in news["newsitems"]:
        if not isinstance(item,dict):
            raise MonitoringError("Steam item must be structured")
        news_id=item.get("gid")
        if not isinstance(news_id,str) or not re.fullmatch(r"[0-9]{1,24}",news_id):
            raise MonitoringError("Steam article GID must be bounded digits")
        if news_id in seen:
            raise MonitoringError("Steam replay returned duplicate articles")
        seen.add(news_id)
        published=_utc(item.get("date"))
        if published>observed_at:
            raise MonitoringError("future Steam news cannot count as observation")
        source=_safe_news_url(item.get("url"))
        # Only stable metadata, not headline, descriptions, reviews, screenshots,
        # copyrighted expression, or potentially prompt-injecting text.
        evidence=canonical_digest(dict(
            app_id=title.steam_app_id,gid=news_id,
            date=item["date"],source_url=source))
        signals.append(PublicSignal(
            title_id=title.title_id,signal_id="steamnews-"+news_id,
            source_url=source,source_digest=evidence,
            published_at=published,observed_at=observed_at,
            source_group="steamnews-"+title.title_id,
            signal_kind="official_announcement",
            reviewed_feature_ids=(),
            review_evidence_digest=None,reviewer_id=None,
        ))
    return tuple(sorted(signals,key=lambda s:s.signal_id))


def poll_public_steam_titles(
    titles: tuple[CompetitorTitle,...],*,observed_at: str,
    authorized: bool,fetcher=None,
)->NewsBatch:
    if not authorized:
        raise PermissionError("live rival-monitor access needs an explicit opt-in operator")
    if (type(titles) is not tuple or len(titles)>_MAX_TITLES
            or any(not isinstance(t,CompetitorTitle) for t in titles)
            or len({t.title_id for t in titles})!=len(titles)):
        raise MonitoringError("bounded unique curated title watchlist required")
    # The same Steam app must not masquerade as two independent titles.
    app_ids=[t.steam_app_id for t in titles]
    if any(i is None for i in app_ids) or len(set(app_ids))!=len(app_ids):
        raise MonitoringError("valid distinct official Steam app IDs required")
    # Prevent time drift, spoofed date formats and publications from future.
    try:
        dt=datetime.strptime(observed_at,"%Y-%m-%dT%H:%M:%SZ")
        if dt.strftime("%Y-%m-%dT%H:%M:%SZ")!=observed_at:
            raise ValueError
    except (ValueError,TypeError) as exc:
        raise MonitoringError("canonical UTC monitor time required") from exc
    if fetcher is None:
        opener=build_opener(ProxyHandler({}),HTTPSHandler(),_NoRedirect())
        def fetcher(url):
            request=Request(url,headers={"Accept":"application/json",
                                       "User-Agent":"Skeleton-Game-Rival-Watch/1.0"})
            with opener.open(request,timeout=8) as response:
                if response.status!=200:
                    raise MonitoringError("non-200 official game news response")
                length=response.headers.get("Content-Length")
                if length is not None and int(length)>_MAX_RESPONSE:
                    raise MonitoringError("official news response too large")
                return response.read(_MAX_RESPONSE+1)
    signals=[]
    errors=[]
    for title in sorted(titles,key=lambda t:t.title_id):
        url=f"{_STEAM_API}?appid={title.steam_app_id}&count={_MAX_PER_TITLE}&maxlength=0&format=json"
        try:
            response=fetcher(url)
            if not isinstance(response,bytes):
                raise MonitoringError("trusted public feed adapter must return bytes")
            signals.extend(_parse_news(title,response,observed_at=observed_at))
        except (MonitoringError,OSError,TimeoutError,ValueError,KeyError) as exc:
            errors.append(f"{title.title_id}:{type(exc).__name__}")
            # All-or-nothing per rival: no incomplete confidence from a failed
            # source read; other titles are still independently reportable.
    return NewsBatch(observed_at,tuple(sorted(t.title_id for t in titles)),
                     tuple(sorted(signals,key=lambda s:(s.title_id,s.signal_id))),
                     tuple(sorted(errors)))


__all__=["MonitoringError","NewsBatch","poll_public_steam_titles"]
