from skeleton.automation.advanced_bots import ADVANCED_BOTS
from skeleton.automation.secretary import dispatchable_specialists, route


def test_secretary_knows_every_registered_specialist():
    names = {bot.name for bot in ADVANCED_BOTS}
    assert len(names) == 13
    assert {
        "security-auditor",
        "dependency-guardian",
        "api-contract",
        "release-guardian",
        "feature-builder",
    } <= names


def test_secretary_routes_security_plan_to_security_specialist():
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route("Code scanning reports a CORS authentication vulnerability and SSRF risk", due)
    assert "security-auditor" in selected


def test_secretary_routes_dependency_plan_to_dependency_specialist():
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route("Dependabot found a vulnerable dependency and lockfile needs repair", due)
    assert "dependency-guardian" in selected


def test_secretary_caps_parallel_specialists():
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route("security dependency CI regression performance release API docs coverage", due)
    assert len(selected) <= 3


def test_secretary_routes_exact_build_authority_without_model_keyword_dependency():
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route(
        "routine repository state with no feature keywords",
        due,
        build_authorization=object(),
    )
    assert "feature-builder" in selected


def test_secretary_never_routes_feature_builder_without_build_authority():
    due = [bot.name for bot in ADVANCED_BOTS]
    selected = route(
        "build-approved feature implement enhancement",
        due,
        build_authorization=None,
    )
    assert "feature-builder" not in selected


def test_route_does_not_invent_builder_when_not_in_due_set():
    selected = route(
        "routine repository state",
        [],
        build_authorization=object(),
    )
    assert "feature-builder" not in selected


def test_dispatchable_specialists_keeps_authorized_builder_hot_during_cooldown():
    state = {
        "feature-builder": {
            "name": "feature-builder",
            "enabled": True,
            "failures": 0,
            "last_run": 10**12,
            "circuit_open": False,
        }
    }
    due = dispatchable_specialists(
        state,
        build_authorization=object(),
    )
    assert "feature-builder" in due


def test_dispatchable_specialists_preserves_builder_circuit_breaker():
    state = {
        "feature-builder": {
            "name": "feature-builder",
            "enabled": True,
            "failures": 3,
            "last_run": 0.0,
            "circuit_open": True,
        }
    }
    due = dispatchable_specialists(
        state,
        build_authorization=object(),
    )
    assert "feature-builder" not in due


def test_dispatchable_specialists_does_not_bypass_cooldown_without_authority():
    state = {
        "feature-builder": {
            "name": "feature-builder",
            "enabled": True,
            "failures": 0,
            "last_run": 10**12,
            "circuit_open": False,
        }
    }
    due = dispatchable_specialists(
        state,
        build_authorization=None,
    )
    assert "feature-builder" not in due
