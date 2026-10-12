"""Dragon technical-source glean matrix and canonical analyze-stage review handoff.

Purely deterministic lenses on EXACT captured text and separately observed peer
versions. No inferred finding is a reviewed fact. No language-model-generated
claim, rights grant, neural training or Wiki/HOAG approval occurs here.

The canonical SequentialAlmanacWorker stage-3 receipt is the ONLY persistent
analysis authority. A receipt and its compact packet commit atomically.
"""
from __future__ import annotations

from collections import Counter
import json
import re
from urllib.parse import urlsplit

from .contracts import canonical_digest, canonical_json
from .dragon_almanacs import _auth
from .dragon_almanac_sequence import AlmanacClaim, SequentialAlmanacWorker
from .dragon_technical_source_captures import DragonSourceCaptures
from .dragon_wisdom_authority import DragonWisdomAuthority, WisdomGrant
from .reviewed_knowledge import KnowledgeBrief
from .reviewed_knowledge import _integer

_TOKEN = re.compile(r"[a-z0-9]+")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
# These are *search lenses*, not hard-coded beliefs about source statements.
_LENSES = {
    "mechanics": frozenset("npc player physics input quest level collision dialogue movement game".split()),
    "implementation": frozenset("code compiler api runtime function system data register memory algorithm".split()),
    "performance": frozenset("frame fps latency speed bandwidth cpu gpu optimize performance timing".split()),
    "compatibility": frozenset("version console hardware device mobile handheld backward platform port support".split()),
    "failure": frozenset("bug error failure invalid crash unsafe race deadlock overflow exception".split()),
    "validation": frozenset("test measure benchmark verify proof check reproduce validation regression".split()),
    "rights": frozenset("license rights permission copyright trademark patent proprietary attribution".split()),
    "production": frozenset("pipeline export release package deploy asset build editor import update".split()),
    "uncertainty": frozenset("may might likely estimated uncertain unknown experimental preliminary".split()),
}
_NEGATION = frozenset({"not", "never", "no", "cannot", "without", "unsupported"})
_UNCERTAIN = frozenset({"may", "might", "could", "possibly", "experimental", "unknown"})
_MAX_PEERS = 8
_MAX_LINES = 6
_MAX_PACKET_BYTES = 12_000


def _tokens(value: str) -> set[str]:
    return set(_TOKEN.findall(value.lower()))


def _findings(capture: dict, focus: tuple[str, ...]) -> list[dict]:
    text=capture["document"]["text"]
    rows=[]
    for index,passage in enumerate(capture["evidence_candidates"][:_MAX_LINES]):
        start,end=passage["start"],passage["end"]
        quote=passage["exact_quote"]
        if (type(start) is not int or type(end) is not int
            or not 0<=start<end<=len(text)
            or text[start:end]!=quote or len(quote)>240):
            raise ValueError("unverifiable source evidence span")
        words=_tokens(quote)
        facets=[
            {"lens":lens,"trigger_terms":sorted(words&terms)}
            for lens,terms in sorted(_LENSES.items())
            if words&terms
        ]
        topical=sorted(words&set(focus))
        rows.append({
            "reading_id":canonical_digest([capture["digest"],start,end,quote]),
            "index":index,"start":start,"end":end,
            "exact_quote":quote,"lenses":facets,
            "topic_matches":topical,
            "has_negation":bool(words&_NEGATION),
            "has_hedge":bool(words&_UNCERTAIN),
            "confidence":"not_assessed",
            "stance":"unreviewed",
            "independent_verification_required":True,
        })
    return rows


