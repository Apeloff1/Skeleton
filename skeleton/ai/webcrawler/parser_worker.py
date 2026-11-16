"""Private one-shot parser worker; bounded stdin and stdout only.

CPython isolated mode, minimal inherited environment and hard POSIX resource
limits. The audit hook is defense in depth against accidental network and
process creation, not a general-purpose sandbox against compromised native code.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys

MAX_BODY = 2_097_152
MAX_HEADER = 16_384
MAX_OUTPUT = 12 * 1024 * 1024
MAX_MEMORY = 512 * 1024 * 1024


def _limits() -> None:
    if os.name != "posix":
        raise RuntimeError("hard resource limits unavailable")
    import resource
    for kind, value in (
        (resource.RLIMIT_AS, MAX_MEMORY),
        (resource.RLIMIT_CPU, 5),
        (resource.RLIMIT_CORE, 0),
        (resource.RLIMIT_FSIZE, MAX_OUTPUT),
        (resource.RLIMIT_NOFILE, 64),
    ):
        _, hard = resource.getrlimit(kind)
        cap = min(hard, value) if hard != resource.RLIM_INFINITY else value
        resource.setrlimit(kind, (cap, cap))


def _audit(event: str, args: tuple) -> None:
    if (event.startswith("socket.") or event.startswith("subprocess.")
            or event in {"os.system", "os.fork", "os.forkpty", "os.exec",
                         "os.posix_spawn", "os.spawn", "os.kill", "os.killpg",
                         "ctypes.dlopen", "ctypes.dlsym", "os.remove", "os.unlink",
                         "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.chown",
                         "os.chdir", "os.truncate", "os.link", "os.symlink"}):
        raise PermissionError("isolated parser has no external execution authority")
    if event == "open" and len(args) == 3:
        _, _, flags = args
        if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise PermissionError("isolated parser cannot open writable files")


def _receive() -> tuple[dict, bytes]:
    prefix = sys.stdin.buffer.read(4)
    if len(prefix) != 4:
        raise ValueError("invalid parser envelope")
    size = struct.unpack(">I", prefix)[0]
    if not 1 <= size <= MAX_HEADER:
        raise ValueError("invalid parser header bound")
    header = sys.stdin.buffer.read(size)
    if len(header) != size:
        raise ValueError("incomplete parser header")
    meta = json.loads(header.decode("utf-8", errors="strict"))
    if not isinstance(meta, dict) or type(meta.get("body_size")) is not int:
        raise ValueError("malformed parser metadata")
    body_size = meta["body_size"]
    if not 0 <= body_size <= MAX_BODY:
        raise ValueError("invalid parser body bound")
    body = sys.stdin.buffer.read(body_size + 1)
    if len(body) != body_size:
        raise ValueError("invalid parser body length")
    return meta, body


def _parse(meta: dict, body: bytes) -> tuple[str, dict | None]:
    # Only this fixed, installed tree is added to isolated sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from skeleton.ai.webcrawler.core import CrawlPolicy, FetchResponse, extract_document
    from skeleton.ai.webcrawler.structured_discovery import (
        UnsupportedDiscoveryRoot, parse_plaintext_sitemap, parse_structured_discovery,
    )
    sys.addaudithook(_audit)
    mode = meta.get("mode")
    try:
        if mode == "document":
            if set(meta) != {"mode", "url", "canonical_url", "media", "status",
                             "fetched_at", "max_chars", "body_size"}:
                raise ValueError("invalid metadata")
            if (type(meta["max_chars"]) is not int
                    or not 1 <= meta["max_chars"] <= MAX_BODY
                    or meta["media"].split(";", 1)[0].strip().lower() == "application/pdf"):
                raise ValueError("invalid worker document policy")
            response = FetchResponse(meta["url"], meta["status"],
                                     {"content-type": meta["media"]}, body, meta["fetched_at"])
            doc = extract_document(response, meta["canonical_url"],
                                   max_links=256, max_text_chars=meta["max_chars"],
                                   link_base_url=meta["url"])
            if doc is None:
                return "empty", None
            return "ok", {"title": doc.title, "text": doc.text,
                          "links": list(doc.links[:256]),
                          "truncated": doc.provenance.get("parser_text_truncated") is True,
                          "structural_projection": doc.provenance.get("structural_projection")}
        if mode in {"sitemap", "discovery"}:
            if set(meta) != {"mode", "url", "media", "hosts", "max_bytes", "body_size"}:
                raise ValueError("invalid discovery metadata")
            hosts = meta["hosts"]
            if (not isinstance(hosts, list) or not 1 <= len(hosts) <= 16
                    or any(not isinstance(host, str) or len(host) > 253 for host in hosts)
                    or type(meta["max_bytes"]) is not int
                    or not len(body) <= meta["max_bytes"] <= MAX_BODY):
                raise ValueError("invalid worker discovery policy")
            policy = CrawlPolicy(allowed_hosts=frozenset(hosts),
                                 max_response_bytes=meta["max_bytes"])
            if mode == "sitemap":
                item = parse_plaintext_sitemap(body, document_url=meta["url"],
                                               policy=policy, max_links=256, max_entries=1024)
            else:
                item = parse_structured_discovery(body, media_type=meta["media"],
                    document_url=meta["url"], policy=policy, max_links=256, max_entries=1024)
            return "ok", {"kind": item.kind, "links": list(item.links),
                          "examined": item.examined_entries, "discarded": item.discarded_entries,
                          "capped": item.capped}
        raise ValueError("unknown parser mode")
    except UnsupportedDiscoveryRoot:
        return "unsupported", None
    except (ValueError, UnicodeError, OverflowError, RecursionError):
        return "rejected", None


def main() -> int:
    try:
        _limits()
        meta, body = _receive()
        status, payload = _parse(meta, body)
        output = json.dumps({"status": status, "payload": payload}, ensure_ascii=False,
                            allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(output) > MAX_OUTPUT:
            return 2
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
        return 0
    except (Exception, KeyboardInterrupt):
        # Do not expose attacker-controlled exceptions or environment details.
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
