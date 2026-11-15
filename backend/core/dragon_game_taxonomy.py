"""Canonical game-source taxonomy for coverage, cadence and discovery.

A taxonomy entry is a routing label, never a determination that a source is
public, accurate, copyrighted legitimately, safe to fetch or licensed to train.
"""
from __future__ import annotations

from dataclasses import dataclass

HOUR=3600
DAY=24*HOUR
WEEK=7*DAY

@dataclass(frozen=True)
class SourceClass:
    family: str
    interval: int
    priority: int
    historical_value: int

# Existing 15 keys remain stable across persisted catalogues. Additional classes
# avoid collapsing platform, technical, community and preservation materials.
_SPECS={
    "official_wiki":("knowledge",DAY,75,85),
    "community_wiki":("knowledge",DAY,65,85),
    "reference_database":("knowledge",DAY,60,80),
    "lore_database":("knowledge",WEEK,35,80),
    "item_database":("knowledge",DAY,55,85),
    "quest_database":("knowledge",DAY,50,85),
    "map_database":("knowledge",DAY,55,80),
    "achievement_database":("knowledge",DAY,45,70),
    "strategy_database":("knowledge",DAY,50,75),
    "faq":("knowledge",WEEK,30,70),
    "storefront":("market",6*HOUR,80,70),
    "platform_catalogue":("market",6*HOUR,80,70),
    "regional_catalogue":("market",DAY,60,75),
    "physical_release":("market",WEEK,40,85),
    "subscription_catalogue":("market",DAY,65,65),
    "delisting_notice":("market",HOUR,95,95),
    "release_feed":("lifecycle",HOUR,100,90),
    "patch_notes":("lifecycle",HOUR,100,95),
    "developer_blog":("lifecycle",6*HOUR,80,80),
    "release_calendar":("lifecycle",HOUR,95,80),
    "announcement":("lifecycle",HOUR,90,85),
    "roadmap":("lifecycle",6*HOUR,75,90),
    "changelog":("lifecycle",HOUR,90,95),
    "hotfix":("lifecycle",HOUR,100,95),
    "maintenance_notice":("lifecycle",HOUR,90,65),
    "server_status":("lifecycle",HOUR,75,30),
    "early_access":("lifecycle",HOUR,95,90),
    "beta_program":("lifecycle",6*HOUR,85,85),
    "demo_catalogue":("lifecycle",6*HOUR,80,85),
    "expansion_catalogue":("lifecycle",6*HOUR,85,85),
    "seasonal_event":("lifecycle",HOUR,90,75),
    "manual":("technical",WEEK,40,95),
    "technical_reference":("technical",WEEK,55,95),
    "engine_docs":("technical",WEEK,60,95),
    "sdk_docs":("technical",DAY,65,95),
    "api_reference":("technical",DAY,65,90),
    "editor_docs":("technical",WEEK,55,90),
    "scripting_reference":("technical",DAY,65,95),
    "file_format":("technical",WEEK,50,95),
    "compatibility_database":("technical",DAY,70,85),
    "hardware_requirements":("technical",DAY,50,75),
    "benchmark":("technical",DAY,40,65),
    "controller_support":("technical",WEEK,40,80),
    "troubleshooting":("technical",DAY,55,75),
    "security_advisory":("technical",HOUR,100,90),
    "bug_tracker":("technical",6*HOUR,75,80),
    "source_repository":("technical",DAY,60,95),
    "build_documentation":("technical",DAY,65,95),
    "mod_catalogue":("creation",DAY,65,80),
    "mod_documentation":("creation",DAY,65,85),
    "mod_release":("creation",6*HOUR,80,85),
    "level_editor":("creation",WEEK,50,85),
    "mapping_guide":("creation",WEEK,40,80),
    "asset_catalogue":("creation",DAY,45,75),
    "community_workshop":("creation",DAY,60,80),
    "design_reference":("creation",WEEK,45,85),
    "postmortem":("creation",WEEK,40,95),
    "developer_talk":("creation",WEEK,40,90),
    "community_guide":("community",DAY,55,75),
    "community_forum":("community",DAY,40,65),
    "walkthrough":("community",WEEK,45,85),
    "speedrun_database":("community",DAY,55,85),
    "challenge_guide":("community",DAY,45,75),
    "trading_reference":("community",6*HOUR,45,45),
    "community_event":("community",6*HOUR,70,65),
    "esports":("competition",6*HOUR,65,70),
    "tournament_schedule":("competition",HOUR,80,70),
    "ruleset":("competition",DAY,65,90),
    "competitive_stats":("competition",DAY,55,65),
    "accessibility":("inclusion",WEEK,65,90),
    "localization":("inclusion",DAY,55,90),
    "language_patch":("inclusion",DAY,55,80),
    "input_accessibility":("inclusion",WEEK,60,90),
    "content_rating":("inclusion",WEEK,45,80),
    "preservation":("history",WEEK,60,100),
    "historical_catalogue":("history",WEEK,50,100),
    "prototype_history":("history",WEEK,40,100),
    "version_history":("history",DAY,70,100),
    "archived_manual":("history",WEEK,50,100),
    "hardware_history":("history",WEEK,40,100),
    "development_history":("history",WEEK,40,100),
    "rights_statement":("governance",DAY,90,100),
    "license_notice":("governance",DAY,95,100),
    "source_policy":("governance",DAY,95,100),
    "official_support":("governance",DAY,75,80),
}
SOURCE_CLASSES={name:SourceClass(*fields) for name,fields in _SPECS.items()}
KINDS={name:spec.interval for name,spec in SOURCE_CLASSES.items()}
FAMILIES=frozenset(spec.family for spec in SOURCE_CLASSES.values())


def source_class(kind):
    try:
        return SOURCE_CLASSES[kind]
    except (TypeError,KeyError) as exc:
        raise ValueError("unknown source class") from exc


def cadence(kind,stage):
    spec=source_class(kind)
    interval=spec.interval
    if stage in {"announced","early_access","updated"}:
        interval=min(6*HOUR,interval)
    if stage=="delisted":
        interval=min(interval,DAY)
    return interval


def priority(kind,stage):
    spec=source_class(kind)
    return min(100,spec.priority+{"announced":10,"early_access":8,"updated":8,
                                 "delisted":15}.get(stage,0))


def public_taxonomy():
    return {"source_classes":[{"kind":name,"family":spec.family,
                "default_review_seconds":spec.interval,"priority":spec.priority,
                "historical_value":spec.historical_value}
                for name,spec in sorted(SOURCE_CLASSES.items())],
            "families":sorted(FAMILIES),"network_authority":False,
            "source_use_authority":False,"training_allowed":False}