def _peer_signals(captures: DragonSourceCaptures, owner: str,
                  current: dict, source_id: str,
                  peer_ids: tuple[str, ...]) -> list[dict]:
    """Cross-check source *identity*, observed text and lexical tension only."""
    original_host=urlsplit(current["source_url"]).hostname or ""
    original_topics=set(captures._source(owner,source_id)[1]["topics"])
    source_words=_tokens(" ".join(
        p["exact_quote"] for p in current["evidence_candidates"]))
    source_neg=bool(source_words&_NEGATION)
    signals=[]
    for peer_id in peer_ids:
        if peer_id==source_id:
            raise ValueError("source cannot be its own independent corroborator")
        peer_source,peer_seed=captures._source(owner,peer_id)
        versions=captures._history(owner,peer_id)
        if not versions:
            signals.append({"source_id":peer_id,"status":"no_capture",
                            "independence":"unassessed"})
            continue
        peer=versions[-1]
        # An unchanged re-observation retains the most recent real quotation
        # candidates; it is not itself new corroboration.
        last_changed=next((x for x in reversed(versions)
                           if x["change"]!="unchanged"),peer)
        other_host=urlsplit(peer["source_url"]).hostname or ""
        shared=sorted(original_topics&set(peer_seed["topics"]))
        duplicate=(current["content_sha256"]==peer["content_sha256"])
        peer_words=_tokens(" ".join(
            p["exact_quote"] for p in last_changed["evidence_candidates"]))
        polarity=bool(peer_words&_NEGATION)
        overlap=sorted(source_words&peer_words-(_NEGATION|_UNCERTAIN))[:12]
        possible_tension=bool(shared and overlap and source_neg!=polarity)
        signals.append({
            "source_id":peer_id,
            "latest_capture_digest":peer["digest"],
            "status":"observed",
            "shared_topics":shared[:8],
            "verbatim_overlap_terms":overlap,
            "same_content":duplicate,
            "same_host":original_host==other_host,
            "lexical_tension_hint":possible_tension,
            "independence":"not_proven",
            "review_action":("duplicate_or_common_origin_check" if duplicate or
                             original_host==other_host else
                             "verify_possible_negation_difference" if possible_tension
                             else "check_claim_level_independence"),
        })
    return signals


