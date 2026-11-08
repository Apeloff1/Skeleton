"""Approved evaluation measurements and strict local lookup."""
from importlib import import_module
ALLOWED=frozenset(('accuracy', 'precision', 'recall', 'specificity', 'f1', 'balanced_accuracy', 'brier', 'mean_absolute_error', 'false_accept_rate', 'false_reject_rate', 'latency_guard', 'regression_delta'))
_LOADERS = {
    "accuracy": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.accuracy"),
    "precision": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.precision"),
    "recall": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.recall"),
    "specificity": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.specificity"),
    "f1": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.f1"),
    "balanced_accuracy": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.balanced_accuracy"),
    "brier": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.brier"),
    "mean_absolute_error": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.mean_absolute_error"),
    "false_accept_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.false_accept_rate"),
    "false_reject_rate": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.false_reject_rate"),
    "latency_guard": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.latency_guard"),
    "regression_delta": lambda: import_module("skeleton.ai.runtime.operational_ai.agent_fabric.assurance.measurements.evaluation.regression_delta"),
}

def measure(name,observations):
    if name not in ALLOWED:raise ValueError('unknown measurement contract')
    module=_LOADERS[name]()
    return module.measure(observations)
