from pathlib import Path
import re

from core.canonical_product_policy import CANONICAL_PRODUCT_POLICY
from core.product_kernel import PRODUCT_KERNEL


CATALOG = Path(__file__).resolve().parents[2] / "frontend" / "src" / "product" / "productCatalog.ts"


def test_canonical_policy_domains_match_product_kernel_capabilities():
    policy_domains = {item.domain for item in CANONICAL_PRODUCT_POLICY}
    kernel_ids = {capability.id for capability in PRODUCT_KERNEL.all()}
    assert policy_domains == kernel_ids


def test_frontend_operation_vocabulary_matches_backend_charter_exactly():
    source = CATALOG.read_text(encoding="utf-8")
    frontend_actions = set(re.findall(r"operation:\s*'([^']+)'", source))
    backend_actions = {
        action
        for domain_policy in CANONICAL_PRODUCT_POLICY
        for action in domain_policy.actions
    }
    assert frontend_actions == backend_actions


def test_every_frontend_capability_routes_through_canonical_surface():
    source = CATALOG.read_text(encoding="utf-8")
    capability_ids = set(re.findall(r"^\s{4}id:\s*'([^']+)',\s*$", source, re.MULTILINE))
    # Top-level capability ids are exactly the ProductKernel vocabulary; action
    # ids are more deeply indented and therefore excluded by the anchored regex.
    assert capability_ids == {capability.id for capability in PRODUCT_KERNEL.all()}
    assert "href: '/hub'" not in source
