"""Approved learning measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('dataset_coverage', 'validation_holdout_fraction', 'contamination_score', 'update_acceptance_ratio', 'replay_coverage', 'calibration_gap', 'distribution_shift_rate', 'reward_hacking_alert_rate', 'training_data_rights_coverage', 'test_isolation_score', 'gradual_promotion_ratio', 'regression_hold_ratio'))
_LOADERS = {
    "dataset_coverage": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.dataset_coverage"),
    "validation_holdout_fraction": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.validation_holdout_fraction"),
    "contamination_score": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.contamination_score"),
    "update_acceptance_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.update_acceptance_ratio"),
    "replay_coverage": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.replay_coverage"),
    "calibration_gap": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.calibration_gap"),
    "distribution_shift_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.distribution_shift_rate"),
    "reward_hacking_alert_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.reward_hacking_alert_rate"),
    "training_data_rights_coverage": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.training_data_rights_coverage"),
    "test_isolation_score": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.test_isolation_score"),
    "gradual_promotion_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.gradual_promotion_ratio"),
    "regression_hold_ratio": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.regression_hold_ratio"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
