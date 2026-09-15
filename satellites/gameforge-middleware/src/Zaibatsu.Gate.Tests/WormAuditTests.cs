using Zaibatsu.Gate.Audit;
using Xunit;

namespace Zaibatsu.Gate.Tests;

public sealed class WormAuditTests
{
    [Fact]
    public void Hash_chain_is_deterministic()
    {
        var e = new AuditEntry(1, DateTimeOffset.UnixEpoch, "request", "s", "p", "r", "d", "GENESIS", "");
        var h1 = WormAuditLog.ComputeHash(e);
        var h2 = WormAuditLog.ComputeHash(e);
        Assert.Equal(h1, h2);
        Assert.Equal(64, h1.Length); // SHA-256 hex
    }

    [Fact]
    public void Hash_changes_with_any_field()
    {
        var e = new AuditEntry(1, DateTimeOffset.UnixEpoch, "request", "s", "p", "r", "d", "GENESIS", "");
        var baseline = WormAuditLog.ComputeHash(e);
        Assert.NotEqual(baseline, WormAuditLog.ComputeHash(e with { Detail = "altered" }));
        Assert.NotEqual(baseline, WormAuditLog.ComputeHash(e with { Seq = 2 }));
        Assert.NotEqual(baseline, WormAuditLog.ComputeHash(e with { PrevHash = "X" }));
    }
}
