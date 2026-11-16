"""Live public publisher dispatch through existing canonical acquisition controls.

Only an exact reviewed registry entry may be selected. No arbitrary URL,
credential handling, alternate target, challenge handling or direct transport.
A user-confirmed queue request does not itself execute network activity.
"""
from __future__ import annotations

from core.dragon_dataset_library import _library, target
from core.dragon_game_corpus import digest

# Explicit finite reviewed connector surface. Registry catalog entries outside
# this set still require ordinary independent operator review.
CONNECTORS = {
    "steam-census-index": "licensed_public_export",
    "eve-sde": "open_dataset_manifest",
    "eve-ref-data": "open_dataset_manifest",
    "wikipedia-dumps": "open_dataset_manifest",
}


def plan_connector(target_id, revision):
    current, _ = _library()
    if revision != current:
        raise ValueError("dataset registry revision changed")
    if not isinstance(target_id, str) or target_id not in CONNECTORS:
        raise ValueError("target has no reviewed connector")
    item = target(target_id)
    if item["access"] != "public_download" or not item["url"].startswith("https://"):
        raise ValueError("connector target unavailable")
    return {"target": target_id, "registry_revision": current,
            "endpoint": item["url"], "method": CONNECTORS[target_id],
            "plan_digest": digest([current,target_id,item["url"],CONNECTORS[target_id]]),
            "network_executed": False, "license_verified": False}


async def queue_connector(app, scope, body, *, principal):
    from core.dragon_crawler import authenticated_scope, CrawlerError
    if (authenticated_scope(principal) != scope or principal.get("role") not in {"editor","admin"}
            or any(body.get(flag) is not True for flag in ("consent","rights_acknowledged",
                "publisher_permission_acknowledged","independent_resource_acknowledged"))):
        raise CrawlerError("crawler_connector_consent","Explicit current publisher permission required.",403)
    if set(body) != {"target","registry_revision","plan_digest","idempotency_key",
            "consent","rights_acknowledged","publisher_permission_acknowledged",
            "independent_resource_acknowledged"}:
        raise ValueError("exact connector command required")
    plan = plan_connector(body["target"],body["registry_revision"])
    if plan["plan_digest"] != body["plan_digest"]:
        raise ValueError("connector plan changed")
    key = body["idempotency_key"]
    if not isinstance(key,str) or not 1<=len(key)<=128 or key.strip()!=key:
        raise ValueError("connector operation identity")
    await app._grant_principal(scope,{"principal_email":principal["email"].strip().lower()})
    session = await app.create_publisher_intake(scope,{
        "endpoint":plan["endpoint"],"method":plan["method"],
        "idempotency_key":"registry-connector:"+digest([plan["plan_digest"],key]),
        "consent":True,"rights_acknowledged":True,
        "publisher_permission_acknowledged":True,"independent_resource_acknowledged":True})
    # The normal run and automation controls remain the only live dispatch
    # entry points. No implicit automated retries or privilege expansion.
    return {**plan,"session":session,"queued":True,"automation_enabled_by_connector":False}
