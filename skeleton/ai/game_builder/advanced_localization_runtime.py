"""Original multilingual text catalogue, pluralization and fallback reference.

Actually resolves authored strings, per-locale plural variants, RTL direction
and finite fallback behavior. Four explicitly supported locales do not
magically implement every requested language or constitute certified
translation quality. No model or network translations are fabricated.
"""
from __future__ import annotations

from copy import deepcopy

ACTIONS = ("inspect", "lang:en", "lang:fr", "lang:ar", "lang:ja",
           "show:welcome", "show:warning", "count:0", "count:1",
           "count:2", "count:5", "audit", "finish")
_LOCALES = ("en", "fr", "ar", "ja")
_KEYS = ("welcome", "warning", "items")
_TEXT = {
    "en": {"welcome":"Welcome to the original world.",
           "warning":"Proceed with care.",
           "items":{"one":"{n} item", "other":"{n} items"}},
    "fr": {"welcome":"Bienvenue dans le monde original.",
           "warning":"Avancez avec prudence.",
           "items":{"one":"{n} objet", "other":"{n} objets"}},
    "ar": {"welcome":"مرحبا في العالم الأصلي.",
           "warning":"تابع بحذر.",
           "items":{"zero":"لا عناصر", "one":"عنصر واحد",
                    "two":"عنصران", "few":"{n} عناصر",
                    "many":"{n} عنصرا", "other":"{n} عنصر"}},
    "ja": {"welcome":"オリジナルの世界へようこそ。",
           "warning":"注意して進んでください。",
           "items":{"other":"{n} 個"}},
}


class LocalizationActionError(ValueError):
    """Unknown source locale, missing protected translation or invalid plural."""


def _int(v, lo, hi, name):
    if type(v) is not int or not lo <= v <= hi:
        raise LocalizationActionError("invalid localized " + name)
    return v


def default_layout(config, seed):
    _int(seed, 0, 2**31-1, "seed")
    count = min(len(_LOCALES), config["language_count"])
    count_keys = min(len(_KEYS), config["text_keys"])
    keys = list(_KEYS[:count_keys])
    return {
        "title": "Original Message Catalogue " + str(seed % 10000),
        "source_locale": "en",
        "locales": [
            {"id": locale,
             "strings": {
                 key: ("Items" if key == "items" and not config["plural_rules"]
                       else deepcopy(_TEXT[locale][key]))
                 for key in keys
             }}
            for locale in _LOCALES[:count]
        ],
        "required_keys": keys,
    }


def _text(value):
    return (type(value) is str and 1 <= len(value) <= 160
            and all(ord(character) >= 32 for character in value)
            and value.count("{n}") <= 1
            and "{" not in value.replace("{n}","")
            and "}" not in value.replace("{n}",""))


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "title", "source_locale", "locales", "required_keys",
    }:
        raise LocalizationActionError("exact original localization source required")
    if not _text(layout["title"]) or layout["source_locale"] != "en":
        raise LocalizationActionError("reviewed source language and title required")
    locales = layout["locales"]
    keys = layout["required_keys"]
    if (type(keys) is not list or not 1 <= len(keys) <= min(3,config["text_keys"])
            or len(keys) != len(set(keys)) or any(key not in _KEYS for key in keys)):
        raise LocalizationActionError("unsupported original source text key")
    if (type(locales) is not list or not 1 <= len(locales) <= min(4,config["language_count"])
            or type(locales[0]) is not dict or locales[0].get("id") != "en"):
        raise LocalizationActionError("source locale must be the first valid real text catalogue")
    cleaned = []
    seen = set()
    for entry in locales:
        if type(entry) is not dict or set(entry) != {"id", "strings"}:
            raise LocalizationActionError("localized authored catalogue fields mismatch")
        locale = entry["id"]
        if locale not in _LOCALES or locale in seen:
            raise LocalizationActionError("unknown or duplicate source language")
        seen.add(locale)
        strings = entry["strings"]
        if type(strings) is not dict or not set(strings).issubset(keys):
            raise LocalizationActionError("unknown localized string key")
        clean = {}
        for key,value in strings.items():
            if key == "items" and config["plural_rules"]:
                allowed = ("zero", "one", "two", "few", "many", "other")
                if (type(value) is not dict or "other" not in value or
                        not set(value).issubset(allowed) or not all(
                            _text(template) for template in value.values())):
                    raise LocalizationActionError("plural source must have safe bounded forms")
                clean[key] = dict(value)
            else:
                if not _text(value):
                    raise LocalizationActionError("unsafe or missing original localized prose")
                clean[key] = value
        cleaned.append({"id":locale, "strings": clean})
    first = cleaned[0]["strings"]
    if set(first) != set(keys):
        raise LocalizationActionError("original source language must cover all authored keys")
    return {"title": layout["title"], "source_locale":"en",
            "locales":cleaned,"required_keys":list(keys)}


