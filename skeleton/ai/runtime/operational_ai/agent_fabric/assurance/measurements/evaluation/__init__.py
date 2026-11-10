"""Approved evaluation measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('accuracy', 'precision', 'recall', 'specificity', 'f1', 'balanced_accuracy', 'brier', 'mean_absolute_error', 'false_accept_rate', 'false_reject_rate', 'latency_guard', 'regression_delta'))
def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=import_module('skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.'+name)
    return module.measure(observations)
