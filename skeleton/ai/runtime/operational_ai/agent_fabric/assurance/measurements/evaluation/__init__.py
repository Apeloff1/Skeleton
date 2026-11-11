"""Approved evaluation measurements and strict local lookup."""
ALLOWED=frozenset(('accuracy', 'precision', 'recall', 'specificity', 'f1', 'balanced_accuracy', 'brier', 'mean_absolute_error', 'false_accept_rate', 'false_reject_rate', 'latency_guard', 'regression_delta'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "accuracy":
        from . import accuracy as module
    elif name == "precision":
        from . import precision as module
    elif name == "recall":
        from . import recall as module
    elif name == "specificity":
        from . import specificity as module
    elif name == "f1":
        from . import f1 as module
    elif name == "balanced_accuracy":
        from . import balanced_accuracy as module
    elif name == "brier":
        from . import brier as module
    elif name == "mean_absolute_error":
        from . import mean_absolute_error as module
    elif name == "false_accept_rate":
        from . import false_accept_rate as module
    elif name == "false_reject_rate":
        from . import false_reject_rate as module
    elif name == "latency_guard":
        from . import latency_guard as module
    elif name == "regression_delta":
        from . import regression_delta as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
