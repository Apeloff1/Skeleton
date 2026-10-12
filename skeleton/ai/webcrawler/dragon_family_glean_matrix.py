"""Mother Dragon's evidence-governed glean matrix.

The three idle hatchlings deliver verified source revisions. The mother can
recognize cross-source hypotheses, unresolved disagreements, adjacency and
research priorities, but does NOT autonomously hallucinate findings, crawl,
approve Wiki facts, evaluate models, create weights or mint game XP.

A trusted research producer submits a LensObservation only after canonical
source review and an independent claim/anchor verification callback. Source
revocations and later revisions automatically invalidate old observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Callable
import json
import re
import sqlite3

from .dragon_family import (
    DragonFamily, SourceReceipt, _digest, _epoch, _hash, _owner, _source_id, _utc,
)

SCHEMA="skeleton.ai.dragon.glean.v1"
LENSES=(
    "game_mechanics","game_ai","narrative","world_design","level_design",
    "gameplay_balance","accessibility","player_experience","retention",
    "portability","native_hardware","performance","reliability",
    "security","provenance","copyright","licensing","economics",
    "production","testing","adversarial","competitive","adjacent_transfer",
)
STANCES=("supports","challenges")
_ALLOWED=re.compile(r"^[a-z][a-z0-9_.:-]{2,79}$")
ZERO="0"*64


@dataclass(frozen=True)
class LensObservation:
    source_id: str
    content_digest: str
    proposition_digest: str
    anchor_digest: str
    lens: str
    stance: str
    independence_group: str
    confidence: float
    observed_at: float
    explanation: str


class DragonGleanMatrix:
    """Owner-bound post-review correlation; no second source authority.

    `finding_verify` is independent of the original source producer: it must
    verify the exact quotation/timecoded anchor and the claimed proposition.
    In particular, merely tagging a source with a topic never creates an
    observation. The host must supply both trusted callbacks.
    """

    def __init__(self, family: DragonFamily, *,
                 finding_verify: Callable[[str,LensObservation], bool] | None = None,
                 maximum_findings: int = 50000):
        if not isinstance(family,DragonFamily) or family.owner_scope is None:
            raise PermissionError("gleaning requires a trusted owner-locked Dragon Family")
        if family.approval is None:
            raise PermissionError("canonical source reviewer required")
        if finding_verify is not None and not callable(finding_verify):
            raise ValueError("invalid independent claim reviewer")
        if type(maximum_findings) is not int or not 100<=maximum_findings<=1000000:
            raise ValueError("invalid glean storage budget")
        self.family=family
        self.owner=family.owner_scope
        self.db=family.db
        self.finding_verify=finding_verify
        self.maximum_findings=maximum_findings
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_glean_observations (
            owner TEXT NOT NULL, lens TEXT NOT NULL, proposition_digest TEXT NOT NULL,
            source_id TEXT NOT NULL, content_digest TEXT NOT NULL,
            anchor_digest TEXT NOT NULL, stance TEXT NOT NULL,
            independence_group TEXT NOT NULL, confidence REAL NOT NULL,
            observed_at REAL NOT NULL, explanation TEXT NOT NULL,
            PRIMARY KEY(owner,lens,proposition_digest,source_id,content_digest,anchor_digest,stance))""")
        self.db.execute("""CREATE INDEX IF NOT EXISTS dragon_glean_claims
            ON dragon_glean_observations(owner,lens,proposition_digest)""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_glean_events (
            owner TEXT NOT NULL, sequence INTEGER NOT NULL, at REAL NOT NULL,
            action TEXT NOT NULL, lens TEXT NOT NULL,
            proposition_digest TEXT NOT NULL, source_id TEXT NOT NULL,
            change TEXT NOT NULL, previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL, PRIMARY KEY(owner,sequence))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS dragon_glean_shadow_queue (
            owner TEXT NOT NULL, lens TEXT NOT NULL,
            proposition_digest TEXT NOT NULL, requested_at REAL NOT NULL,
            evidence_fingerprint TEXT NOT NULL,
            source_revision_json TEXT NOT NULL,
            decision_fingerprint TEXT NOT NULL, note TEXT NOT NULL,
            PRIMARY KEY(owner,lens,proposition_digest,evidence_fingerprint))""")
        self.db.commit()

    def _owner(self,owner: str,authorized:bool) -> None:
        _owner(owner)
        self.family._assert_owner(owner)
        if not authorized:
            raise PermissionError("authenticated mother dragon producer required")

    @staticmethod
    def _validate(row: LensObservation) -> None:
        if not isinstance(row,LensObservation):
            raise ValueError("structured reviewed lens observation required")
        _source_id(row.source_id)
        for x in (row.content_digest,row.proposition_digest,row.anchor_digest):
            _digest(x)
        if row.lens not in LENSES or row.stance not in STANCES:
            raise ValueError("unsupported insight lens or evidence stance")
        if not isinstance(row.independence_group,str) or not _ALLOWED.fullmatch(row.independence_group):
            raise ValueError("invalid independent publisher group")
        if (type(row.confidence) not in (int,float) or
                not isfinite(row.confidence) or not 0<=row.confidence<=1):
            raise ValueError("unbounded lens confidence")
        _epoch(row.observed_at)
        if (not isinstance(row.explanation,str) or
                not 12<=len(row.explanation)<=240 or
                any(ord(c)<32 for c in row.explanation)):
            raise ValueError("reviewer must provide bounded useful explanation")

    def _latest(self, owner: str, sid: str) -> tuple | None:
        return self.db.execute("""SELECT r.content_digest,r.review_digest,r.observed_at,
            s.media,s.topics_json
            FROM dragon_family_readings r
            JOIN dragon_family_sources s ON s.owner=r.owner AND s.source_id=r.source_id
            WHERE r.owner=? AND r.source_id=?
            ORDER BY r.observed_at DESC,r.rowid DESC LIMIT 1""",(owner,sid)).fetchone()

    def _source_fresh(self,owner: str,sid: str,digest: str) -> tuple | None:
        found=self._latest(owner,sid)
        if not found or found[0]!=digest:
            return None
        if self.family.approval(SourceReceipt(sid,digest,found[1],found[2])) is not True:
            return None
        return found

    def _event(self,owner: str,action: str,observation: LensObservation,
               at: float,note: str) -> None:
        prev=self.db.execute("""SELECT sequence,at,event_hash FROM dragon_glean_events
            WHERE owner=? ORDER BY sequence DESC LIMIT 1""",(owner,)).fetchone()
        seq,prior=(prev[0]+1,prev[2]) if prev else (1,ZERO)
        if seq>self.maximum_findings or (prev and at<prev[1]):
            raise ValueError("glean event budget exhausted or event time regressed")
        fingerprint=_hash([owner,seq,at,action,observation.lens,
            observation.proposition_digest,observation.source_id,note,prior])
        self.db.execute("""INSERT INTO dragon_glean_events
            VALUES(?,?,?,?,?,?,?,?,?,?)""",(owner,seq,at,action,
            observation.lens,observation.proposition_digest,
            observation.source_id,note,prior,fingerprint))

    def record(self,owner: str,observation: LensObservation, *,
               authorized: bool) -> bool:
        """Store one independently attested claim/anchor on current evidence.

        Never infer 'support' or 'challenge' from a search ranking or LLM score.
        Recheck source/reviewer inside one SQLite write transaction. A revoked
        claim or duplicate anchor never contributes to family progression.
        """
        self._owner(owner,authorized)
        if self.finding_verify is None:
            raise PermissionError("independent proposition/anchor verifier not installed")
        self._validate(observation)
        if self._source_fresh(owner,observation.source_id,observation.content_digest) is None:
            raise PermissionError("canonical reviewed source revision missing or revoked")
        if self.finding_verify(owner,observation) is not True:
            raise PermissionError("independent proposition/anchor verification required")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            current=self._source_fresh(owner,observation.source_id,observation.content_digest)
            if current is None or self.finding_verify(owner,observation) is not True:
                raise PermissionError("source or independent review changed during glean admission")
            if observation.observed_at<current[2]:
                raise ValueError("glean observation precedes reviewed source revision")
            duplicate=self.db.execute("""SELECT 1 FROM dragon_glean_observations
                WHERE owner=? AND lens=? AND proposition_digest=? AND source_id=?
                    AND content_digest=? AND anchor_digest=? AND stance=?""",
                (owner,observation.lens,observation.proposition_digest,
                 observation.source_id,observation.content_digest,
                 observation.anchor_digest,observation.stance)).fetchone()
            if duplicate:
                return False
            count=self.db.execute("""SELECT COUNT(*) FROM dragon_glean_observations
                WHERE owner=?""",(owner,)).fetchone()[0]
            if count>=self.maximum_findings:
                raise ValueError("glean observation capacity exhausted")
            self.db.execute("""INSERT INTO dragon_glean_observations
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(owner,observation.lens,
                observation.proposition_digest,observation.source_id,
                observation.content_digest,observation.anchor_digest,
                observation.stance,observation.independence_group,
                float(observation.confidence),observation.observed_at,
                observation.explanation))
            self._event(owner,"finding_recorded",observation,observation.observed_at,
                "(gleaned: independently reviewed "+observation.lens+
                " evidence; "+observation.stance+")")
        return True

    def _fresh_observations(self,owner: str) -> tuple[list[tuple],int]:
        rows=self.db.execute("""SELECT lens,proposition_digest,source_id,content_digest,
            anchor_digest,stance,independence_group,confidence,observed_at,explanation
            FROM dragon_glean_observations WHERE owner=?
            ORDER BY lens,proposition_digest,source_id,observed_at""",(owner,)).fetchall()
        valid=[]
        stale=0
        # Check each reviewed source revision once; an invalid source may
        # invalidate many observations without granting evidence by repetition.
        cache:dict[tuple[str,str],tuple|None]={}
        for r in rows:
            key=(r[2],r[3])
            if key not in cache:
                cache[key]=self._source_fresh(owner,*key)
            current=cache[key]
            if current is None:
                stale+=1
                continue
            valid.append((*r,current[3]))
        return valid,stale

    @staticmethod
    def _aggregate(rows:list[tuple]) -> list[dict[str,object]]:
        groups:dict[tuple[str,str],list[tuple]]={}
        for r in rows:
            groups.setdefault((r[0],r[1]),[]).append(r)
        cells=[]
        for (lens,proposition),items in groups.items():
            supporters=[r for r in items if r[5]=="supports"]
            challengers=[r for r in items if r[5]=="challenges"]
            # Repeating anchors, independent-group names or mirror URLs can
            # never manufacture corroboration from one underlying source.
            distinct_supports={r[2] for r in supporters}
            independent_support={r[6] for r in supporters}
            distinct_challenges={r[2] for r in challengers}
            independent_challenges={r[6] for r in challengers}
            enough=len(distinct_supports)>=2 and len(independent_support)>=2
            contested=bool(challengers)
            status=("contested" if contested else
                    "wiki_candidate" if enough else "needs_independent_sources")
            sources={r[2] for r in items}
            cell=dict(lens=lens,proposition_digest=proposition,
                status=status,source_count=len(sources),
                support_sources=len(distinct_supports),
                challenge_sources=len(distinct_challenges),
                support_groups=len(independent_support),
                challenge_groups=len(independent_challenges),
                modalities=sorted({r[-1] for r in items}),
                latest_at=_utc(max(r[8] for r in items)),
                exemplar=sorted(items,key=lambda r:(-r[7],r[2]))[0][9],
                priority=("investigate_disagreement" if contested else
                          "independent_wiki_review" if enough else
                          "seek_separate_source"),
                # This is information-priority triage, NOT model gain or XP.
                evidence_fingerprint=_hash(sorted(
                    [r[2],r[3],r[4],r[5],r[6]] for r in items)),
                )
            cells.append(cell)
        return sorted(cells,key=lambda c:(
            0 if c["status"]=="contested" else
            1 if c["status"]=="wiki_candidate" else 2,
            -c["source_count"],c["lens"],c["proposition_digest"]))

    def projection(self,owner: str,*,authorized:bool,limit:int=20) -> dict[str,object]:
        self._owner(owner,authorized)
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid glean projection page")
        valid,stale=self._fresh_observations(owner)
        cells=self._aggregate(valid)
        counts={k:sum(c["status"]==k for c in cells) for k in
                ("contested","wiki_candidate","needs_independent_sources")}
        return dict(schema=SCHEMA,insights=len(cells),counts=counts,
            stale_observations=stale,total_active_observations=len(valid),
            lenses_used=len({c["lens"] for c in cells}),
            cells=cells[:limit],read_only=True,
            promotion="independent Wiki then sandbox; never direct live weights",
            updated_at=max((c["latest_at"] for c in cells),default=None))

    def history(self,owner: str,*,authorized:bool,limit:int=20) -> list[dict[str,object]]:
        self._owner(owner,authorized)
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid glean history limit")
        rows=self.db.execute("""SELECT sequence,at,action,lens,proposition_digest,
            source_id,change,previous_hash,event_hash
            FROM dragon_glean_events WHERE owner=? ORDER BY sequence""",(owner,)).fetchall()
        prior=ZERO
        result=[]
        for seq,row in enumerate(rows,1):
            n,at,action,lens,proposition,sid,note,previous,digest=row
            if (n!=seq or previous!=prior or
                _hash([owner,n,at,action,lens,proposition,sid,note,previous])!=digest or
                (result and at<float(result[-1]["epoch"]))):
                raise ValueError("glean review event chain integrity failure")
            prior=digest
            result.append(dict(sequence=n,at=_utc(at),epoch=at,action=action,
                lens=lens,proposition_digest=proposition,source_id=sid,
                change=note,digest=digest))
        return [{k:v for k,v in r.items() if k!="epoch"} for r in result[-limit:][::-1]]

    def research_briefs(self,owner: str,*,authorized:bool,
                        limit:int=20) -> list[dict[str,object]]:
        """Pure, task-relevant mission briefs; no direct crawler dispatch.

        A host planner may take these read-only requests through its existing
        SSRF/robots/rights/budget gates. Every action is conditional on current
        verified source custody and must be approved by that planner before
        starting an idle worker.
        """
        self._owner(owner,authorized)
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid glean research brief budget")
        valid,_=self._fresh_observations(owner)
        cells=self._aggregate(valid)
        briefs=[]
        for cell in cells:
            lens=cell["lens"]
            proposition=cell["proposition_digest"]
            evidence=cell["evidence_fingerprint"]
            affected=sorted({r[2] for r in valid if
                r[0]==lens and r[1]==proposition})
            modalities=tuple(cell["modalities"])
            if cell["status"]=="contested":
                rule=("IF independent evidence challenges the same proposition "
                      "AND corroboration is incomplete, THEN investigate both "
                      "source revisions and seek a fresh counterexample; BUT "
                      "never promote conflicting evidence")
                action="revisit_conflicting_sources"
                targets=("monitor","article","video")
                priority=0
            elif cell["status"]=="wiki_candidate":
                rule=("IF two distinct source identities AND two reviewed "
                      "publisher groups corroborate a proposition AND no "
                      "current challenge exists, THEN request independent Wiki "
                      "review; BUT do not bypass sandbox holdouts")
                action="request_independent_wiki"
                targets=()
                priority=1
            else:
                rule=("IF independently supported by one source OR one publisher "
                      "group only, THEN seek a different evidence group and "
                      "adjacent technical context; BUT do not count repeated "
                      "observations as corroboration")
                action="find_independent_corroboration"
                targets=("article","video")
                priority=2
            briefs.append(dict(
                schema="skeleton.ai.dragon.glean_brief.v1",
                lens=lens,proposition_digest=proposition,
                evidence_fingerprint=evidence,
                action=action,priority=priority,
                source_ids=affected[:12],
                source_count=len(affected),
                required_specialists=list(targets),
                existing_modalities=list(modalities),
                last_evidence_at=cell["latest_at"],
                condition=rule,
                human_review_required=True,
                permits_network=False,
                permits_weight_promotion=False))
        return sorted(briefs,key=lambda b:(
            b["priority"],-b["source_count"],b["lens"],b["proposition_digest"]))[:limit]

    def queue_shadow_candidate(self,owner: str,lens:str,proposition_digest:str,*,
                               authorized:bool,at:float,
                               wiki_claim_verify:Callable[[str,str,str,tuple[str,...]],bool]) -> str:
        """Queue ONLY a Wiki-reviewed, uncontested proposition for evaluation.

        This does not train a model or declare a demonstrated quality gain. It
        requires separately reviewed supporting source revisions in Almanakk,
        independent Wiki claim-level review, and a fresh source evidence set.
        """
        self._owner(owner,authorized)
        if lens not in LENSES:
            raise ValueError("unsupported glean lens")
        _digest(proposition_digest)
        at=_epoch(at)
        if not callable(wiki_claim_verify):
            raise PermissionError("separate Wiki proposition verifier required")
        self.db.execute("BEGIN IMMEDIATE")
        with self.db:
            valid,_=self._fresh_observations(owner)
            cells=self._aggregate([r for r in valid if r[0]==lens and r[1]==proposition_digest])
            if len(cells)!=1 or cells[0]["status"]!="wiki_candidate":
                raise PermissionError("insufficient independent, uncontested glean evidence")
            sources=sorted(set((r[2],r[3]) for r in valid
                if r[0]==lens and r[1]==proposition_digest and r[5]=="supports"))
            if not sources:
                raise PermissionError("no corroborated sources")
            for sid,digest in sources:
                current=self.db.execute("""SELECT stage FROM dragon_almanakk_reviews
                    WHERE owner=? AND source_id=? AND content_digest=?
                    ORDER BY updated_at DESC LIMIT 1""",(owner,sid,digest)).fetchone()
                if not current or current[0] not in (
                        "wiki_verified","shadow_validated","weight_handoff"):
                    raise PermissionError("all corroborating sources require independent Wiki review")
            evidence=tuple(cells[0]["evidence_fingerprint"] for _ in range(1))
            witness_ids=tuple(sid for sid,_ in sources)
            if wiki_claim_verify(owner,lens,proposition_digest,witness_ids) is not True:
                raise PermissionError("Wiki has not independently verified this cross-source inference")
            rows=[[sid,digest] for sid,digest in sources]
            evidence_fingerprint=_hash([lens,proposition_digest,rows,evidence])
            decision=_hash([owner,lens,proposition_digest,evidence_fingerprint,at])
            present=self.db.execute("""SELECT 1 FROM dragon_glean_shadow_queue
                WHERE owner=? AND lens=? AND proposition_digest=?
                    AND evidence_fingerprint=?""",(owner,lens,proposition_digest,
                    evidence_fingerprint)).fetchone()
            if present:
                return evidence_fingerprint
            self.db.execute("""INSERT INTO dragon_glean_shadow_queue VALUES(?,?,?,?,?,?,?,?)""",
                (owner,lens,proposition_digest,at,evidence_fingerprint,
                 json.dumps(rows,separators=(",",":")),decision,
                 "(queued: independently corroborated and Wiki-reviewed for holdout sandbox)"))
        return evidence_fingerprint

    def shadow_queue(self,owner: str,*,authorized:bool,limit:int=20) -> list[dict[str,object]]:
        self._owner(owner,authorized)
        if type(limit) is not int or not 1<=limit<=100:
            raise ValueError("invalid shadow queue page")
        rows=self.db.execute("""SELECT lens,proposition_digest,requested_at,
            evidence_fingerprint,source_revision_json,note
            FROM dragon_glean_shadow_queue WHERE owner=?
            ORDER BY requested_at DESC,evidence_fingerprint DESC LIMIT ?""",
            (owner,limit)).fetchall()
        result=[]
        valid,_=self._fresh_observations(owner)
        current=self._aggregate(valid)
        status_map={(c["lens"],c["proposition_digest"]):c for c in current}
        for lens,prop,at,fp,versions,note in rows:
            cell=status_map.get((lens,prop))
            revisions=json.loads(versions)
            latest_pairs={tuple((r[2],r[3])) for r in valid
                if r[0]==lens and r[1]==prop and r[5]=="supports"}
            fresh=bool(cell and cell["status"]=="wiki_candidate" and
                       latest_pairs=={tuple(v) for v in revisions})
            if fresh:
                for sid,digest in latest_pairs:
                    row=self.db.execute("""SELECT stage FROM dragon_almanakk_reviews
                        WHERE owner=? AND source_id=? AND content_digest=?
                        ORDER BY updated_at DESC LIMIT 1""",(owner,sid,digest)).fetchone()
                    if not row or row[0] not in ("wiki_verified","shadow_validated","weight_handoff"):
                        fresh=False
                        break
            result.append(dict(lens=lens,proposition_digest=prop,
                queued_at=_utc(at),evidence_fingerprint=fp,
                status="awaiting_holdout" if fresh else "stale_requires_wiki_recheck",
                note=note))
        return result
