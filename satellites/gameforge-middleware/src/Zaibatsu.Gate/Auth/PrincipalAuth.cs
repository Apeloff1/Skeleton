using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using Microsoft.AspNetCore.Authentication;
using Microsoft.Extensions.Options;

namespace Zaibatsu.Gate.Auth;

public static class PrincipalAuthentication
{
    public const string Scheme = "PrincipalSeal";
}

public sealed class PrincipalAuthenticationOptions : AuthenticationSchemeOptions
{
    public Dictionary<string, byte[]> Keyring { get; } = new();
}

public sealed class PrincipalAuthenticationHandler
    : AuthenticationHandler<PrincipalAuthenticationOptions>
{
    public PrincipalAuthenticationHandler(
        IOptionsMonitor<PrincipalAuthenticationOptions> options,
        ILoggerFactory logger,
        UrlEncoder encoder)
        : base(options, logger, encoder)
    {
        var section = Context.RequestServices
            .GetRequiredService<IConfiguration>()
            .GetSection("Gate:Keyring");
        foreach (var child in section.GetChildren())
        {
            if (child.Value is { } hex)
                Options.Keyring[child.Key] = Convert.FromHexString(hex);
        }
    }

    protected override Task<AuthenticateResult> AuthenticateAsync()
    {
        if (!Request.Headers.TryGetValue("X-Zaibatsu-Seal", out var seal) || string.IsNullOrWhiteSpace(seal))
            return Task.FromResult(AuthenticateResult.NoResult());

        var parts = seal.ToString().Split('.', 4);
        if (parts.Length != 4)
            return Task.FromResult(AuthenticateResult.Fail("seal malformed"));

        var (principalId, attesterId, expiryRaw, sigHex) = (parts[0], parts[1], parts[2], parts[3]);
        if (!long.TryParse(expiryRaw, out var expiryUnix))
            return Task.FromResult(AuthenticateResult.Fail("seal expiry unreadable"));
        if (DateTimeOffset.FromUnixTimeSeconds(expiryUnix) < DateTimeOffset.UtcNow)
            return Task.FromResult(AuthenticateResult.Fail("seal expired"));

        byte[] sig;
        try { sig = Convert.FromHexString(sigHex); }
        catch { return Task.FromResult(AuthenticateResult.Fail("seal signature unreadable")); }

        var payload = Encoding.UTF8.GetBytes($"{principalId}.{attesterId}.{expiryRaw}");
        foreach (var key in Options.Keyring.Values)
        {
            var expect = HMACSHA256.HashData(key, payload);
            if (CryptographicOperations.FixedTimeEquals(expect, sig))
            {
                var identity = new ClaimsIdentity(new[]
                {
                    new Claim(ClaimTypes.NameIdentifier, principalId),
                    new Claim("attester", attesterId),
                }, PrincipalAuthentication.Scheme);
                var ticket = new AuthenticationTicket(new ClaimsPrincipal(identity), PrincipalAuthentication.Scheme);
                return Task.FromResult(AuthenticateResult.Success(ticket));
            }
        }
        return Task.FromResult(AuthenticateResult.Fail("seal signature invalid"));
    }
}

public interface IGatePolicy
{
    bool IsOpenRoute(string path);
    string? RequiredDomain(string path);
}

public sealed class GatePolicy : IGatePolicy
{
    private static readonly string[] OpenPrefixes = { "/health", "/ready" };

    private static readonly (string Prefix, string Domain)[] Domains =
    {
        ("/api/fabric", "fabric"),
        ("/api/legions", "legions"),
        ("/api/swarm", "swarm"),
        ("/api/governance", "governance"),
        ("/api/cognition", "cognition"),
        ("/api/lafs", "lafs"),
        ("/api/studio", "studio"),
        ("/api/sagas", "fabric"),
        ("/api/court", "court"),
    };

    public bool IsOpenRoute(string path) =>
        OpenPrefixes.Any(p => path.StartsWith(p, StringComparison.OrdinalIgnoreCase));

    public string? RequiredDomain(string path)
    {
        foreach (var (prefix, domain) in Domains)
            if (path.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                return domain;
        return null;
    }
}
