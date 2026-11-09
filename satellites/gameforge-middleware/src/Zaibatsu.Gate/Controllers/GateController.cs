using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Zaibatsu.Gate.Audit;

namespace Zaibatsu.Gate.Controllers;

[ApiController]
[AllowAnonymous]
public sealed class GateController : ControllerBase
{
    private readonly IWormAuditLog _audit;
    private readonly IHttpClientFactory _http;

    public GateController(IWormAuditLog audit, IHttpClientFactory http)
    {
        _audit = audit;
        _http = http;
    }

    [HttpGet("/gate/health")]
    public IActionResult Health() => Ok(new
    {
        status = "ok",
        gate = "zaibatsu",
        auditSeq = _audit.Latest?.Seq ?? 0,
    });

    [HttpGet("/gate/ready")]
    public async Task<IActionResult> Ready(CancellationToken ct)
    {
        var client = _http.CreateClient("rust");
        try
        {
            var rust = await client.GetAsync("/ready", ct);
            return Ok(new
            {
                ready = rust.IsSuccessStatusCode,
                rust = (int)rust.StatusCode,
                auditSeq = _audit.Latest?.Seq ?? 0,
            });
        }
        catch (Exception)
        {
            return StatusCode(503, new { ready = false, rust = "unreachable" });
        }
    }

    [HttpGet("/gate/audit/head")]
    public IActionResult AuditHead() => Ok(_audit.Latest);
}