def start(config, seed):
    layout = normalize_layout(config, default_layout(config, seed))
    return {
        "title":layout["title"],"source_locale":layout["source_locale"],
        "locales":deepcopy(layout["locales"]),"required_keys":list(layout["required_keys"]),
        "language":"en","text_direction":"ltr","rendered":[],
        "fallback_count":0,"resolved":0,"missing":0,
        "score":0,"turn":0,"finished":False,"failed":False,"events":[],
        "machine_translation_produced":False,
    }


def apply_scene(state, config, layout):
    if state["turn"]:
        raise LocalizationActionError("cannot switch authored language pack during live message custody")
    source=normalize_layout(config,layout)
    state["title"]=source["title"]
    state["source_locale"]=source["source_locale"]
    state["locales"]=deepcopy(source["locales"])
    state["required_keys"]=list(source["required_keys"])


def _plural(locale, n):
    if locale == "ar":
        if n == 0: return "zero"
        if n == 1: return "one"
        if n == 2: return "two"
        mod = n % 100
        if 3 <= mod <= 10: return "few"
        if 11 <= mod <= 99: return "many"
        return "other"
    if locale == "fr":
        return "one" if n in (0,1) else "other"
    if locale == "en":
        return "one" if n == 1 else "other"
    return "other"


def _resolve(state, config, key, n=None):
    if key not in state["required_keys"]:
        raise LocalizationActionError("string key not declared in current source")
    lang = next((x for x in state["locales"] if x["id"]==state["language"]),None)
    source = state["locales"][0]
    if lang is None:
        raise LocalizationActionError("unregistered locale cannot be rendered")
    value = lang["strings"].get(key)
    fallback = False
    if value is None:
        if config["fallback"] == "block_release":
            raise LocalizationActionError("required translation missing: release must block")
        if config["fallback"] == "display_key":
            value = key
        else:
            value = source["strings"][key]
        fallback = True
    if isinstance(value, dict):
        label = _plural(state["language"] if not fallback else "en", n)
        template = value.get(label,value["other"])
        value = template.replace("{n}",str(n))
    state["fallback_count"] += int(fallback)
    state["resolved"] += 1
    state["rendered"].append({
        "locale":state["language"],"key":key,"text":value,
        "fallback":fallback,"direction":state["text_direction"],
        "plural_count":n,
    })
    state["rendered"]=state["rendered"][-24:]
    state["score"] += 1 if fallback else 2


def step(state,config,action):
    if action not in ACTIONS or state["finished"] or state["failed"]:
        raise LocalizationActionError("undeclared original language operation")
    events=[]
    if action.startswith("lang:"):
        target=action[5:]
        if target not in {entry["id"] for entry in state["locales"]}:
            raise LocalizationActionError("requested language lacks a reviewed source pack")
        state["language"]=target
        state["text_direction"]="rtl" if config["rtl_layout"] and target=="ar" else "ltr"
        events.append("authored_language_and_direction_changed")
    elif action.startswith("show:"):
        _resolve(state,config,action.split(":")[1])
        events.append("actual_source_string_resolved")
    elif action.startswith("count:"):
        if not config["plural_rules"]:
            raise LocalizationActionError("source disabled plural rule interpreter")
        _resolve(state,config,"items",int(action.split(":")[1]))
        events.append("locale_appropriate_plural_variant_evaluated")
    elif action=="audit":
        if state["resolved"]==0:
            raise LocalizationActionError("catalogue audit needs actual resolved text")
        lang=next(e for e in state["locales"] if e["id"]==state["language"])
        state["missing"]=len(set(state["required_keys"])-set(lang["strings"]))
        events.append("real_source_catalogue_coverage_computed")
    elif action=="finish":
        if not state["resolved"]:
            raise LocalizationActionError("localization trial must resolve real original text")
        if config["fallback"]=="block_release" and state["missing"]:
            raise LocalizationActionError("untranslated keys block release")
        state["finished"]=True
        events.append("earned_original_translation_lookup_trial_complete")
    else:
        events.append("original_locale_strings_inspected")
    state["turn"]+=1
    state["events"]=events
    return events


__all__=["ACTIONS","LocalizationActionError","default_layout",
         "normalize_layout","start","apply_scene","step"]
