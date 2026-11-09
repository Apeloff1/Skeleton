"""Jeeves read-time routing with fresh evidence and safe canary fallback.

All indices must already be independently approved through the durable
Dragon weight vault. The signed freshness ledger supplies a second,
revocable serving fence. The control version is not a magic safe default:
a canary fallback must also pass its own current evidence fence.
"""
from __future__ import annotations
import re
from .dragon_evidence_freshness_ledger import DragonKnowledgeFreshnessLedger
from .dragon_weight_deployment_vault import DragonDurableWeightVault
from .dragon_weight_canary import DragonWeightCanary

_HEX = re.compile(r"[0-9a-f]{64}\Z")


class JeevesFreshnessGuard:
    """Read-only routing façade: bound index, evidence, tenant, and expiry."""

    def __init__(self, vault: DragonDurableWeightVault,
                 ledger: DragonKnowledgeFreshnessLedger,
                 canary: DragonWeightCanary | None = None):
        if (not isinstance(vault, DragonDurableWeightVault)
            or not isinstance(ledger, DragonKnowledgeFreshnessLedger)
            or vault.owner != ledger.owner
            or (canary is not None and (
                not isinstance(canary, DragonWeightCanary)
                or canary.vault is not vault
                or canary.plan.owner != vault.owner))):
            raise TypeError("one canonical owner with existing signed routing custody required")
        self.vault=vault
        self.ledger=ledger
        self.canary=canary

    def _check(self, index: str, bindings: dict, now: int) -> dict:
        if type(index) is not str or not _HEX.fullmatch(index):
            raise ValueError("canonical index identity required")
        binding=bindings.get(index)
        if (type(binding) is not tuple or len(binding)!=2
            or any(type(item) is not str or not _HEX.fullmatch(item)
                   for item in binding)):
            raise PermissionError("trusted index-to-evidence binding absent")
        return self.ledger.require_current(
            binding[0], now=now, index_digest=index,
            source_set_digest=binding[1])

    def route(self, query: str, *, now: int, bindings: dict[str,tuple[str,str]],
              cohort_digest: str | None = None, limit: int = 5) -> dict:
        if (type(query) is not str or len(query)>600
            or type(now) is not int or now<0
            or type(bindings) is not dict or not 1<=len(bindings)<=2
            or type(limit) is not int or not 1<=limit<=20):
            raise ValueError("bounded trusted routing request required")
        if self.canary is None and cohort_digest is not None:
            raise ValueError("unconfigured canary cannot select cohorts")
        if self.canary is not None and (
            type(cohort_digest) is not str or not _HEX.fullmatch(cohort_digest)):
            raise ValueError("privacy-preserving canary cohort digest required")
        before=self.vault.audit()
        if (before.get("owner")!=self.vault.owner
            or before.get("history_verified") is not True
            or before.get("neural_weights_changed") is not False
            or before.get("generation",0)<=0):
            raise PermissionError("durable approved index history required")
        active=before["index_digest"]
        if self.canary is None:
            proof=self._check(active,bindings,now)
            routed=self.vault.route(query,limit=limit,now=now)
            if routed.get("index_digest")!=active:
                raise PermissionError("routing index expired or changed")
            selected=active
            action="approved_active"
        else:
            plan=self.canary.plan
            if plan.candidate_digest!=active:
                raise PermissionError("canary candidate no longer current")
            reviewed=self.canary.audit(now=now)
            if reviewed.get("owner")!=self.vault.owner:
                raise PermissionError("cross-owner canary state")
            control=plan.control_digest
            # A failed candidate never inherits control's validity. Both
            # versions are checked independently against signer-bound source
            # sets, with only reviewed control eligible as a fallback.
            control_proof=self._check(control,bindings,now)
            candidate_ok=True
            try:
                candidate_proof=self._check(active,bindings,now)
            except PermissionError:
                candidate_ok=False
                candidate_proof=None
            if (not candidate_ok or
                reviewed.get("candidate_exposure_permitted") is not True):
                routed=self.vault.route_version(
                    query,index_digest=control,now=now,limit=limit)
                selected=control
                proof=control_proof
                action=("fallback_stale_candidate" if not candidate_ok
                        else "fallback_halted_canary")
            else:
                routed=self.canary.select(
                    query,cohort_digest=cohort_digest,now=now,limit=limit)
                selected=(active if routed.get("candidate_selected") is True
                          else control)
                if routed.get("selected_index_digest")!=selected:
                    raise PermissionError("canary routed different index")
                proof=(candidate_proof if selected==active
                       else control_proof)
                action=("signed_canary" if selected==active
                        else "signed_control_cohort")
        after=self.vault.audit()
        if (after.get("generation")!=before["generation"]
            or after.get("head_digest")!=before["head_digest"]
            or after.get("index_digest")!=active):
            raise PermissionError("concurrent weight activation invalidated routing snapshot")
        # Re-check after routing: a source update could have invalidated the
        # selected release after the first fence read.
        fresh=self._check(selected,bindings,now)
        if fresh["head_mac"]!=proof["head_mac"]:
            raise PermissionError("freshness changed during routing")
        if (routed.get("read_only") is not True
            or routed.get("neural_weights_changed") is not False
            or type(routed.get("bookmarked_retrieval_ids")) is not list):
            raise ValueError("untrusted runtime route result")
        return {
            "schema":"skeleton.jeeves.freshness_guarded_route.v1",
            "owner":self.vault.owner,
            "selected_index_digest":selected,
            "vault_generation":before["generation"],
            "freshness_revision":proof["revision"],
            "freshness_head_mac":proof["head_mac"],
            "route_mode":action,
            "bookmarked_retrieval_ids":routed["bookmarked_retrieval_ids"],
            "full_rollout_authorized":False,
            "read_only":True,
            "neural_weights_changed":False,
            "automated_learning_authorized":False,
        }
