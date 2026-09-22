"""Throughput request_pipeline pack tests."""

from __future__ import annotations

from skeleton.request_pipeline.catalog import PIPELINE_CATALOG, describe_catalog
from skeleton.request_pipeline.evidence import digest_plane, render_evidence
from skeleton.request_pipeline.filters import FilterChain, FilterVerdict, run_filters
from skeleton.request_pipeline.operations import digest_registry, playbook_smoke, registry, validate_plan
from skeleton.request_pipeline.pipeline import default_pipeline, run_pipeline_dry
from skeleton.request_pipeline.principal import bind_principal, mint_principal_token, verify_principal_token
from skeleton.request_pipeline.scopes import evaluate_role, evaluate_scope


def test_default_pipeline_stages():
    names = default_pipeline().names()
    assert "authenticate" in names
    assert "authorize" in names
    assert "admit_write" in names


def test_principal_token_roundtrip():
    tok = mint_principal_token("alice", secret="s3cret", ttl_secs=120)
    assert tok
    p = verify_principal_token(tok, secret="s3cret")
    assert p is not None and p.name == "alice"
    assert verify_principal_token(tok, secret="wrong") is None


def test_scope_and_role():
    p = bind_principal("op", roles=("operator",), scopes=("read", "write"))
    assert evaluate_scope(p, ("write",))["ok"] is True
    assert evaluate_scope(p, ("admin",))["ok"] is False
    assert evaluate_role(p, ("admin", "operator"))["ok"] is True


def test_pipeline_dry_authz_fail():
    p = bind_principal("guest", roles=("guest",), scopes=("read",))
    out = run_pipeline_dry(path="/api/v1/forge/x", method="POST", principal=p, required_scopes=("write",))
    assert out["ok"] is False
    assert out["failed_at"] == "authorize"


def test_filters_deny_huge_body():
    chain = FilterChain(name="t", max_body_bytes=100)
    r = run_filters(chain, headers={"user-agent": "x"}, content_length=1000)
    assert r.verdict is FilterVerdict.DENY


def test_catalog_and_registry():
    assert len(PIPELINE_CATALOG) >= 100
    assert len(describe_catalog()) == len(PIPELINE_CATALOG)
    reg = registry()
    assert len(reg) >= 100
    plan = next(iter(reg.values()))()
    assert validate_plan(plan)["ok"] is True
    assert len(digest_registry()) == 64


def test_playbook_and_evidence():
    smoke = playbook_smoke()
    assert smoke["dry"]["ok"] is True
    assert smoke["filter"]["verdict"] == "allow"
    a = digest_plane()
    assert a == digest_plane()
    ev = render_evidence()
    assert ev.stages >= 5
    assert ev.catalog >= 100

# --- sampled registry plans ---

def test_registry_plan_forge_get_0():
    plan = registry()["forge.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_forge_post_0():
    plan = registry()["forge.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_gameforge_get_0():
    plan = registry()["gameforge.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_gameforge_post_0():
    plan = registry()["gameforge.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_swarm_get_0():
    plan = registry()["swarm.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_swarm_post_0():
    plan = registry()["swarm.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_jeeves_get_0():
    plan = registry()["jeeves.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_jeeves_post_0():
    plan = registry()["jeeves.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_memory_get_0():
    plan = registry()["memory.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_memory_post_0():
    plan = registry()["memory.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_retrieval_get_0():
    plan = registry()["retrieval.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_retrieval_post_0():
    plan = registry()["retrieval.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_pipeline_get_0():
    plan = registry()["pipeline.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_pipeline_post_0():
    plan = registry()["pipeline.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_intelligence_get_0():
    plan = registry()["intelligence.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_intelligence_post_0():
    plan = registry()["intelligence.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_resilience_get_0():
    plan = registry()["resilience.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_resilience_post_0():
    plan = registry()["resilience.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_context_get_0():
    plan = registry()["context.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_context_post_0():
    plan = registry()["context.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_ledger_get_0():
    plan = registry()["ledger.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_ledger_post_0():
    plan = registry()["ledger.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_scheduler_get_0():
    plan = registry()["scheduler.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_scheduler_post_0():
    plan = registry()["scheduler.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_genesis_get_0():
    plan = registry()["genesis.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_genesis_post_0():
    plan = registry()["genesis.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_capabilities_get_0():
    plan = registry()["capabilities.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_capabilities_post_0():
    plan = registry()["capabilities.post.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_interface_get_0():
    plan = registry()["interface.get.0"]()
    assert validate_plan(plan)["ok"] is True

def test_registry_plan_interface_post_0():
    plan = registry()["interface.post.0"]()
    assert validate_plan(plan)["ok"] is True

