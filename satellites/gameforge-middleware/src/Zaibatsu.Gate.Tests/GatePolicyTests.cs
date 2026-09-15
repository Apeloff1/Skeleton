using Zaibatsu.Gate.Auth;
using Xunit;

namespace Zaibatsu.Gate.Tests;

public sealed class GatePolicyTests
{
    private readonly GatePolicy _policy = new();

    [Theory]
    [InlineData("/health", true)]
    [InlineData("/ready", true)]
    [InlineData("/api/fabric/x", false)]
    public void Open_routes_are_health_only(string path, bool open)
        => Assert.Equal(open, _policy.IsOpenRoute(path));

    [Theory]
    [InlineData("/api/fabric/propose", "fabric")]
    [InlineData("/api/legions", "legions")]
    [InlineData("/api/cognition/beliefs", "cognition")]
    [InlineData("/api/nowhere", null)]
    public void Domains_resolve_or_seal(string path, string? domain)
        => Assert.Equal(domain, _policy.RequiredDomain(path));
}
