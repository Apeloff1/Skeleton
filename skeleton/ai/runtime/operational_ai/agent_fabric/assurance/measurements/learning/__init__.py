"""Approved learning measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('dataset_coverage', 'validation_holdout_fraction', 'contamination_score', 'update_acceptance_ratio', 'replay_coverage', 'calibration_gap', 'distribution_shift_rate', 'reward_hacking_alert_rate', 'training_data_rights_coverage', 'test_isolation_score', 'gradual_promotion_ratio', 'regression_hold_ratio'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.learning.'+name)
    return module.measure(observations)
