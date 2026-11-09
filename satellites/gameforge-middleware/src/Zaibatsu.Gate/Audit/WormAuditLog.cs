using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Zaibatsu.Gate.Audit;

public sealed record AuditEntry(
    long Seq,
    DateTimeOffset Ts,
    string Kind,
    string Seal,
    string Principal,
    string Route,
    string Detail,
    string PrevHash,
    string Hash);

public interface IWormAuditLog
{
    Task<AuditEntry> AppendAsync(string kind, string seal, string principal, string route, string detail, CancellationToken ct = default);
    AuditEntry? Latest { get; }
}

public sealed class WormAuditLog : IWormAuditLog, IDisposable
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly string _path;
    private readonly ILogger<WormAuditLog> _log;
    private AuditEntry? _latest;
    private long _seq;

    public WormAuditLog(IConfiguration cfg, ILogger<WormAuditLog> log)
    {
        _log = log;
        _path = cfg["Gate:AuditPath"] ?? "audit";
        Directory.CreateDirectory(_path);
        RestoreChain();
    }

    public AuditEntry? Latest => _latest;

    private void RestoreChain()
    {
        var file = Path.Combine(_path, "worm.log");
        if (!File.Exists(file)) return;

        string prevHash = GenesisHash;
        foreach (var line in File.ReadLines(file))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            var entry = JsonSerializer.Deserialize<AuditEntry>(line);
            if (entry is null)
                throw new InvalidOperationException("Audit chain unreadable — refusing to start.");
            if (entry.PrevHash != prevHash || entry.Hash != ComputeHash(entry with { Hash = "" }))
                throw new InvalidOperationException($"Audit chain broken at seq {entry.Seq} — refusing to start.");
            prevHash = entry.Hash;
            _latest = entry;
            _seq = entry.Seq;
        }
        _log.LogInformation("WORM audit chain restored at seq {Seq}", _seq);
    }

    public async Task<AuditEntry> AppendAsync(string kind, string seal, string principal, string route, string detail, CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct);
        try
        {
            var seq = _seq + 1;
            var draft = new AuditEntry(
                Seq: seq,
                Ts: DateTimeOffset.UtcNow,
                Kind: kind,
                Seal: seal,
                Principal: principal,
                Route: route,
                Detail: detail,
                PrevHash: _latest?.Hash ?? GenesisHash,
                Hash: "");
            var entry = draft with { Hash = ComputeHash(draft) };

            var line = JsonSerializer.Serialize(entry) + "\n";
            var file = Path.Combine(_path, "worm.log");
            await File.AppendAllTextAsync(file, line, Encoding.UTF8, ct);
            using var fs = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read);
            fs.Flush(flushToDisk: true);

            _latest = entry;
            _seq = seq;
            return entry;
        }
        finally
        {
            _gate.Release();
        }
    }

    private const string GenesisHash = "GENESIS";

    internal static string ComputeHash(AuditEntry e)
    {
        var payload = $"{e.Seq}|{e.Ts:O}|{e.Kind}|{e.Seal}|{e.Principal}|{e.Route}|{e.Detail}|{e.PrevHash}";
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(payload)));
    }

    public void Dispose() => _gate.Dispose();
}
