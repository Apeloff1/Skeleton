"""Security regression tests for the arbitrary-code execution guard."""

from core.exec_guard import execution_policy, production_runtime


def test_execution_is_disabled_by_default():
    policy = execution_policy({})
    assert policy.enabled is False
    assert policy.production is False


def test_development_requires_explicit_opt_in():
    policy = execution_policy({"ALLOW_UNSAFE_CODE_EXECUTION": "true"})
    assert policy.enabled is True
    assert policy.production is False


def test_production_rejects_single_flag_opt_in():
    policy = execution_policy({
        "ALLOW_UNSAFE_CODE_EXECUTION": "true",
        "KUBERNETES_SERVICE_HOST": "10.0.0.1",
    })
    assert policy.enabled is False
    assert policy.production is True
    assert "second risk acknowledgement" in policy.reason


def test_production_requires_two_independent_opt_ins():
    policy = execution_policy({
        "ALLOW_UNSAFE_CODE_EXECUTION": "true",
        "ACKNOWLEDGE_PRODUCTION_RCE_RISK": "true",
        "K_SERVICE": "codedock-api",
    })
    assert policy.enabled is True
    assert policy.production is True


def test_falsey_deploy_marker_does_not_create_production_mode():
    assert production_runtime({"EMERGENT_DEPLOY": "false"}) is False


def test_hosted_runtime_markers_are_fail_closed():
    for marker in ("K_SERVICE", "KUBERNETES_SERVICE_HOST", "DYNO", "WEBSITE_INSTANCE_ID"):
        assert production_runtime({marker: "present"}) is True


def test_truthy_values_are_case_and_whitespace_tolerant():
    policy = execution_policy({"ALLOW_UNSAFE_CODE_EXECUTION": "  YeS  "})
    assert policy.enabled is True
