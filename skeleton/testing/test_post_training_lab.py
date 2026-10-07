from __future__ import annotations
import hashlib
from skeleton.training.post_training import *
S=lambda x:hashlib.sha256(x.encode()).hexdigest()
def run():return PostTrainingRun("RUN.POST.1",S("base"),PreferenceDataset("DATASET.PREF.1",S("data"),S("rights")),S("objective"),"ALGO.DPO",S("cfg"))
def test_lineage_binds_data_objective_algorithm_and_base_model():
 r=run();changed=PostTrainingRun(r.run_id,r.base_model_digest,r.dataset,S("other-objective"),r.algorithm_id,r.config_digest);assert r.lineage_digest!=changed.lineage_digest
def test_candidate_without_eval_is_not_qualified_or_production_authorized():
 c=PostTrainingCandidate("CANDIDATE.1",run().lineage_digest,S("model"));assert not c.experimentally_qualified and not c.production_authorized()
def test_eval_evidence_only_qualifies_experiment_not_production():
 c=PostTrainingCandidate("CANDIDATE.1",run().lineage_digest,S("model"),S("eval"));assert c.experimentally_qualified and not c.production_authorized()
def test_dataset_rights_are_part_of_lineage():
 r=run();d=PreferenceDataset(r.dataset.dataset_id,r.dataset.version_digest,S("different-rights"));changed=PostTrainingRun(r.run_id,r.base_model_digest,d,r.objective_digest,r.algorithm_id,r.config_digest);assert r.lineage_digest!=changed.lineage_digest
