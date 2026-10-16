"""Evidence-gated era/console/genre/period benchmarks for Jeeves game authoring.

A bounded local evidence consumer under the developer CLI: never a crawler,
license evaluator, ranking authority or renderer. Operator-provided facts remain
unverified until independently audited.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import date
import math
from pathlib import Path, PurePosixPath
import re
import struct
import zlib
from typing import Any
from urllib.parse import urlsplit

SCHEMA = "skeleton.game.market_quality.v1"
ASSET_SCHEMA = "skeleton.game.asset_quality_receipt.v1"
MAX_DATA_BYTES = 2 * 1024 * 1024
MAX_ASSET_EVIDENCE_BYTES = 64 * 1024
MAX_COHORTS = 80
MAX_TITLES = 512
MIN_COHORT = 5
MIN_CRITIC_REVIEWS = 7
MIN_SCORE = 85
TOP_PERCENT = 0.25
_HEX = re.compile(r"^[0-9a-f]{64}$")
_IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")
_PERIOD = re.compile(r"^([12][0-9]{3})-([12][0-9]{3})$")
_FILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SOURCES = frozenset({"publisher_filing", "audited_sales", "industry_research",
                      "critic_aggregate", "review_archive", "independent_review"})
_SALES = {"publisher_filing", "audited_sales", "industry_research"}
_RATINGS = {"critic_aggregate", "review_archive", "independent_review"}
_RUBRICS = {
    "asset": ("silhouette", "readability", "era_fidelity", "material_detail",
              "art_direction", "accessibility", "originality"),
    "animation": ("silhouette", "timing", "motion_clarity", "transitions",
                  "era_fidelity", "accessibility", "originality"),
    "cutscene": ("composition", "camera_continuity", "timing", "lighting",
                 "story_clarity", "era_fidelity", "originality"),
    "music": ("motif", "mix_clarity", "dynamic_range", "loop_quality",
              "era_fidelity", "originality", "accessibility"),
}


class QualityError(ValueError):
    """Insufficient or incompatible quality evidence: fail closed."""


def _error(msg: str) -> None:
    raise QualityError(msg)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj = {}
    for key, value in pairs:
        if key in obj:
            _error("duplicate field in quality evidence JSON")
        obj[key] = value
    return obj


def _read(root: Path, relative: str, maximum: int) -> tuple[dict[str, Any], str]:
    from skeleton.developer.game_cli import _load
    _load(root)
    if not isinstance(relative, str) or not relative or "\\" in relative:
        _error("unsafe quality evidence path")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(p in {"", ".", ".."} for p in relative.split("/")):
        _error("unsafe quality evidence path")
    if path.parts[0] != "design" or len(path.parts) != 2 or path.suffix != ".json":
        _error("evidence file must be a direct JSON child of project design/")
    selected = root
    for component in path.parts:
        selected = selected / component
        if selected.is_symlink():
            _error("symlink in quality evidence path")
    if not selected.is_file() or selected.stat().st_size > maximum:
        _error("quality evidence missing, nonregular or oversized")
    try:
        content = selected.read_bytes()
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=lambda x: _error("invalid numeric constant"))
    except (UnicodeError, ValueError) as exc:
        raise QualityError("invalid quality evidence JSON") from exc
    if not isinstance(value, dict):
        _error("quality evidence must be a JSON object")
    return value, hashlib.sha256(content).hexdigest()


def _ident(value: object, name: str) -> str:
    if not isinstance(value, str) or _IDENT.fullmatch(value) is None:
        _error(f"invalid {name}")
    return value


def _natural(value: Any, name: str, *, minimum: int = 0, maximum: int = 10**12) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        _error(f"invalid {name}")
    return value


def _period(value: Any) -> tuple[int, int]:
    if not isinstance(value, str):
        _error("invalid release period")
    m = _PERIOD.fullmatch(value)
    if not m:
        _error("period must use YYYY-YYYY")
    lo, hi = (int(x) for x in m.groups())
    if lo > hi or hi - lo > 9 or lo < 1970 or hi > 2100:
        _error("release period must cover 1-10 consecutive years")
    return lo, hi


def _source(src: Any, role: str) -> dict[str, str]:
    if not isinstance(src, dict) or set(src) != {"url", "issuer", "kind", "published"}:
        _error(f"invalid {role} evidence citation")
    kind = src["kind"]
    if not isinstance(kind, str) or kind not in (_SALES if role == "sales" else _RATINGS):
        _error(f"unsupported {role} evidence authority")
    issuer = _ident(src["issuer"], f"{role} evidence issuer")
    uri = src["url"]
    if not isinstance(uri, str) or len(uri) > 1024:
        _error("evidence URL invalid")
    try:
        parts = urlsplit(uri)
        if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
            _error("evidence URL must be public HTTPS without credentials or fragment")
        # A URL-shaped string is never proof that a citation was fetched.
        # Reject local, private, numeric and internal origins even if someone
        # presents them as a purportedly independent market publication.
        host = parts.hostname.lower()
        if host.endswith(".") or "%" in host or "\\" in host:
            _error("non-public or ambiguous evidence hostname")
        if parts.port is not None and not 1 <= parts.port <= 65535:
            _error("invalid evidence port")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            _error("literal IP addresses cannot qualify as public citations")
        if (not re.fullmatch(r"[a-z0-9-]+(?:\\.[a-z0-9-]+)+", host)
                or any(label.startswith("-") or label.endswith("-")
                       for label in host.split("."))
                or re.fullmatch(r"[a-z]{2,63}|xn--[a-z0-9-]+", host.rsplit(".", 1)[-1]) is None
                or host.endswith((".localhost", ".local", ".localdomain",
                                  ".internal", ".lan", ".home.arpa",
                                  ".onion", ".invalid", ".test", ".example"))
                or host in {"localhost", "localdomain"}
                or all(part.isdigit() for part in host.split("."))):
            _error("local, reserved or malformed evidence hostname")
    except ValueError as exc:
        raise QualityError("invalid evidence URL") from exc
    published = src["published"]
    if not isinstance(published, str) or re.fullmatch(r"(?:19|20)[0-9]{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])", published) is None:
        _error("evidence published date must be ISO YYYY-MM-DD (2000+)")
    try:
        observed = date.fromisoformat(published)
    except ValueError as exc:
        raise QualityError("evidence publication date is not a real calendar date") from exc
    if observed > date.today():
        _error("future-dated quality evidence cannot qualify")
    return {"url": uri, "issuer": issuer, "kind": kind, "published": published}


def _entry(value: Any, *, era: str, console: str, genre: str,
           period: str) -> dict[str, Any]:
    expected = {"id", "release_year", "sales_units", "sales_basis", "sales_scope",
                "critic_score", "critic_reviews", "sales_source", "rating_source"}
    if not isinstance(value, dict) or set(value) != expected:
        _error("benchmark title evidence must contain exactly the declared fields")
    identity = _ident(value["id"], "benchmark title identity")
    lo, hi = _period(period)
    release = _natural(value["release_year"], "release_year", minimum=1970, maximum=2100)
    if not lo <= release <= hi:
        _error("benchmark release year outside period")
    sales = _natural(value["sales_units"], "sales_units", minimum=1)
    basis = value["sales_basis"]
    if basis not in ("sell_through", "reported_units", "shipments"):
        _error("unsupported unit-sales measurement basis")
    scope = value["sales_scope"]
    if scope not in ("global_lifetime", "regional_lifetime"):
        _error("unsupported sales measurement scope")
    quality = _natural(value["critic_score"], "critic_score", maximum=100)
    reviews = _natural(value["critic_reviews"], "critic_reviews", minimum=1, maximum=100000)
    sale_cite = _source(value["sales_source"], "sales")
    rating_cite = _source(value["rating_source"], "rating")
    if sale_cite["url"] == rating_cite["url"] or sale_cite["issuer"].casefold() == rating_cite["issuer"].casefold():
        _error("sales and ratings must be independently sourced")
    if (int(sale_cite["published"][:4]) < release
        or int(rating_cite["published"][:4]) < release):
        _error("commercial or review evidence predates the recorded title release")
    return {"id": identity, "release_year": release, "sales_units": sales,
            "sales_basis": basis, "sales_scope": scope,
            "critic_score": quality, "critic_reviews": reviews,
            "sales_source": sale_cite, "rating_source": rating_cite}


def load_cohort(root: Path, *, console: str, genre: str, period: str,
                profile: str = "design/market_benchmarks.json") -> dict[str, Any]:
    """Exact cohort match; never compare a different console, genre or decade."""
    from skeleton.developer.game_cli import _load
    cfg = _load(root)
    console, genre = _ident(console, "console"), _ident(genre, "genre")
    _period(period)
    payload, sha = _read(root, profile, MAX_DATA_BYTES)
    if set(payload) != {"schema", "cohorts"} or payload["schema"] != SCHEMA:
        _error("unsupported or incomplete benchmark schema")
    cohorts = payload["cohorts"]
    if not isinstance(cohorts, list) or len(cohorts) > MAX_COHORTS:
        _error("too many or invalid benchmark cohorts")
    matches = []
    identities: set[tuple[str, str, str, str]] = set()
    for item in cohorts:
        if not isinstance(item, dict) or set(item) != {"era", "console", "genre", "period", "records"}:
            _error("invalid benchmark cohort fields")
        key = tuple(_ident(item[field], field) for field in ("era", "console", "genre")) + (item["period"],)
        _period(key[3])
        normalized = tuple(s.casefold() for s in key)
        if normalized in identities:
            _error("duplicate benchmark cohort")
        identities.add(normalized)
        if key == (cfg["era"], console, genre, period):
            matches.append(item)
    if len(matches) != 1:
        _error("exact era/console/genre/period cohort absent")
    selected = matches[0]
    records = selected["records"]
    if not isinstance(records, list) or len(records) > MAX_TITLES:
        _error("invalid benchmark record count")
    normalized_records = [_entry(row, era=cfg["era"], console=console,
                                 genre=genre, period=period) for row in records]
    unique_ids = [r["id"].casefold() for r in normalized_records]
    if len(set(unique_ids)) != len(unique_ids):
        _error("duplicate game identity in benchmark cohort")
    return {"schema": SCHEMA, "era": cfg["era"], "console": console,
            "genre": genre, "period": period, "profile_sha256": sha,
            "records": normalized_records,
            "evidence_status": "operator_supplied_not_independently_verified"}


def rank_cohort(root: Path, *, console: str, genre: str, period: str,
                profile: str = "design/market_benchmarks.json") -> dict[str, Any]:
    cohort = load_cohort(root, console=console, genre=genre,
                         period=period, profile=profile)
    records = cohort.pop("records")
    if len(records) < MIN_COHORT:
        _error(f"at least {MIN_COHORT} comparable games required for rankings")
    if len({r["sales_basis"] for r in records}) != 1 or len({r["sales_scope"] for r in records}) != 1:
        _error("cannot compare inconsistent unit-sales basis or geographic scope")
    if any(r["critic_reviews"] < MIN_CRITIC_REVIEWS for r in records):
        _error("each ranked game needs a credible critic review sample")
    if len({r["sales_units"] for r in records}) < 3 or len({r["critic_score"] for r in records}) < 3:
        _error("cohort lacks enough distinct sales and rating evidence to rank reliably")
    # Ordinal top quartile for BOTH axes; ties share rank rather than
    # arbitrarily excluding an equivalent result by alphabetical sort order.
    cutoff = max(1, math.ceil(len(records) * TOP_PERCENT))
    rows = []
    for rec in records:
        sale_position = 1 + sum(r["sales_units"] > rec["sales_units"] for r in records)
        critic_position = 1 + sum(r["critic_score"] > rec["critic_score"] for r in records)
        eligible = (
            sale_position <= cutoff
            and critic_position <= cutoff
            and rec["critic_score"] >= MIN_SCORE
            and rec["critic_reviews"] >= MIN_CRITIC_REVIEWS
        )
        rows.append({
            "id": rec["id"], "release_year": rec["release_year"],
            "sales_units": rec["sales_units"], "sales_rank": sale_position,
            "quality_score": rec["critic_score"], "quality_rank": critic_position,
            "critic_reviews": rec["critic_reviews"], "top_tier": eligible,
            "sales_source": rec["sales_source"], "rating_source": rec["rating_source"],
        })
    rows.sort(key=lambda r: (not r["top_tier"], max(r["sales_rank"], r["quality_rank"]),
                             r["sales_rank"] + r["quality_rank"], r["id"].casefold()))
    leaders = [r for r in rows if r["top_tier"]]
    summary = {
        **cohort, "cohort_size": len(rows), "top_quartile_cutoff_rank": cutoff,
        "minimum_critic_score": MIN_SCORE, "minimum_review_count": MIN_CRITIC_REVIEWS,
        "sales_basis": records[0]["sales_basis"], "sales_scope": records[0]["sales_scope"],
        "qualifying_count": len(leaders),
        "eligible_for_inspiration": bool(leaders),
        "qualification": "dual_top_quartile_sales_and_critic_consensus",
        "leaders": leaders,
        "all_ranks": rows,
        "benchmark_status": "relative_ranking_from_operator_supplied_evidence",
        "asset_quality_proven": False,
        "rights_to_copy_assets": False,
    }
    return summary


def prompt_profile(ranking: dict[str, Any]) -> dict[str, Any]:
    """Provide model only aggregate signals, no named third-party IP."""
    if not ranking.get("eligible_for_inspiration"):
        _error("no independently rated and commercially top-tier titles for cohort")
    leaders = ranking["leaders"]
    return {
        "era": ranking["era"], "console": ranking["console"],
        "genre": ranking["genre"], "period": ranking["period"],
        "cohort_size": ranking["cohort_size"],
        "qualified_reference_count": len(leaders),
        "reference_sales_range_units": [min(r["sales_units"] for r in leaders),
                                         max(r["sales_units"] for r in leaders)],
        "reference_critic_range": [min(r["quality_score"] for r in leaders),
                                   max(r["quality_score"] for r in leaders)],
        "criteria": "top quartile in both comparable sales and review consensus; critic >=85; >=7 reviews",
        "source_status": "operator_supplied_not_independently_verified",
        "instructions": (
            "Produce original game designs, not derivatives or lifted game art. "
            "Use these aggregate commercial and quality bars only as design ambitions. "
            "Do not claim actual asset fidelity, sales potential, review score, "
            "runtime performance or model improvement without independent evidence."
        ),
    }


def _probe_artifact(path: Path, kind: str) -> dict[str, Any]:
    """Static container checks only; not visual/artistic or decoding proof."""
    ext = path.suffix.lower()
    size = path.stat().st_size
    if not 32 <= size <= 128 * 1024 * 1024:
        _error("asset container is empty, truncated or oversized")
    with path.open("rb") as stream:
        head = stream.read(32)
        if kind in ("asset", "animation") and ext == ".png":
            if head[:8] != b"\x89PNG\r\n\x1a\n":
                _error("invalid PNG file signature")
            stream.seek(8)
            seen_idat = False
            width = height = None
            for idx in range(16000):
                header = stream.read(8)
                if len(header) != 8:
                    _error("truncated PNG chunk header")
                length, tag = struct.unpack(">I4s", header)
                if length > 64 * 1024 * 1024:
                    _error("PNG chunk exceeds bounded limit")
                if idx == 0 and (tag != b"IHDR" or length != 13):
                    _error("missing first PNG IHDR chunk")
                crc = zlib.crc32(tag)
                remaining = length
                first = b""
                while remaining:
                    portion = stream.read(min(1 << 20, remaining))
                    if not portion:
                        _error("truncated PNG chunk payload")
                    if idx == 0:
                        first += portion
                    crc = zlib.crc32(portion, crc)
                    remaining -= len(portion)
                expected = stream.read(4)
                if len(expected) != 4 or (crc & 0xffffffff) != struct.unpack(">I", expected)[0]:
                    _error("PNG chunk CRC mismatch")
                if idx == 0:
                    width, height = struct.unpack(">II", first[:8])
                    if not 1 <= width <= 16384 or not 1 <= height <= 16384:
                        _error("PNG render dimensions invalid")
                if tag == b"IDAT":
                    seen_idat = True
                if tag == b"IEND":
                    if length != 0 or not seen_idat or stream.read(1):
                        _error("PNG missing image payload or contains trailing data")
                    return {"container": "png", "width": width, "height": height,
                            "container_integrity_checked": True}
            _error("PNG exceeds chunk count limit")
        elif kind == "animation" and ext == ".gif":
            if head[:6] not in (b"GIF87a", b"GIF89a"):
                _error("GIF signature invalid")
            width, height = struct.unpack("<HH", head[6:10])
            if not 1 <= width <= 16384 or not 1 <= height <= 16384:
                _error("GIF dimensions invalid")
            return {"container": "gif", "width": width, "height": height,
                    "container_integrity_checked": False}
        elif kind == "cutscene" and ext == ".mp4":
            if head[4:8] != b"ftyp" or struct.unpack(">I", head[:4])[0] < 16:
                _error("MP4 brand header invalid")
            return {"container": "mp4", "container_integrity_checked": False}
        elif kind == "music" and ext == ".wav":
            if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
                _error("WAV RIFF signature invalid")
            return {"container": "wav", "container_integrity_checked": False}
        else:
            _error("unsupported or mismatched render media format")
    _error("could not inspect media container")


def gate_render_asset(root: Path, *, console: str, genre: str, period: str,
                      evidence: str, profile: str = "design/market_benchmarks.json") -> dict[str, Any]:
    """Require original content, real file identity, visual QA and performance QA.

    Operator QA values are not automatically certified by this static preflight.
    """
    ranking = rank_cohort(root, console=console, genre=genre, period=period, profile=profile)
    if not ranking["eligible_for_inspiration"]:
        _error("render gate denied: no qualifying top-tier game references")
    data, evidence_sha = _read(root, evidence, MAX_ASSET_EVIDENCE_BYTES)
    required = {"schema", "kind", "asset_path", "sha256", "originality",
                "qa_scores", "reviewers", "performance"}
    if set(data) != required or data["schema"] != ASSET_SCHEMA:
        _error("unsupported asset quality receipt")
    kind = data["kind"]
    if kind not in _RUBRICS:
        _error("unsupported render quality kind")
    asset_rel = data["asset_path"]
    if not isinstance(asset_rel, str) or "\\" in asset_rel or len(asset_rel) > 256:
        _error("unsafe asset path")
    p = PurePosixPath(asset_rel)
    if p.is_absolute() or len(p.parts) < 2 or p.parts[0] != "assets" or any(
        seg in {"", ".", ".."} for seg in asset_rel.split("/")
    ):
        _error("rendered content must reside within project assets/")
    dest = root
    for seg in p.parts:
        dest = dest / seg
        if dest.is_symlink():
            _error("asset path contains symlink")
    if not dest.is_file() or dest.stat().st_size > 128 * 1024 * 1024:
        _error("render artifact missing, unsafe or oversized")
    digest = data["sha256"]
    if not isinstance(digest, str) or _HEX.fullmatch(digest) is None:
        _error("invalid rendered asset identity")
    h = hashlib.sha256()
    with dest.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != digest:
        _error("rendered asset SHA-256 mismatch")
    probe = _probe_artifact(dest, kind)
    if data["originality"] != "original":
        _error("rendered asset must declare original provenance")
    rubric = data["qa_scores"]
    if not isinstance(rubric, dict) or set(rubric) != set(_RUBRICS[kind]):
        _error("render QA must include all quality dimensions for its kind")
    if any(type(score) is not int or not 90 <= score <= 100 for score in rubric.values()):
        _error("top-tier render QA requires >=90 in every quality dimension")
    reviewers = data["reviewers"]
    if not isinstance(reviewers, list) or len(reviewers) < 2 or len(reviewers) > 8 or any(
        not isinstance(person, str) or _IDENT.fullmatch(person) is None for person in reviewers
    ) or len({x.casefold() for x in reviewers}) != len(reviewers):
        _error("at least two distinct named reviewers required")
    perf = data["performance"]
    if not isinstance(perf, dict) or set(perf) != {"measured_ms", "budget_ms", "platform"}:
        _error("invalid render performance evidence")
    if perf["platform"] != console:
        _error("performance assessment console mismatch")
    for field in ("measured_ms", "budget_ms"):
        val = perf[field]
        if type(val) not in (int, float) or not math.isfinite(val) or not 0 < val <= 10000:
            _error("invalid render performance measurement")
    if perf["measured_ms"] > perf["budget_ms"]:
        _error("render performance exceeds declared platform budget")
    return {"ok": True, "action": "asset-gate", "artifact": asset_rel,
            "artifact_sha256": digest, "evidence_sha256": evidence_sha,
            "profile_sha256": ranking["profile_sha256"],
            "quality_dimensions": sorted(rubric), "quality_score_floor": min(rubric.values()),
            "reviewer_count": len(reviewers), "benchmarked_reference_count": ranking["qualifying_count"],
            "static_checks_passed": True,
            "media_probe": probe,
            "human_scores_independently_verified": False,
            "performance_measurement_independently_verified": False,
            "peak_quality_proven": False, "production_qualified": False}


def benchmark_matrix(root: Path, *,
                     profile: str = "design/market_benchmarks.json") -> dict[str, Any]:
    """Coverage review across all operator-declared eras/consoles/genres/periods.

    Only declarations in the supplied file are scanned; this is never a claim
    that every world platform or historical title has been documented.
    """
    payload, identity = _read(root, profile, MAX_DATA_BYTES)
    if payload.get("schema") != SCHEMA or set(payload) != {"schema", "cohorts"}:
        _error("unsupported benchmark evidence envelope")
    cohorts = payload["cohorts"]
    if not isinstance(cohorts, list) or len(cohorts) > MAX_COHORTS:
        _error("invalid declared benchmark cohort count")
    found: set[tuple[str, str, str, str]] = set()
    matrix = []
    for row in cohorts:
        if not isinstance(row, dict) or set(row) != {"era", "console", "genre", "period", "records"}:
            _error("malformed benchmark cohort declaration")
        key = tuple(_ident(row[field], field) for field in ("era", "console", "genre")) + (row["period"],)
        _period(key[3])
        folded = tuple(v.casefold() for v in key)
        if folded in found:
            _error("duplicate benchmark cohort identity")
        found.add(folded)
        info: dict[str, Any] = {"era":key[0], "console":key[1], "genre":key[2],
                                "period":key[3]}
        try:
            from skeleton.developer.game_cli import _load
            active = _load(root)["era"]
            if active != key[0]:
                # Every workspace is configured for one canonical era; other
                # eras are catalogued here but cannot inherit that validation.
                info.update({"ready":False, "status":"other_era_not_validated_in_workspace",
                             "qualifying_count":0})
            else:
                rank = rank_cohort(root, console=key[1], genre=key[2],
                                   period=key[3], profile=profile)
                info.update({"ready":rank["eligible_for_inspiration"],
                             "status":"eligible" if rank["eligible_for_inspiration"]
                             else "no_dual_top_tier",
                             "cohort_size":rank["cohort_size"],
                             "qualifying_count":rank["qualifying_count"]})
        except QualityError as exc:
            info.update({"ready":False, "status":"invalid_evidence",
                         "error":str(exc), "qualifying_count":0})
        matrix.append(info)
    ready = sum(bool(item["ready"]) for item in matrix)
    return {"ok":bool(matrix) and ready == len(matrix),
            "action":"benchmark-matrix", "profile_sha256":identity,
            "declared_cohorts":len(matrix), "qualifying_cohorts":ready,
            "gapped_cohorts":len(matrix)-ready, "coverage":matrix,
            "global_platform_coverage_proven":False,
            "market_values_independently_verified":False}
