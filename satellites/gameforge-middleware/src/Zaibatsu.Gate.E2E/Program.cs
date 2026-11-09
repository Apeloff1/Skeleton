using System.Net.Http.Json;

namespace Zaibatsu.Gate.E2E;

/// <summary>
/// End-to-end gauntlet probe: health, sealed-route refusal, audit head.
/// Runs against a live gate; exits non-zero on any broken contract.
/// </summary>
public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        var baseAddr = args.Length > 0 ? args[0] : "http://localhost:5000";
        using var http = new HttpClient { BaseAddress = new Uri(baseAddr), Timeout = TimeSpan.FromSeconds(10) };
        var failures = 0;

        async Task Check(string name, Func<Task<bool>> probe)
        {
            try
            {
                var ok = await probe();
                Console.WriteLine($"{(ok ? "PASS" : "FAIL")} {name}");
                if (!ok) failures++;
            }
            catch (Exception e)
            {
                Console.WriteLine($"FAIL {name} — {e.Message}");
                failures++;
            }
        }

        await Check("gate health", async () =>
            (await http.GetAsync("/gate/health")).IsSuccessStatusCode);

        await Check("sealed route refuses anonymous", async () =>
            (await http.GetAsync("/api/fabric/fabric/tail")).StatusCode == System.Net.HttpStatusCode.Unauthorized);

        await Check("unwritten route sealed", async () =>
            (await http.GetAsync("/api/nowhere")).StatusCode == System.Net.HttpStatusCode.NotFound);

        await Check("audit head advances", async () =>
        {
            var a = await http.GetFromJsonAsync<AuditHead>("/gate/audit/head");
            await http.GetAsync("/gate/health");
            var b = await http.GetFromJsonAsync<AuditHead>("/gate/audit/head");
            return a is not null && b is not null && b.Seq > a.Seq && b.PrevHash == a.Hash;
        });

        Console.WriteLine(failures == 0 ? "GAUNTLET CLEAR" : $"{failures} FAILURES");
        return failures == 0 ? 0 : 1;
    }

    private sealed record AuditHead(long Seq, string Hash, string PrevHash);
}