class DragonTechnicalGlean:
    """Immutable, task-aware analysis with canonical owner/claim fencing."""

    def __init__(self, captures: DragonSourceCaptures):
        if not isinstance(captures,DragonSourceCaptures):
            raise TypeError("canonical Dragon source capture authority required")
        self.captures=captures
        self.a=captures.a
        self.db=captures.db
        self.worker=SequentialAlmanacWorker(self.a)

    def _latest(self,owner,source_id,capture_digest):
        self.captures._source(owner,source_id)
        if not isinstance(capture_digest,str) or not _HEX.fullmatch(capture_digest):
            raise ValueError("exact source capture digest required")
        history=self.captures._history(owner,source_id)
        if not history or history[-1]["digest"]!=capture_digest:
            raise ValueError("stale, missing or superseded source capture")
        current=history[-1]
        if current["change"]=="unchanged":
            raise ValueError("unchanged observation cannot create new analysis")
        return current

    def preview(self,owner: str,source_id: str,*,capture_digest: str,
                peers: tuple[str, ...]=(),authorized: bool) -> dict:
        """No writes, no network, no model execution."""
        _auth(owner,authorized)
        if (not isinstance(peers,tuple) or len(peers)>_MAX_PEERS
            or len(set(peers))!=len(peers)
            or any(not isinstance(x,str) for x in peers)):
            raise ValueError("bounded unique cross-source peers required")
        source=self._latest(owner,source_id,capture_digest)
        seed=self.captures._source(owner,source_id)[1]
        readings=_findings(source,tuple(seed["topics"]))
        peers_found=_peer_signals(self.captures,owner,source,source_id,tuple(sorted(peers)))
        lens_counts=dict(sorted(Counter(
            facet["lens"] for x in readings for facet in x["lenses"]
        ).items()))
        questions=[]
        for lens in lens_counts:
            questions.append({
                "lens":lens,
                "question":"Which exact observation supports or contradicts this "+lens+" interpretation?",
                "answered":False,
            })
        if source["change"]=="changed":
            questions.append({
                "lens":"revision",
                "question":"Which previously accepted claims were invalidated by this content revision?",
                "answered":False,
            })
        packet={
            "schema":"skeleton.dragon.technical_glean.v1",
            "owner":owner,"source_id":source_id,
            "source_url":source["source_url"],
            "capture_digest":source["digest"],
            "content_sha256":source["content_sha256"],
            "observed_at":source["observed_at"],
            "change":source["change"],
            "readings":readings,
            "lens_counts":lens_counts,
            "peer_signals":peers_found,
            "unanswered_questions":questions,
            "improvements":["(task-focused exact-span lenses and cross-source skepticism added)"],
            "analysis_kind":"hypotheses_and_source_quotations_only",
            "fact_checked":False,
            "independent_groups_verified":0,
            "wiki_review_required":True,
            "source_rights_recheck_required":True,
            "knowledge_approved":False,
            "weight_promotion_authorized":False,
            "training_authorized":False,
        }
        if len(canonical_json(packet).encode("utf-8"))>_MAX_PACKET_BYTES:
            raise ValueError("review packet exceeds compact stage budget")
        return {**packet,"packet_digest":canonical_digest(packet)}

    def complete_analyze(self,claim: AlmanacClaim,*,capture_digest: str,
                         peers: tuple[str,...]=(),now: int,
                         authorized: bool,trusted_worker: bool) -> dict:
        if not isinstance(claim,AlmanacClaim) or claim.stage!="analyze":
            raise ValueError("canonical analyze-stage claim required")
        _auth(claim.owner,authorized)
        if trusted_worker is not True:
            raise PermissionError("trusted analysis operator required")
        _integer(now,"analysis clock",0,4_102_444_800)
        packet=self.preview(claim.owner,claim.source_id,
                            capture_digest=capture_digest,peers=peers,authorized=True)
        # Verify the exact extraction receipt and its input identity. A
        # browser-submitted packet cannot substitute a stage-2 extraction.
        row=self.db.execute(
            "SELECT body,digest FROM dragon_almanac_steps "
            "WHERE owner=? AND source=? AND stage=2",
            (claim.owner,claim.source_id)).fetchone()
        if row is None:
            raise ValueError("missing canonical extract receipt")
        extracted=json.loads(row[0])
        if (canonical_digest(extracted)!=row[1]
            or extracted.get("output_digest")!=claim.input_digest
            or extracted.get("evidence",{}).get("capture_digest")!=capture_digest
            or extracted.get("training_authorized") is not False):
            raise ValueError("analysis cannot attach to stale extraction evidence")
        # Persist packet *inside* the existing trusted stage receipt so it and
        # the queue advancement commit atomically, never as a detached ledger.
        payload={k:v for k,v in packet.items() if k!="packet_digest"}
        evidence={
            "url":claim.url,"input_digest":claim.input_digest,
            "output_digest":packet["packet_digest"],
            "derived_claims_are_unreviewed":True,
            "claim_count":len(packet["readings"]),
            "capture_digest":capture_digest,
            "analysis_packet":payload,
            "analysis_digest":packet["packet_digest"],
        }
        receipt=self.worker.finish(claim,now=now,
            output_digest=packet["packet_digest"],evidence=evidence,
            authorized=True,trusted_worker=True)
        return {
            "stage":"analyze","receipt_digest":receipt,
            "analysis_digest":packet["packet_digest"],
            "capture_digest":capture_digest,
            "readings":len(packet["readings"]),
            "peer_observations":len(packet["peer_signals"]),
            "next_stage":"canonical_review",
            "wiki_review_required":True,"knowledge_approved":False,
            "weight_promotion_authorized":False,
        }

    def handoff(self,owner:str,source_id:str,*,authorized:bool,
                include_quotes:bool=False) -> dict:
        """Read the current, fully lineage-verified canonical analysis packet."""
        _auth(owner,authorized)
        if type(include_quotes) is not bool:
            raise ValueError("explicit quote visibility required")
        self.captures._source(owner,source_id)
        job=self.db.execute(
            "SELECT stage,state,input_digest,s.digest,s.body FROM dragon_almanac_jobs j "
            "JOIN dragon_almanac_sources s ON s.owner=j.owner AND s.source=j.source "
            "WHERE j.owner=? AND j.source=?", (owner,source_id)).fetchone()
        if job is None:
            raise ValueError("canonical policy queue required")
        stage,state,input_digest,source_digest,source_body=job
        if state=="blocked":
            return {"owner":owner,"source_id":source_id,
                    "status":"policy_or_review_blocked","review_ready":False}
        if type(stage) is not int or stage<4 or stage>5:
            return {"owner":owner,"source_id":source_id,
                    "status":"awaiting_analysis_stage","review_ready":False}
        body=json.loads(source_body)
        row=self.db.execute(
            "SELECT body,digest FROM dragon_almanac_steps "
            "WHERE owner=? AND source=? AND stage=3",
            (owner,source_id)).fetchone()
        # After canonical review the queue input is the reviewed revision,
        # while _verify_prefix is intentionally defined only for live stages
        # 0..4. Verify the first four steps against the analyze output, then
        # separately verify the final sealed review receipt.
        if stage==5:
            if row is None:
                raise ValueError("missing reviewed analysis receipt")
            pending=json.loads(row[0])
            if canonical_digest(pending)!=row[1]:
                raise ValueError("corrupt reviewed analysis receipt")
            self.worker._verify_prefix(
                owner,source_id,4,pending["output_digest"],
                body["url"],source_digest,4_102_444_800)
            final=self.db.execute(
                "SELECT body,digest FROM dragon_almanac_steps "
                "WHERE owner=? AND source=? AND stage=4",
                (owner,source_id)).fetchone()
            if final is None:
                raise ValueError("reviewed stage has no canonical receipt")
            verified=json.loads(final[0])
            if (canonical_digest(verified)!=final[1]
                or verified.get("owner")!=owner
                or verified.get("source_id")!=source_id
                or verified.get("stage")!="canonical_review"
                or verified.get("input_digest")!=pending["output_digest"]
                or verified.get("output_digest")!=input_digest
                or verified.get("training_authorized") is not False
                or state!="reviewed"):
                raise ValueError("canonical review lineage invalid")
        else:
            self.worker._verify_prefix(owner,source_id,stage,input_digest,
                                       body["url"],source_digest,4_102_444_800)
        if row is None:
            raise ValueError("missing analysis receipt")
        stored=json.loads(row[0])
        if canonical_digest(stored)!=row[1]:
            raise ValueError("tampered analysis stage receipt")
        evidence=stored["evidence"]
        packet=evidence["analysis_packet"]
        packet_digest=canonical_digest(packet)
        if (packet_digest!=stored["output_digest"]
            or packet_digest!=evidence["analysis_digest"]
            or packet.get("owner")!=owner or packet.get("source_id")!=source_id
            or packet.get("fact_checked") is not False
            or packet.get("training_authorized") is not False):
            raise ValueError("review handoff identity invalid")
        current=self.captures._history(owner,source_id)
        if not current or packet["capture_digest"] not in {
            x["digest"] for x in current
        }:
            raise ValueError("analysis refers to missing or altered capture")
        # Harmless re-observations with identical content do not invalidate
        # completed review work; a genuinely changed page always does.
        if (current[-1]["content_sha256"]!=packet["content_sha256"]
            or any(x["change"]=="changed"
                   for x in current if x["sequence"] >
                   next(y["sequence"] for y in current
                        if y["digest"]==packet["capture_digest"]))):
            raise ValueError("new capture superseded analysis; reanalyze")
        # The current reviewed library is authoritative; an analysis packet
        # is never equivalent to an accepted ReviewedKnowledgeStore document.
        approved=[
            x for x in self.a.library._rows(owner)
            if x["source_id"]==source_id and x["source_url"]==packet["source_url"]
            and x["source_text_digest"]==packet["content_sha256"]
            and x["status"]=="active" and "design_reference" in x["allowed_scopes"]
        ]
        result={
            "schema":"skeleton.dragon.technical_handoff.v1",
            "owner":owner,"source_id":source_id,
            "analysis_digest":packet_digest,
            "capture_digest":packet["capture_digest"],
            "observed_at":packet["observed_at"],
            "lens_counts":packet["lens_counts"],
            "source_peer_warnings":packet["peer_signals"],
            "unanswered_questions":packet["unanswered_questions"],
            "reviewed_document_matches":len(approved),
            "status":"canonical_wiki_review_verified" if stage==5 else
                     "awaiting_independent_wiki_hoag_review",
            "review_ready":True,"canonical_review_auto_completed":False,
            "weight_promotion_authorized":False,
            "training_authorized":False,
        }
        result["readings"]=(packet["readings"] if include_quotes else [
            {k:v for k,v in x.items() if k!="exact_quote"}
            for x in packet["readings"]
        ])
        return result


    def complete_canonical_review(self,claim:AlmanacClaim,*,capture_digest:str,
                                  brief:KnowledgeBrief,mechanic:str,
                                  wiki_review_digest:str,review_evidence_digest:str,
                                  grant:WisdomGrant,authority:DragonWisdomAuthority,
                                  now:int,authorized:bool,trusted_worker:bool)->dict:
        """Close source work only after a separate, signed accepted Wiki review.

        Wiki review is performed elsewhere by a verified independent principal.
        This adapter never issues a grant, fabricates a reviewed document, or
        provides HOAG model-training authority.
        """
        if not isinstance(claim,AlmanacClaim) or claim.stage!="canonical_review":
            raise ValueError("canonical review-stage claim required")
        _auth(claim.owner,authorized)
        if trusted_worker is not True:
            raise PermissionError("trusted reviewer handoff required")
        _integer(now,"review clock",0,4_102_444_800)
        if (not isinstance(brief,KnowledgeBrief)
            or brief.owner!=claim.owner
            or brief.scope!="design_reference" or brief.conflicts
            or brief.independent_groups<2):
            raise ValueError("fresh two-group conflict-free reviewed brief required")
        if (not isinstance(authority,DragonWisdomAuthority)
            or authority.pyramid.library is not self.a.library):
            raise PermissionError("same-owner signed Wiki authority required")
        if (not isinstance(wiki_review_digest,str) or not _HEX.fullmatch(wiki_review_digest)
            or not isinstance(review_evidence_digest,str)
            or not _HEX.fullmatch(review_evidence_digest)):
            raise ValueError("bounded signed Wiki evidence hashes required")
        if not isinstance(mechanic,str) or not mechanic or len(mechanic)>160:
            raise ValueError("reviewed mechanic required")
        self.a.library.require_fresh_brief(brief,authorized=True)
        authority.verify_grant(
            grant,role="wiki_reviewer",owner=claim.owner,
            target_digest=brief.to_payload()["brief_digest"],now=now)
        events=authority.pyramid._history(claim.owner)
        wiki=authority.pyramid._review(events,wiki_review_digest)
        expected=canonical_digest({
            "review_evidence":review_evidence_digest,
            "grant":grant.digest,
            "brief_digest":brief.to_payload()["brief_digest"],
            "mechanic":mechanic,
        })
        if (wiki["disposition"]!="accepted" or wiki["mechanic"]!=mechanic
            or wiki["reviewer"]!=grant.subject or wiki["review_evidence"]!=expected
            or wiki["knowledge_root"]!=brief.knowledge_root
            or wiki["brief_digest"]!=brief.to_payload()["brief_digest"]
            or wiki["independent_groups"]<2
            or not wiki["at"]<=now<wiki["expires_at"]):
            raise PermissionError("signed accepted Wiki verdict is absent or stale")
        packet=self.handoff(claim.owner,claim.source_id,authorized=True)
        if (packet["review_ready"] is not True
            or packet["analysis_digest"]!=claim.input_digest
            or packet["capture_digest"]!=capture_digest):
            raise ValueError("Wiki approval targets stale or missing source analysis")
        history=self.captures._history(claim.owner,claim.source_id)
        current=next((x for x in history if x["digest"]==capture_digest),None)
        if (current is None or
            history[-1]["content_sha256"]!=current["content_sha256"]):
            raise ValueError("canonical review source capture was superseded")
        docs=[x for x in self.a.library._rows(claim.owner)
              if x["source_id"]==claim.source_id
              and x["source_url"]==current["source_url"]
              and x["source_text_digest"]==current["content_sha256"]
              and x["status"]=="active"
              and "design_reference" in x["allowed_scopes"]]
        if len(docs)!=1:
            raise ValueError("current reviewed source document must match captured text")
        doc=docs[0]
        supports=[h for h in brief.citations
                  if h.source_id==claim.source_id and h.mechanic==mechanic
                  and h.stance=="supports"
                  and h.revision_digest==doc["revision_digest"]
                  and h.source_text_digest==current["content_sha256"]
                  and h.confidence_ppm>=800000]
        if not supports or not any(
            r[0]==claim.source_id and r[1]==doc["revision_digest"]
            and r[2] in {h.note_id for h in supports}
            for r in wiki["source_refs"]
        ):
            raise ValueError("independent Wiki verdict lacks exact source citation")
        evidence={
            "url":claim.url,"input_digest":claim.input_digest,
            "output_digest":doc["revision_digest"],
            "analysis_digest":packet["analysis_digest"],
            "capture_digest":capture_digest,
            "wiki_review_digest":wiki_review_digest,
            "wiki_reviewer_grant_digest":grant.digest,
            "independent_groups":wiki["independent_groups"],
            "human_independent_review":True,
            "model_promotion_authorized":False,
        }
        receipt=self.worker.finish(claim,now=now,
            output_digest=doc["revision_digest"],evidence=evidence,
            authorized=True,trusted_worker=True)
        return {
            "stage":"canonical_review","receipt_digest":receipt,
            "reviewed_source_revision":doc["revision_digest"],
            "wiki_review_digest":wiki_review_digest,
            "next_stage":"reviewed",
            "knowledge_almanac_review_verified":True,
            "hoag_memory_promotion_completed":False,
            "model_training_authorized":False,
        }
