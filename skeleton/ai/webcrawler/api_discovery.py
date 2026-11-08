"""Finite API pagination discovery through the existing canonical Dragon worker.

JSON:API, HAL, OData, Hydra and Collection+JSON are *discovery inputs*, not
network clients, API authentication methods, or evidence reviews. Only top-level
pagination relations may nominate URL hints. Embedded records, author links,
schema contexts, attachments, actions and relationship URLs are never followed.

All hints are constrained to the exact original origin and the immutable
CrawlPolicy. The worker subsequently rechecks robots, DNS/socket, consent,
deadline, host delay, grants and cumulative dispatch reservation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from collections.abc import Mapping
from urllib.parse import parse_qsl, urlsplit

from .core import CrawlPolicy, canonicalize_url

API_DISCOVERY_TYPES = frozenset({
    "application/vnd.api+json",
    "application/hal+json",
    "application/odata+json",
    "application/vnd.hydra+json",
    "application/vnd.collection+json",
})
MAX_API_BYTES = 1_048_576
MAX_API_RELATIONS = 64
MAX_API_ITEMS = 1024
_AUTH_QUERY_KEYS = frozenset({
    "access_token", "refresh_token", "id_token", "api_key",
    "apikey", "api-key", "auth", "authorization", "password",
    "secret", "client_secret", "clientsecret", "signature",
    "x-amz-signature", "x-goog-signature", "key", "jwt",
})
_SENSITIVE_QUERY = re.compile(
    r"(?i)(?:^|[_-])(?:secret|password|passwd|api[_-]?key|authorization|bearer|credential|signature)(?:$|[_-])"
)


class APIDiscoveryError(ValueError):
    """Malformed or unbounded API navigation format."""


@dataclass(frozen=True)
class APIPageDiscovery:
    kind: str
    links: tuple[str, ...]
    examined: int
    rejected: int
    capped: bool
    pagination_only: bool = True
    acquired_network: bool = False
    added_authority: bool = False


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, val in pairs:
        if key in result:
            raise APIDiscoveryError("duplicate API discovery object property")
        result[key] = val
    return result


def _nonfinite(value: str):
    raise APIDiscoveryError("non-finite API discovery numeric literal")


def _load(body: bytes) -> dict:
    if type(body) is not bytes or not 0 < len(body) <= MAX_API_BYTES:
        raise APIDiscoveryError("API discovery byte capacity exceeded")
    if body.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00")):
        raise APIDiscoveryError("unsupported API discovery byte encoding")
    try:
        root = json.loads(
            body.decode("utf-8-sig", errors="strict"),
            object_pairs_hook=_unique,
            parse_constant=_nonfinite,
        )
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise APIDiscoveryError("invalid JSON API discovery document") from exc
    if not isinstance(root, dict):
        raise APIDiscoveryError("API discovery root must be an object")
    return root


def _item_count(rows: object) -> int:
    if isinstance(rows, list):
        if len(rows) > MAX_API_ITEMS:
            raise APIDiscoveryError("API collection exceeds item inspection bound")
        return len(rows)
    if isinstance(rows, dict) or rows is None:
        return int(rows is not None)
    raise APIDiscoveryError("invalid API collection root")


def _jsonapi(root: dict) -> tuple[str, list[object], int]:
    if not any(key in root for key in ("data", "errors", "meta")):
        raise APIDiscoveryError("JSON:API document envelope missing")
    version = root.get("jsonapi", {})
    if not isinstance(version, dict):
        raise APIDiscoveryError("invalid JSON:API metadata")
    if "version" in version and version["version"] not in ("1.0", "1.1"):
        raise APIDiscoveryError("unsupported JSON:API version")
    count = _item_count(root.get("data")) if "data" in root else 0
    links = root.get("links")
    if not isinstance(links, dict):
        raise APIDiscoveryError("JSON:API pagination links missing")
    nominated = []
    for key in ("next", "prev"):
        value = links.get(key)
        if isinstance(value, dict):
            # JSON:API link object: URL is in href; meta has no authority.
            value = value.get("href")
        if value is not None:
            nominated.append(value)
    return "jsonapi_pagination", nominated, count


def _hal(root: dict) -> tuple[str, list[object], int]:
    links = root.get("_links")
    if not isinstance(links, dict):
        raise APIDiscoveryError("HAL link-object envelope missing")
    embedded = root.get("_embedded", {})
    if not isinstance(embedded, dict) or len(embedded) > 64:
        raise APIDiscoveryError("invalid HAL embedded-root bound")
    count = 0
    for val in embedded.values():
        if isinstance(val, list):
            count += len(val)
        else:
            count += 1
        if count > MAX_API_ITEMS:
            raise APIDiscoveryError("HAL embedded collection too large")
    nominated = []
    for rel in ("next", "prev"):
        val = links.get(rel)
        if isinstance(val, dict):
            nominated.append(val.get("href"))
        elif val is not None:
            # HAL pagination only via a single link object.
            nominated.append(None)
    return "hal_pagination", nominated, count


def _odata(root: dict) -> tuple[str, list[object], int]:
    count = _item_count(root.get("value")) if "value" in root else 0
    if not any(key.startswith("@odata.") for key in root):
        raise APIDiscoveryError("OData annotation envelope missing")
    nominated = [
        root[key]
        for key in ("@odata.nextLink", "@odata.deltaLink")
        if key in root and key == "@odata.nextLink"
    ]
    return "odata_pagination", nominated, count


def _hydra(root: dict) -> tuple[str, list[object], int]:
    if not any(key in root for key in ("hydra:member", "member", "hydra:view")):
        raise APIDiscoveryError("Hydra collection envelope missing")
    members = root.get("hydra:member", root.get("member", []))
    count = _item_count(members)
    view = root.get("hydra:view")
    if view is not None and not isinstance(view, dict):
        raise APIDiscoveryError("Hydra pagination view must be an object")
    view = view or {}
    nominated = []
    for key in ("hydra:next", "hydra:previous"):
        if key in view:
            nominated.append(view[key])
    return "hydra_pagination", nominated, count


def _collection(root: dict) -> tuple[str, list[object], int]:
    obj = root.get("collection")
    if not isinstance(obj, dict) or obj.get("version") != "1.0":
        raise APIDiscoveryError("Collection+JSON envelope or version invalid")
    count = _item_count(obj.get("items", []))
    relations = obj.get("links", [])
    if not isinstance(relations, list) or len(relations) > MAX_API_RELATIONS:
        raise APIDiscoveryError("Collection+JSON link count exceeded")
    nominated = []
    for val in relations:
        if not isinstance(val, dict):
            raise APIDiscoveryError("invalid Collection+JSON link")
        if val.get("rel") in ("next", "prev"):
            nominated.append(val.get("href"))
    return "collection_json_pagination", nominated, count


_DISPATCH = {
    "application/vnd.api+json": _jsonapi,
    "application/hal+json": _hal,
    "application/odata+json": _odata,
    "application/vnd.hydra+json": _hydra,
    "application/vnd.collection+json": _collection,
}


def discover_api_pages(
    body: bytes, *, media_type: str, document_url: str, policy: CrawlPolicy,
    max_links: int = 16, max_entries: int = 512,
) -> APIPageDiscovery:
    if (not isinstance(policy, CrawlPolicy)
            or media_type not in _DISPATCH
            or type(max_links) is not int or not 1 <= max_links <= 64
            or type(max_entries) is not int or not 1 <= max_entries <= 1024):
        raise APIDiscoveryError("invalid API pagination authority or bounds")
    canonical = canonicalize_url(document_url)
    if canonical != document_url or not policy.admits(canonical):
        raise APIDiscoveryError("API source outside immutable crawl scope")
    origin = urlsplit(canonical)
    data = _load(body)
    kind, raw_links, item_count = _DISPATCH[media_type](data)
    if len(raw_links) > MAX_API_RELATIONS:
        raise APIDiscoveryError("API navigation relations exceed bound")
    if item_count > max_entries:
        raise APIDiscoveryError("API collection item capacity exceeded")
    links = []
    seen = set()
    rejected = 0
    capped = False
    examined = 0
    for value in raw_links:
        examined += 1
        if not isinstance(value, str) or not 1 <= len(value.encode("utf-8")) <= 4096:
            rejected += 1
            continue
        try:
            dest = canonicalize_url(value, base=canonical)
            split = urlsplit(dest)
            if (split.scheme != origin.scheme or split.netloc != origin.netloc
                    or dest == canonical or not policy.admits(dest)
                    or dest in seen):
                raise ValueError("API link is out of authorized origin scope")
            query_names = [k.casefold() for k, _ in parse_qsl(
                split.query, keep_blank_values=True, max_num_fields=256,
            )]
            if any(k in _AUTH_QUERY_KEYS or _SENSITIVE_QUERY.search(k)
                   for k in query_names):
                raise ValueError("API pagination contains credential query keys")
        except (ValueError, UnicodeError):
            rejected += 1
            continue
        if len(links) >= max_links:
            capped = True
            break
        seen.add(dest)
        links.append(dest)
    return APIPageDiscovery(
        kind=kind, links=tuple(links), examined=examined,
        rejected=rejected, capped=capped,
    )
