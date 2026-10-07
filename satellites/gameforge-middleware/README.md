# Zaibatsu Gate — C# Middleware for the GameForge Empire

The C# / ASP.NET Core gate that fronts the Rust backend. Fortune-500 /
government grade by construction: every request sealed, bounded, audited
into a hash-chained WORM ledger *before* it proceeds, authenticated by
verifiable credential, and admitted only through a fail-closed policy gate.

## The gauntlet (in order)

1. **RequestSeal** — correlation id minted or sanitized; threads through
   logs, audit, and the proxied request.
2. **BodyBound** — hard request-size ceiling; the empire reads no
   unbounded scrolls.
3. **WormAudit** — hash-chained, fsync'd ledger. Audit failure = request
   refused. Chain verified on startup; a tampered chain stops the gate.
4. **PrincipalAuth** — HMAC-sealed identity (`principal.attester.expiry.sig`
   in `X-Zaibatsu-Seal`); identity is verified, never self-declared.
   mTLS can front this unchanged.
5. **PolicyGate** — route → governance domain; unwritten routes sealed
   (404), sealed routes demand authentication (401). Fail-closed both ways.

Then, and only then, YARP proxies to the Rust spine with active `/ready`
health checks.

## Layout

```
src/
  Zaibatsu.Gate/           the gate itself (one organ per file)
    Audit/WormAuditLog.cs    hash-chained WORM ledger
    Auth/PrincipalAuth.cs    seal authentication + policy map
    Middleware/              the gauntlet pieces, in pipeline order
    Controllers/GateController.cs  gate health / readiness / audit head
  Zaibatsu.Gate.Tests/     hash-chain and policy unit tests
  Zaibatsu.Gate.E2E/       gauntlet probe against a live gate
```

## Run

```bash
dotnet run --project src/Zaibatsu.Gate          # gate on :5000, proxy to rust :8001
dotnet test                                     # unit tests
dotnet run --project src/Zaibatsu.Gate.E2E      # gauntlet probe
```

Config in `appsettings.json`: `Gate:RustBackend`, `Gate:AuditPath`,
`Gate:Keyring` (hex HMAC keys by id), `Gate:MaxBodyBytes`.

## Doctrine

1. Fail-closed everywhere — anything unwritten is sealed.
2. Audit before service — a request we cannot audit is refused.
3. Identity is verified, never self-declared.
4. Bounded by construction — bodies, retries, timeouts, ledger lines.
5. The middleware closes the Rust backend's review findings F4/F5 at the
   edge, while the Rust side fixes them at the core. Two walls, one law.
