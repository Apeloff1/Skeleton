"""Deterministic inspection of *real PNG pixels* against Jeeves' original canon.

Conservative offline inspection: PNG RGB/RGBA 8-bit noninterlaced only.
Does not infer visual-semantic similarity, authorship, copyright clearance,
animation quality, or model capability. Different renders require reviewed
variants, rather than silently being presented as identical game assets.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
from struct import unpack
import binascii
import zlib

from .story_canon_fabric import (
    StoryCanonError, digest, require, validate_story_bible)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES = 5_000_000
MAX_PIXELS = 1024 * 1024
MAX_RASTER_BYTES = 4 * MAX_PIXELS + 1024
VISUAL_KINDS = frozenset(("character", "environment", "prop", "item",
                          "ability", "animation", "vfx", "ui"))


class AssetPixelError(StoryCanonError):
    """Binary artwork is malformed, unreviewed or visually off canon."""


def _reject(condition, why):
    if not condition:
        raise AssetPixelError(why)


def _png_chunks(data):
    _reject(type(data) is bytes and
            len(PNG_SIGNATURE) + 12 <= len(data) <= MAX_PNG_BYTES and
            data.startswith(PNG_SIGNATURE), "bounded original PNG required")
    off = len(PNG_SIGNATURE)
    while off < len(data):
        _reject(off + 12 <= len(data), "truncated image chunk")
        size = unpack(">I", data[off:off+4])[0]
        kind = data[off+4:off+8]
        off += 8
        _reject(size <= MAX_PNG_BYTES and off+size+4 <= len(data),
                "truncated or oversized PNG chunk")
        payload = data[off:off+size]
        found_crc = unpack(">I", data[off+size:off+size+4])[0]
        _reject((binascii.crc32(kind+payload) & 0xffffffff) == found_crc,
                "artwork chunk CRC damaged")
        off += size+4
        _reject(all(65 <= v <= 90 or 97 <= v <= 122 for v in kind),
                "unsafe PNG chunk type")
        yield kind, payload
        if kind == b"IEND":
            _reject(off == len(data), "trailing unreviewed binary after image")
            return
    raise AssetPixelError("image missing final IEND chunk")


def _unfilter(rows, width, height, pixel_bytes):
    stride = width * pixel_bytes
    _reject(len(rows) == height * (stride + 1),
            "compressed image dimensions disagree with original header")
    previous = bytes(stride)
    for y in range(height):
        start = y * (stride + 1)
        algorithm = rows[start]
        line = bytearray(rows[start+1:start+stride+1])
        _reject(algorithm in (0, 1, 2, 3, 4),
                "unrecognized PNG raster filter")
        for x in range(stride):
            left = line[x-pixel_bytes] if x >= pixel_bytes else 0
            up = previous[x]
            above_left = previous[x-pixel_bytes] if x >= pixel_bytes else 0
            if algorithm == 1:
                predicted = left
            elif algorithm == 2:
                predicted = up
            elif algorithm == 3:
                predicted = (left+up)//2
            elif algorithm == 4:
                estimate = left+up-above_left
                a, b, c = abs(estimate-left), abs(estimate-up), abs(estimate-above_left)
                predicted = left if a <= b and a <= c else up if b <= c else above_left
            else:
                predicted = 0
            line[x] = (line[x]+predicted)&255
        yield bytes(line)
        previous = line


def _decode_pixels(data):
    ihdr = None
    frames = []
    started = ended = False
    previous = None
    for kind, payload in _png_chunks(data):
        if ihdr is None:
            _reject(kind == b"IHDR" and len(payload) == 13,
                    "image header must be the first chunk")
            width,height,bit_depth,color,compression,filtering,interlace = unpack(
                ">IIBBBBB",payload)
            _reject(1 <= width <= 1024 and 1 <= height <= 1024 and
                    width*height <= MAX_PIXELS,
                    "bounded image dimensions or pixel budget exceeded")
            _reject(bit_depth == 8 and color in (2,6) and compression == 0
                    and filtering == 0 and interlace == 0,
                    "only safe noninterlaced RGB or RGBA artwork is supported")
            ihdr=(width,height,3 if color==2 else 4)
        elif kind == b"IDAT":
            _reject(not ended and
                    (previous in (b"IHDR", b"IDAT") or not started),
                    "image data blocks are not contiguous")
            started=True
            frames.append(payload)
        elif kind == b"IEND":
            _reject(started and not payload, "image has no pixel data or malformed ending")
            ended=True
        elif kind[0] & 32 == 0:
            raise AssetPixelError("unrecognized critical PNG control chunk")
        else:
            _reject(not started or previous in (b"IHDR", b"IDAT")
                    or kind not in (b"IDAT",),
                    "unsupported binary chunk")
        previous=kind
    _reject(ihdr is not None and started and ended,
            "image has incomplete source structure")
    width,height,bpp=ihdr
    payload=b"".join(frames)
    _reject(len(payload) <= MAX_PNG_BYTES,"compressed artwork exceeds size budget")
    expected=height*(width*bpp+1)
    _reject(expected <= MAX_RASTER_BYTES,"artwork expansion budget exceeded")
    try:
        stream=zlib.decompressobj()
        result=stream.decompress(payload,expected+1)
        _reject(len(result)==expected and stream.eof
                and not stream.unused_data and not stream.unconsumed_tail,
                "image compression or declared raster size invalid")
        remainder=stream.flush()
        _reject(not remainder, "unreviewed excess decoded pixels")
    except zlib.error as exc:
        raise AssetPixelError("corrupt compressed artwork") from exc
    return width,height,bpp,_unfilter(result,width,height,bpp)


def inspect_png_against_canon(bible, asset_id, data, *, max_channel_delta=0):
    """Check true decoded pixels, original region palette and asset identity."""
    validate_story_bible(bible)
    _reject(type(asset_id) is str and 1 <= len(asset_id) <= 64,
            "exact source asset identity required")
    _reject(type(max_channel_delta) is int and 0 <= max_channel_delta <= 24,
            "artist-controlled channel variation must be bounded")
    asset=next((a for a in bible["assets"] if a["id"]==asset_id),None)
    _reject(asset is not None, "unknown original asset identity")
    _reject(asset["kind"] in VISUAL_KINDS,
            "audio identity requires a separate acoustic source verifier")
    _reject(asset["rights"] == "original_reviewed",
            "unreviewed source assets may not be promoted to a render")
    region=next(r for r in bible["regions"] if r["id"]==asset["region"])
    approved_colors=tuple(
        tuple(int(hex_color[i:i+2],16) for i in (1,3,5))
        for hex_color in asset["palette"])
    _reject(set(asset["palette"]) <= set(region["palette"]),
            "source asset colors disagree with region theme")
    width,height,bpp,rows=_decode_pixels(data)
    visible=0
    deviations=0
    seen_colors=Counter()
    for line in rows:
        for pos in range(0,len(line),bpp):
            rgb=tuple(line[pos:pos+3])
            if bpp==4 and line[pos+3]==0:
                continue
            visible+=1
            seen_colors[rgb]+=1
            distance=min(max(abs(a-b) for a,b in zip(rgb,allowed))
                         for allowed in approved_colors)
            if distance>max_channel_delta:
                deviations+=1
    _reject(visible>0, "rendered original asset has no visible content")
    _reject(deviations == 0,
            "actual PNG pixels violate approved character/region color palette")
    most=seen_colors.most_common(1)[0][0]
    proof={
        "schema":"skeleton.game_builder.original_asset_pixel_receipt.v1",
        "asset":asset_id, "asset_spec_digest":digest(asset),
        "world_bible_digest":bible["digest"],"region":asset["region"],
        "region_palette":region["palette"], "canonical_palette":asset["palette"],
        "binary_sha256":sha256(data).hexdigest(),
        "width":width,"height":height,"channels":bpp,
        "visible_pixels":visible, "distinct_colors":len(seen_colors),
        "dominant_rgb":"#"+"".join(f"{c:02X}" for c in most),
        "allowed_channel_delta":max_channel_delta,
        "actual_palette_mismatch_pixels":deviations,
        "actual_binary_inspected":True,
        "semantic_style_similarity_checked":False,
        "copyright_clearance_proven":False,
        "commercial_release_approved":False,
    }
    return {**proof,"digest":digest(proof)}


def compare_reused_asset(first,last):
    """Exact visual identity lock: scene 500 may not silently recolor scene 1."""
    required={
        "schema","asset","asset_spec_digest","world_bible_digest",
        "region","binary_sha256","width","height","channels",
        "allowed_channel_delta","actual_binary_inspected",
        "copyright_clearance_proven","commercial_release_approved","digest"
    }
    for item in (first,last):
        _reject(type(item) is dict and required <= set(item),
                "real source-pixel proof required")
        _reject(digest({k:v for k,v in item.items() if k!="digest"}) ==
                item["digest"] and item["actual_binary_inspected"] is True,
                "source pixel identity checksum invalid")
    for key in ("asset","asset_spec_digest","world_bible_digest","region",
                "binary_sha256","width","height","channels",
                "allowed_channel_delta"):
        _reject(first[key]==last[key],
                "reused original visual asset changed without a new reviewed identity")
    return {"same_approved_render":True,
            "asset":first["asset"],
            "reference_binary_sha256":first["binary_sha256"],
            "strict_pixel_identity_review":True,
            "copyright_clearance_proven":False}
