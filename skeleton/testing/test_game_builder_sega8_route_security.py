"""Adversarial typed original-game replay custody.

All samples are tiny independently authored synthetic state records, not ROMs,
screenshots, commercial assets, or executable hardware-evidence claims.
"""
from __future__ import annotations

from hashlib import sha256
import json

import pytest

from scripts.game_builder.sega8_source_replay import (
    _parse_reference, Sega8HostReplayError,
)


_FIELDS=("level","x","y","health","score","gems_remaining","won","lost","bond_rank")


def reference() -> dict[str,object]:
    initial=dict.fromkeys(_FIELDS,0)
    initial["health"]=4
    step=dict(initial,button="right",x=1,won=1)
    payload={
        "schema":"skeleton.game_builder.sega8_authoritative_host_route.v1",
        "world_digest":"a"*64,
        "source_content_digest":"b"*64,
        "initial":initial,
        "steps":[step],
        "native_cartridge_compiled":False,
        "host_c_executed":False,
        "z80_cpu_emulator_executed":False,
        "physical_hardware_verified":False,
        "release_approved":False,
    }
    payload["route_sha256"]=sha256(json.dumps(
        payload,sort_keys=True,separators=(",", ":"),
    ).encode()).hexdigest()
    return payload


def encoded(data):
    return json.dumps(data,sort_keys=True,separators=(",", ":")).encode()


def resign(payload):
    payload.pop("route_sha256",None)
    payload["route_sha256"]=sha256(encoded(payload)).hexdigest()
    return payload


def test_exact_typed_original_reference_can_be_verified():
    expected=reference()
    assert _parse_reference(encoded(expected))==expected
    assert _parse_reference(encoded(expected))==expected


@pytest.mark.parametrize("where,key,value",[
    ("root","extra_evidence",{"legally_owned":True}),
    ("root","host_c_executed",True),
    ("root","release_approved","false"),
    ("root","physical_hardware_verified",None),
    ("root","z80_cpu_emulator_executed",True),
    ("initial","external_code","unlicensed"),
    ("initial","health",True),
    ("initial","won",2),
    ("initial","won",1),
    ("step","foreign_evidence","synthetic"),
    ("step","health",-1),
    ("step","score",65536),
    ("step","won",2),
    ("step","lost",True),
    ("step","lost",1),
    ("step","button","jump"),
])
def test_signed_digest_alone_cannot_launder_unreviewed_route_fields(
    where,key,value,
):
    item=reference()
    if where=="root":
        item[key]=value
    elif where=="initial":
        item["initial"][key]=value
    else:
        item["steps"][0][key]=value
    resign(item)
    with pytest.raises(Sega8HostReplayError):
        _parse_reference(encoded(item))


@pytest.mark.parametrize("broken",[
    b'{"schema":"a","schema":"b"}',
    b'{"floating":NaN}',
    b'{"infinite":Infinity}',
    b'{"infinite":1e999}',
    b'{"bad":',
    b'\xff',
    b'null',
    b'[]',
])
def test_unsafe_or_ambiguous_json_rejected_before_route_execution(broken):
    with pytest.raises(Sega8HostReplayError):
        _parse_reference(broken)


def test_duplicate_original_source_id_in_valid_looking_route_is_rejected():
    payload=encoded(reference())
    # Duplicate a field inside an otherwise canonical JSON object, even when
    # the last occurrence agrees with the already approved source identity.
    changed=payload.replace(
        b'"world_digest":',b'"world_digest":"a", "world_digest":',1,
    )
    with pytest.raises(Sega8HostReplayError):
        _parse_reference(changed)


def test_empty_route_and_overflow_in_original_controller_route_rejected():
    payload=reference()
    payload["steps"]=[]
    resign(payload)
    with pytest.raises(Sega8HostReplayError):
        _parse_reference(encoded(payload))
    payload=reference()
    payload["steps"][0]["score"]=2**64
    resign(payload)
    with pytest.raises(Sega8HostReplayError):
        _parse_reference(encoded(payload))



def test_original_route_sha256_rejects_modified_or_missing_hash():
    valid=reference()
    valid["route_sha256"]="f"*64
    with pytest.raises(Sega8HostReplayError,match="modified"):
        _parse_reference(encoded(valid))
    valid.pop("route_sha256")
    with pytest.raises(Sega8HostReplayError):
        _parse_reference(encoded(valid))
