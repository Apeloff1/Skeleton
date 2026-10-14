"""Executable provenance-aware cross-source corroboration."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_execution import LayerDispatch
from .dragon_causal_falsification_worker import FalsificationOutcome
from .dragon_source_independence import SourceProvenance,derive_dependency_clusters


@dataclass(frozen=True)
class CorroboratedClaim:
    hypothesis_id:str
    verdict:str
    supporting_clusters:tuple[str,...]
    opposing_clusters:tuple[str,...]
    unresolved_clusters:tuple[str,...]
    corroborated:bool


@dataclass(frozen=True)
class CorroborationOutput:
    receipt:LayerReceipt
    claims:tuple[CorroboratedClaim,...]
    dependency_clusters:int


def execute_cross_source_corroboration(dispatch:LayerDispatch,
    outcomes_by_source:tuple[tuple[str,FalsificationOutcome],...], *,
    falsification_receipt:LayerReceipt,
    provenance:tuple[SourceProvenance,...],authorized:bool,
    minimum_independent_clusters:int=2)->CorroborationOutput:
    if not authorized: raise PermissionError("corroboration requires authorization")
    if dispatch.layer is not AnalysisLayer.CROSS_SOURCE_CORROBORATION:
        raise ValueError("dispatch targets another analysis layer")
    if falsification_receipt.layer is not AnalysisLayer.CAUSAL_FALSIFICATION or not falsification_receipt.passed:
        raise ValueError("accepted falsification receipt required")
    if dispatch.input_fingerprints!=(falsification_receipt.output_fingerprint,):
        raise ValueError("dispatch evidence mismatch")
    if not 2<=minimum_independent_clusters<=1000:
        raise ValueError("invalid corroboration threshold")
    clusters=derive_dependency_clusters(provenance,authorized=True)
    cluster_for={sid:c.cluster_id for c in clusters for sid in c.source_ids}
    grouped={}
    for source_id,outcome in outcomes_by_source:
        if source_id not in cluster_for:
            raise ValueError("falsification source missing provenance")
        grouped.setdefault(outcome.hypothesis_id,{}).setdefault(
            cluster_for[source_id],set()).add(outcome.verdict)
    claims=[]
    for hid,by_cluster in sorted(grouped.items()):
        support=[];oppose=[];unresolved=[]
        for cluster_id,verdicts in sorted(by_cluster.items()):
            # Conflicting reports inside a dependency cluster are one
            # unresolved evidentiary unit, never independent confirmations.
            if verdicts=={"supported"}: support.append(cluster_id)
            elif verdicts=={"refuted"}: oppose.append(cluster_id)
            else: unresolved.append(cluster_id)
        if len(support)>=minimum_independent_clusters and not oppose:
            verdict="supported"
        elif len(oppose)>=minimum_independent_clusters and not support:
            verdict="refuted"
        else: verdict="inconclusive"
        claims.append(CorroboratedClaim(hid,verdict,tuple(support),tuple(oppose),
            tuple(unresolved),verdict!="inconclusive"))
    canonical=[vars(x) for x in claims]
    digest=sha256(json.dumps({"input":dispatch.input_fingerprints,
        "worker":dispatch.worker,"version":dispatch.worker_version,
        "clusters":[(c.cluster_id,c.source_ids,c.reasons) for c in clusters],
        "claims":canonical},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    independent=max((len(x.supporting_clusters) if x.verdict=="supported"
        else len(x.opposing_clusters) if x.verdict=="refuted" else 0 for x in claims),default=0)
    receipt=LayerReceipt(AnalysisLayer.CROSS_SOURCE_CORROBORATION,
        dispatch.input_fingerprints,digest,independent,
        bool(claims) and all(x.corroborated for x in claims),False)
    return CorroborationOutput(receipt,tuple(claims),len(clusters))
