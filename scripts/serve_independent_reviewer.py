"""Run independent policy signer on a separately administered TLS host.

Requires independently mounted policy, raw Ed25519 signing key, client CA,
server certificate/key. No default credentials, automatic approvals, model
provider, application DB, forward proxy or outbound HTTP. No request logs.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import os
from pathlib import Path
import socket
import ssl
import sys
from threading import BoundedSemaphore, Timer
import time

from scripts.independent_reviewer_policy import (
    MAX_ATTEST_BODY, MAX_REVIEW_BODY, PolicyDenied, ReviewPolicy, ReviewerPolicySigner, load_signer,
)

_MAX_CONNECTIONS = 8
_CONNECTION_SECONDS = 8.0
_IO_SECONDS = 2.0


def _stop(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


class ReviewHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "IndependentReviewer"
    sys_version = ""

    def log_message(self, *args):
        return None

    def log_error(self, *args):
        return None

    def _answer(self, status, content=b"", content_type="application/octet-stream"):
        self.close_connection = True
        self.send_response_only(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Connection", "close")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if content:
            self.wfile.write(content)

    def send_error(self, code, message=None, explain=None):
        # BaseHTTPRequestHandler otherwise includes raw path/header snippets.
        try:
            self._answer(code)
        except OSError:
            self.close_connection = True

    def handle_expect_100(self):
        self._answer(417)
        return False

    def do_POST(self):
        try:
            if self.command != "POST" or self.request_version != "HTTP/1.1":
                raise PolicyDenied("invalid")
            if self.path == "/v1/review":
                limit, media = MAX_REVIEW_BODY, "application/json"
                invoke = self.server.signer.review
            elif self.path == "/v1/attest":
                limit, media = MAX_ATTEST_BODY, "application/octet-stream"
                invoke = self.server.signer.attest
            else:
                self._answer(404)
                return
            if (self.headers.get_all("Transfer-Encoding") or self.headers.get_all("Expect")
                    or self.headers.get_all("Content-Encoding")):
                raise PolicyDenied("invalid")
            lengths = self.headers.get_all("Content-Length") or []
            types = self.headers.get_all("Content-Type") or []
            if len(lengths) != 1 or len(types) != 1 or types[0] != media:
                raise PolicyDenied("invalid")
            length = lengths[0]
            if not length.isascii() or not length.isdecimal() or len(length) > 8 or not 1 <= int(length) <= limit:
                raise PolicyDenied("invalid")
            # No body bytes are accepted until TLS and pinned cert validation.
            peer = self.connection.getpeercert(binary_form=True)
            if not peer:
                raise PolicyDenied("invalid")
            fingerprint = hashlib.sha256(peer).hexdigest()
            if fingerprint not in self.server.signer.policy.client_certificates:
                raise PolicyDenied("invalid")
            deadline = time.monotonic() + _IO_SECONDS
            remaining = int(length)
            raw = bytearray()
            while remaining:
                if time.monotonic() >= deadline:
                    raise PolicyDenied("invalid")
                block = self.rfile.read1(min(65536, remaining))
                if not block:
                    raise PolicyDenied("invalid")
                raw.extend(block)
                remaining -= len(block)
            if time.monotonic() >= deadline:
                raise PolicyDenied("invalid")
            result = invoke(bytes(raw), fingerprint)
            self._answer(200, result, media if self.path == "/v1/review" else "application/octet-stream")
        except (PolicyDenied, ValueError, OSError, ssl.SSLError):
            self.send_error(403)
        except Exception:
            self.send_error(503)


class BoundedTLSReviewer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = 16
    allow_reuse_address = False

    def __init__(self, address, *, signer, tls, max_connections=_MAX_CONNECTIONS):
        if (type(signer) is not ReviewerPolicySigner or not isinstance(tls, ssl.SSLContext)
                or tls.verify_mode != ssl.CERT_REQUIRED or tls.minimum_version < ssl.TLSVersion.TLSv1_2
                or type(max_connections) is not int or not 1 <= max_connections <= 16):
            raise ValueError("independent reviewer server configuration invalid")
        self.signer, self.tls = signer, tls
        self._slots = BoundedSemaphore(max_connections)
        super().__init__(address, ReviewHandler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            self.shutdown_request(request)
            raise

    def process_request_thread(self, request, client_address):
        conn = request
        timer = None
        try:
            conn.settimeout(_IO_SECONDS)
            conn = self.tls.wrap_socket(conn, server_side=True)
            conn.settimeout(_IO_SECONDS)
            timer = Timer(_CONNECTION_SECONDS, _stop, args=(conn,))
            timer.daemon = True
            timer.start()
            self.finish_request(conn, client_address)
        except Exception:
            pass
        finally:
            if timer is not None:
                timer.cancel()
            self.shutdown_request(conn)
            self._slots.release()

    def handle_error(self, request, client_address):
        return None


def server_tls(*, cert, key, client_ca):
    # Do not allow implicit system trust or env-provided CA roots.
    for path in (cert, key, client_ca):
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("reviewer TLS file invalid")
    if key.stat().st_uid != os.geteuid() or key.stat().st_mode & 0o077:
        raise ValueError("reviewer TLS key permissions invalid")
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.verify_mode = ssl.CERT_REQUIRED
    tls.load_verify_locations(cafile=str(client_ca))
    tls.load_cert_chain(certfile=str(cert), keyfile=str(key))
    return tls


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--policy-sha256", required=True)
    parser.add_argument("--signing-key", required=True, type=Path)
    parser.add_argument("--tls-cert", required=True, type=Path)
    parser.add_argument("--tls-key", required=True, type=Path)
    parser.add_argument("--client-ca", required=True, type=Path)
    parser.add_argument("--replay-database", required=True, type=Path)
    parser.add_argument("--replay-ledger-id", required=True)
    args = parser.parse_args(argv)
    try:
        address = ipaddress.IPv4Address(args.bind)
        if address.is_multicast or address.is_unspecified or not 1 <= args.port <= 65535:
            raise ValueError("explicit IPv4 bind required")
        policy = ReviewPolicy.load(args.policy, args.policy_sha256)
        from scripts.independent_reviewer_replay import DurableReplayLedger
        ledger = DurableReplayLedger(args.replay_database, ledger_id=args.replay_ledger_id,
            authority=policy.authority_id, domain=policy.deployment_domain)
        signer = ReviewerPolicySigner(policy, load_signer(args.signing_key), replay_ledger=ledger)
        tls = server_tls(cert=args.tls_cert, key=args.tls_key, client_ca=args.client_ca)
        with BoundedTLSReviewer((str(address), args.port), signer=signer, tls=tls) as server:
            server.serve_forever(poll_interval=.25)
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        print("Independent reviewer startup denied.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
