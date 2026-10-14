from __future__ import annotations
import pytest
from skeleton.network.architecture import *
Z=(NetworkZone("ZONE.PUBLIC",ZoneKind.PUBLIC),NetworkZone("ZONE.INGRESS",ZoneKind.INGRESS),NetworkZone("ZONE.CONTROL",ZoneKind.CONTROL),NetworkZone("ZONE.DATA",ZoneKind.DATA))
def r(i,s,t):return NetworkRoute(i,s,t,"pinned_resolver",1000,2,True,PartitionMode.FAIL_CLOSED)
def test_public_ingress_and_internal_control_are_explicitly_separated():p=NetworkPolicy(Z,(r("ROUTE.1","ZONE.PUBLIC","ZONE.INGRESS"),r("ROUTE.2","ZONE.INGRESS","ZONE.CONTROL")));assert p.route("ZONE.PUBLIC","ZONE.INGRESS").timeout_ms==1000
def test_public_cannot_route_directly_to_control():
 with pytest.raises(NetworkError,match="bypasses ingress"):NetworkPolicy(Z,(r("ROUTE.BAD","ZONE.PUBLIC","ZONE.CONTROL"),))
def test_public_cannot_route_directly_to_data():
 with pytest.raises(NetworkError,match="bypasses ingress"):NetworkPolicy(Z,(r("ROUTE.BAD","ZONE.PUBLIC","ZONE.DATA"),))
def test_route_requires_bounded_timeout_retry_dns_proxy_and_partition_semantics():x=r("ROUTE.1","ZONE.PUBLIC","ZONE.INGRESS");assert x.dns_policy and x.proxy_required and x.partition_mode is PartitionMode.FAIL_CLOSED and x.max_retries==2
def test_missing_route_fails_closed():
 with pytest.raises(NetworkError,match="absent"):NetworkPolicy(Z,()).route("ZONE.PUBLIC","ZONE.INGRESS")
