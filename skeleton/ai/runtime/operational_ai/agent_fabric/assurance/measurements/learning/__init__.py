"""Approved learning measurements and strict local lookup."""
ALLOWED=frozenset(('dataset_coverage', 'validation_holdout_fraction', 'contamination_score', 'update_acceptance_ratio', 'replay_coverage', 'calibration_gap', 'distribution_shift_rate', 'reward_hacking_alert_rate', 'training_data_rights_coverage', 'test_isolation_score', 'gradual_promotion_ratio', 'regression_hold_ratio'))
def measure(name,observations):
    if type(name) is not str or name not in ALLOWED:
        raise ValueError('unknown measurement contract')
    if name == "dataset_coverage":
        from . import dataset_coverage as module
    elif name == "validation_holdout_fraction":
        from . import validation_holdout_fraction as module
    elif name == "contamination_score":
        from . import contamination_score as module
    elif name == "update_acceptance_ratio":
        from . import update_acceptance_ratio as module
    elif name == "replay_coverage":
        from . import replay_coverage as module
    elif name == "calibration_gap":
        from . import calibration_gap as module
    elif name == "distribution_shift_rate":
        from . import distribution_shift_rate as module
    elif name == "reward_hacking_alert_rate":
        from . import reward_hacking_alert_rate as module
    elif name == "training_data_rights_coverage":
        from . import training_data_rights_coverage as module
    elif name == "test_isolation_score":
        from . import test_isolation_score as module
    elif name == "gradual_promotion_ratio":
        from . import gradual_promotion_ratio as module
    elif name == "regression_hold_ratio":
        from . import regression_hold_ratio as module
    else:
        raise ValueError('unknown measurement contract')
    return module.measure(observations)
