"""Jurisdiction-bound IP monitoring projections for the existing legal owner.

News triggers investigation. Only reviewed primary records can corroborate a
reported status. No status, date, dormant label or agreement authorizes reuse.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from urllib.parse import urlsplit
from typing import Iterable

from .contracts import canonical_digest
from .game_research_foundation import bounded
from .reviewed_knowledge import _id, _digest, _integer, _source_url, _text


PRIMARY_REGISTERS = {
    "www.uspto.gov": ("US", "uspto"), "uspto.gov": ("US", "uspto"),
    "patentcenter.uspto.gov": ("US", "uspto"), "fees.uspto.gov": ("US", "uspto"),
    "assignmentcenter.uspto.gov": ("US", "uspto"), "tsdr.uspto.gov": ("US", "uspto"),
    "register.epo.org": ("EP", "epo"), "www.epo.org": ("EP", "epo"),
    "search.patentstyret.no": ("NO", "nipo"), "tidende.patentstyret.no": ("NO", "nipo"),
    "www.patentstyret.no": ("NO", "nipo"),
    "publicrecords.copyright.gov": ("US", "us-copyright-office"),
    "www.copyright.gov": ("US", "us-copyright-office"),
}
RIGHT_TYPES = frozenset({"patent", "copyright", "trademark", "license", "ownership"})
STATUSES = frozenset({"active", "expired", "lapsed", "reinstated", "pending", "assigned",
                      "revoked", "disputed", "unknown"})


@dataclass(frozen=True, slots=True)
class IPWatchSubject:
    subject_id: str
    title_id: str
    right_type: str
    jurisdiction: str
    registration_id: str
    labels: tuple[str, ...] = ()

    def __post_init__(self):
        for k in ("subject_id", "title_id", "jurisdiction"):
            _id(getattr(self, k), k)
        _text(self.registration_id, "registration identity", 192)
        if self.right_type not in RIGHT_TYPES:
            raise ValueError("explicit right type required")
        if not isinstance(self.labels, tuple) or len(self.labels) > 16 or len(set(self.labels)) != len(self.labels):
            raise ValueError("bounded unique historical labels required")
        for label in self.labels:
            _id(label, "historical label")


@dataclass(frozen=True, slots=True)
class IPStatusReport:
    report_id: str
    subject_id: str
    jurisdiction: str
    right_type: str
    registration_id: str
    url: str
    source_kind: str
    publisher_group: str
    content_digest: str
    custody_digest: str
    locator: str
    reported_status: str
    reported_expiry: int | None
    observed_at: int

    def __post_init__(self):
        for k in ("report_id", "subject_id", "jurisdiction", "publisher_group"):
            _id(getattr(self, k), k)
        _text(self.registration_id, "registration identity", 192)
        _source_url(self.url)
        _digest(self.content_digest, "content digest")
        _digest(self.custody_digest, "custody digest")
        _text(self.locator, "record locator", 256)
        if self.source_kind not in {"official_register", "legal_filing", "news", "rights_holder"}:
            raise ValueError("known source kind required")
        if self.reported_status not in STATUSES or self.right_type not in RIGHT_TYPES:
            raise ValueError("known reported status and right type required")
        _integer(self.observed_at, "observed_at", 0, 10**12)
        if self.reported_expiry is not None:
            _integer(self.reported_expiry, "reported expiry", 0, 10**12)


def plan_ip_watch(subjects: Iterable[IPWatchSubject], reports: Iterable[IPStatusReport], *,
                  now: int, authorized: bool, interval_seconds: int = 86400) -> dict:
    if authorized is not True:
        raise PermissionError("authenticated IP watch ingestion required")
    _integer(now, "now", 0, 10**12)
    _integer(interval_seconds, "watch interval", 3600, 604800)
    subjects = bounded(subjects, 1000, IPWatchSubject)
    reports = bounded(reports, 10000, IPStatusReport)
    if len({s.subject_id for s in subjects}) != len(subjects) or len({r.report_id for r in reports}) != len(reports):
        raise ValueError("duplicate subject or report identity")
    by_id = {s.subject_id: s for s in subjects}
    history = {sid: [] for sid in by_id}
    for row in reports:
        subject = by_id.get(row.subject_id)
        if subject is None or (row.jurisdiction, row.right_type, row.registration_id) != (
                subject.jurisdiction, subject.right_type, subject.registration_id):
            raise ValueError("report belongs to another right, territory or registration")
        history[row.subject_id].append(row)
    results = []
    for sid, subject in sorted(by_id.items()):
        rows = sorted(history[sid], key=lambda r: (r.observed_at, r.report_id))
        # Retain every historical report in the receipt; only latest per URL
        # participates in the current comparison. Equivocation fails closed.
        latest = {}
        for r in rows:
            old = latest.get(r.url)
            if old and old.observed_at == r.observed_at and (
                    old.content_digest, old.reported_status, old.reported_expiry) != (
                    r.content_digest, r.reported_status, r.reported_expiry):
                raise ValueError("conflicting same-time IP source reports")
            latest[r.url] = r
        current = [r for r in latest.values() if 0 <= now-r.observed_at < interval_seconds]
        primary = []
        parents = list(range(len(current)))
        labels = {}
        def root(i):
            while parents[i] != i:
                parents[i] = parents[parents[i]]
                i = parents[i]
            return i
        for i, r in enumerate(current):
            authority = PRIMARY_REGISTERS.get(urlsplit(r.url).hostname)
            if (r.source_kind in {"official_register", "legal_filing"} and authority
                    and authority[0] == subject.jurisdiction):
                primary.append(r)
            group = "authority:" + authority[1] if authority else "publisher:" + r.publisher_group.casefold()
            for label in (("group", group), ("host", urlsplit(r.url).hostname), ("body", r.content_digest)):
                if label in labels:
                    parents[root(i)] = root(labels[label])
                else:
                    labels[label] = i
        groups = {root(i) for i in range(len(current))}
        claims = {(r.reported_status, r.reported_expiry) for r in current}
        reasons = []
        if not primary:
            reasons.append("current_primary_record_required")
        if len(groups) < 2:
            reasons.append("independent_crosscheck_required")
        if len(claims) > 1:
            reasons.append("conflicting_status_or_expiry")
        if not current or any(r.reported_status in {"unknown", "disputed"} for r in current):
            reasons.append("status_unresolved")
        if any(r.reported_status == "lapsed" for r in current):
            reasons.append("reinstatement_and_grace_period_review_required")
        if any(r.reported_status == "expired" and (r.reported_expiry is None or r.reported_expiry > now) for r in current):
            reasons.append("expiry_basis_incomplete_or_future")
        if len(current) < len(latest):
            reasons.append("stale_or_future_source_requires_refresh")
        changes = []
        previous = {}
        for r in rows:
            old = previous.get(r.url)
            if old and (old.content_digest, old.reported_status, old.reported_expiry) != (
                    r.content_digest, r.reported_status, r.reported_expiry):
                changes.append({"url": r.url, "before": old.content_digest, "after": r.content_digest,
                                "previous_report": old.report_id, "current_report": r.report_id})
            previous[r.url] = r
        body = {"subject": asdict(subject), "current_report_ids": sorted(r.report_id for r in current),
                "history": [asdict(r) for r in rows], "changes": changes,
                "state": "crosschecked_report_requires_legal_review" if not reasons else "needs_investigation",
                "reported_status": next(iter(claims))[0] if len(claims) == 1 else "unknown",
                "reasons": sorted(reasons), "recheck_due": bool(reasons),
                "next_check_at": min((r.observed_at+interval_seconds for r in latest.values()), default=now),
                "reuse_authorized": False, "release_authority": False}
        results.append({**body, "watch_digest": canonical_digest(body)})
    body = {"schema": "skeleton.game_builder.ip_watch.v1", "checked_at": now,
            "subjects": results, "covered_subjects": len(subjects),
            "coverage": "explicit_registered_subjects_only", "global_completeness": False,
            "acquisition_owner": "skeleton/ai/webcrawler", "dispatch_authorized": False}
    return {**body, "watch_plan_digest": canonical_digest(body)}


def main() -> None:
    import argparse
    from pathlib import Path
    from .contracts import canonical_json
    from .reviewed_knowledge import _strict_json
    parser = argparse.ArgumentParser(description="Cross-check an explicit IP watch corpus without network I/O")
    parser.add_argument("--input", required=True)
    parser.add_argument("--as-of", required=True, type=int)
    parser.add_argument("--trusted-local-operator", action="store_true")
    args = parser.parse_args()
    if not args.trusted_local_operator:
        parser.error("external operator authentication acknowledgement required")
    with Path(args.input).open("rb") as stream:
        raw = stream.read(2_000_001)
    if len(raw) > 2_000_000:
        parser.error("watch corpus byte budget exceeded")
    data = _strict_json(raw.decode("utf-8"))
    if not isinstance(data, dict) or set(data) != {"subjects", "reports"}:
        parser.error("subjects and reports required")
    if (not isinstance(data["subjects"], list) or not isinstance(data["reports"], list)
            or len(data["subjects"]) > 1000 or len(data["reports"]) > 10000):
        parser.error("bounded subject and report arrays required")
    subjects = [IPWatchSubject(**{**r, "labels": tuple(r.get("labels", ()))}) for r in data["subjects"]]
    reports = [IPStatusReport(**r) for r in data["reports"]]
    print(canonical_json(plan_ip_watch(subjects, reports, now=args.as_of, authorized=True)))


if __name__ == "__main__":
    main()
