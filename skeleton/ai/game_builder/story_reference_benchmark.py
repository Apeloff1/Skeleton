"""Comparable book/film/game story references: commercial reach AND criticism.

Never compare ticket admissions, trade-print copies, viewers or game units.
This is a read-only, operator-supplied evidence auditor, not a sales oracle.
"""
from __future__ import annotations

from datetime import date
from math import ceil
import re
from typing import Any
from urllib.parse import urlsplit

SCHEMA="skeleton.jeeves.story_media_benchmark.v1"
MIN_COHORT=5
MIN_CRITIC_SCORE=85
_MEDIA = {
    "novel": ("audited_print_copies", 5),
    "film": ("ticket_admissions", 15),
    "interactive_game": ("reported_units", 7),
    "television": ("audited_viewer_hours", 15),
}


class StoryMarketError(ValueError):
    pass


def _ident(x:Any,name:str)->str:
    if not isinstance(x,str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,75}",x) is None:
        raise StoryMarketError("invalid "+name)
    return x


def _source(src:Any, label:str, *, release_year:int)->dict[str,str]:
    if not isinstance(src,dict) or set(src)!={"url","issuer","published","kind"}:
        raise StoryMarketError("missing "+label+" market source")
    kind=src["kind"]
    if kind not in ("publisher_or_studio_disclosure","audited_industry_measurement",
                     "independent_critic_aggregate","professional_review_archive"):
        raise StoryMarketError("unsupported source evidence category")
    if label=="commercial" and kind not in (
        "publisher_or_studio_disclosure","audited_industry_measurement"
    ):
        raise StoryMarketError("commercial reach evidence must be reported or audited")
    if label=="criticism" and kind not in (
        "independent_critic_aggregate","professional_review_archive"
    ):
        raise StoryMarketError("critic evidence must be independently issued")
    url=src["url"]
    if not isinstance(url,str) or len(url)>1024:
        raise StoryMarketError("invalid source URL")
    try:
        p=urlsplit(url)
        if p.scheme!="https" or not p.hostname or p.username or p.password or p.fragment:
            raise StoryMarketError("only public HTTPS source citations are accepted")
        if p.hostname.lower() in ("localhost","metadata.google.internal"):
            raise StoryMarketError("local or internal evidence citations forbidden")
    except ValueError as exc:
        raise StoryMarketError("malformed source URL") from exc
    published=src["published"]
    try:
        checked=date.fromisoformat(published)
    except (TypeError,ValueError) as exc:
        raise StoryMarketError("invalid source publication date") from exc
    if checked.year<release_year or checked>date.today():
        raise StoryMarketError("source predates work or is future dated")
    return {"url":url,"issuer":_ident(src["issuer"],"source issuer"),
            "published":published,"kind":kind}


def audit_story_references(payload:Any)->dict[str,Any]:
    if not isinstance(payload,dict) or set(payload)!={"schema","cohorts"} or payload["schema"]!=SCHEMA:
        raise StoryMarketError("unrecognized medium-specific reference evidence schema")
    cohorts=payload["cohorts"]
    if not isinstance(cohorts,list) or not 1<=len(cohorts)<=80:
        raise StoryMarketError("expected 1..80 bounded reference cohorts")
    names=set()
    reviews=[]
    for cohort in cohorts:
        fields={"medium","genre","period","territory","commercial_unit","works"}
        if not isinstance(cohort,dict) or set(cohort)!=fields:
            raise StoryMarketError("incomplete source reference cohort")
        medium=cohort["medium"]
        if medium not in _MEDIA:
            raise StoryMarketError("cannot compare unsupported literary/cinematic mediums")
        unit,min_reviews=_MEDIA[medium]
        if cohort["commercial_unit"]!=unit:
            raise StoryMarketError("uncomparable commercial unit for medium")
        genre,territory=_ident(cohort["genre"],"genre"),_ident(cohort["territory"],"territory")
        period=cohort["period"]
        if not isinstance(period,str) or re.fullmatch(r"(?:19|20)[0-9]{2}-(?:19|20)[0-9]{2}",period) is None:
            raise StoryMarketError("invalid release period")
        lo,hi=map(int,period.split("-"))
        if lo>hi or hi-lo>9:
            raise StoryMarketError("period spans too many years")
        key=tuple(s.casefold() for s in (medium,genre,period,territory))
        if key in names:
            raise StoryMarketError("duplicate exact reference cohort")
        names.add(key)
        works=cohort["works"]
        if not isinstance(works,list) or not MIN_COHORT<=len(works)<=512:
            raise StoryMarketError("minimum 5 same-medium, same-period works required")
        ids=set()
        records=[]
        for work in works:
            if not isinstance(work,dict) or set(work)!={
                "id","release_year","commercial_quantity","professional_score",
                "professional_reviews","commercial_source","review_source"
            }:
                raise StoryMarketError("incomplete original reference evidence")
            identity=_ident(work["id"],"reference identity")
            if identity.casefold() in ids:
                raise StoryMarketError("duplicate work in reference cohort")
            ids.add(identity.casefold())
            year=work["release_year"]
            reach=work["commercial_quantity"]
            score=work["professional_score"]
            count=work["professional_reviews"]
            if (type(year)is not int or not lo<=year<=hi or type(reach)is not int or reach<=0
                or type(score)is not int or not 0<=score<=100 or type(count)is not int
                or not min_reviews<=count<=100000):
                raise StoryMarketError("invalid comparable commercial/critic measurements")
            commercial=_source(work["commercial_source"],"commercial",release_year=year)
            critical=_source(work["review_source"],"criticism",release_year=year)
            if (commercial["url"]==critical["url"] or
                commercial["issuer"].casefold()==critical["issuer"].casefold()):
                raise StoryMarketError("commercial and criticism evidence require independent sources")
            records.append((identity,reach,score,count,commercial,critical))
        if len({r[1] for r in records})<3 or len({r[2] for r in records})<3:
            raise StoryMarketError("cohort lacks discriminating commercial/quality evidence")
        cutoff=ceil(len(records)*0.25)
        leaders=[]
        for row in records:
            reach_rank=1+sum(other[1]>row[1] for other in records)
            review_rank=1+sum(other[2]>row[2] for other in records)
            if reach_rank<=cutoff and review_rank<=cutoff and row[2]>=MIN_CRITIC_SCORE:
                leaders.append({
                    "id":row[0],"commercial_quantity":row[1],
                    "commercial_rank":reach_rank,"professional_score":row[2],
                    "professional_rank":review_rank,
                    "professional_reviews":row[3],
                    "commercial_source":row[4],"review_source":row[5],
                })
        reviews.append({
            "medium":medium,"genre":genre,"period":period,"territory":territory,
            "commercial_unit":unit,"cohort_size":len(records),
            "minimum_professional_reviews":min_reviews,
            "dual_top_quartile_rank_cutoff":cutoff,
            "qualified_reference_count":len(leaders),
            "top_tier_inspiration_available":bool(leaders),
            "leaders":sorted(leaders,key=lambda x:(
                x["commercial_rank"]+x["professional_rank"],x["id"])),
            "independent_market_and_critic_source_values_verified":False,
        })
    return {
        "ok":True,"action":"direction-benchmark","schema":SCHEMA,
        "cohorts":reviews,"declared_cohorts":len(reviews),
        "qualified_cohorts":sum(r["top_tier_inspiration_available"] for r in reviews),
        "medium_mixing_permitted":False,
        "operator_supplied_sales_and_review_values":True,
        "external_sources_independently_fetched":False,
        "professional_story_quality_proven":False,
        "full_game_story_complete":False,
    }
