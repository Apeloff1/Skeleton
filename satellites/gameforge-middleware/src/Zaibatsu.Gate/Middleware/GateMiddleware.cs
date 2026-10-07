using System.Net;
using Zaibatsu.Gate.Audit;
using Zaibatsu.Gate.Auth;

namespace Zaibatsu.Gate.Middleware;

public sealed class RequestSealMiddleware
{
    private readonly RequestDelegate _next;
    public RequestSealMiddleware(RequestDelegate next) => _next = next;

    public async Task InvokeAsync(HttpContext ctx)
    {
        var seal = ctx.Request.Headers.TryGetValue("X-Request-Id", out var supplied)
                     && supplied.ToString() is { Length: > 0 and <= 128 } s
            ? s
            : Guid.NewGuid().ToString("N");
        ctx.Items["Seal"] = seal;
        ctx.Response.Headers["X-Request-Id"] = seal;
        ctx.Request.Headers["X-Request-Id"] = seal;
        await _next(ctx);
    }
}

public sealed class BodyBoundMiddleware
{
    private readonly RequestDelegate _next;
    private readonly long _max;
    public BodyBoundMiddleware(RequestDelegate next, IConfiguration cfg)
    {
        _next = next;
        _max = cfg.GetValue("Gate:MaxBodyBytes", 1_048_576L);
    }

    public async Task InvokeAsync(HttpContext ctx)
    {
        if (ctx.Request.ContentLength > _max)
        {
            ctx.Response.StatusCode = (int)HttpStatusCode.RequestEntityTooLarge;
            await ctx.Response.WriteAsJsonAsync(new { error = "scroll_too_large", limit = _max });
            return;
        }
        ctx.Request.HttpContext.Features.Get<Microsoft.AspNetCore.Http.Features.IHttpMaxRequestBodySizeFeature>()
            ?.Let(f => f.MaxRequestBodySize = _max);
        await _next(ctx);
    }
}

internal static class Maybe
{
    public static void Let<T>(this T? self, Action<T> act) where T : class
    {
        if (self is not null) act(self);
    }
}

public sealed class WormAuditMiddleware
{
    private readonly RequestDelegate _next;
    public WormAuditMiddleware(RequestDelegate next) => _next = next;

    public async Task InvokeAsync(HttpContext ctx, IWormAuditLog audit)
    {
        var seal = ctx.Items["Seal"] as string ?? "unsealed";
        var principal = ctx.User?.Identity?.IsAuthenticated == true
            ? ctx.User.Identity.Name ?? "sealed"
            : "anonymous";
        try
        {
            await audit.AppendAsync(
                kind: "request",
                seal: seal,
                principal: principal,
                route: $"{ctx.Request.Method} {ctx.Request.Path}",
                detail: $"from {ctx.Connection.RemoteIpAddress}");
        }
        catch (Exception)
        {
            ctx.Response.StatusCode = (int)HttpStatusCode.ServiceUnavailable;
            await ctx.Response.WriteAsJsonAsync(new { error = "audit_unavailable" });
            return;
        }
        await _next(ctx);
    }
}

public sealed class PolicyGateMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<PolicyGateMiddleware> _log;
    public PolicyGateMiddleware(RequestDelegate next, ILogger<PolicyGateMiddleware> log)
    {
        _next = next;
        _log = log;
    }

    public async Task InvokeAsync(HttpContext ctx, IGatePolicy policy, IWormAuditLog audit)
    {
        var path = ctx.Request.Path.Value ?? "/";
        if (policy.IsOpenRoute(path))
        {
            await _next(ctx);
            return;
        }

        var domain = policy.RequiredDomain(path);
        var seal = ctx.Items["Seal"] as string ?? "unsealed";
        if (domain is null)
        {
            await audit.AppendAsync("deny", seal, "gate", path, "unwritten route — sealed");
            ctx.Response.StatusCode = (int)HttpStatusCode.NotFound;
            await ctx.Response.WriteAsJsonAsync(new { error = "unwritten_route" });
            return;
        }

        if (ctx.User?.Identity?.IsAuthenticated != true)
        {
            await audit.AppendAsync("deny", seal, "gate", path, $"no seal for domain {domain}");
            ctx.Response.StatusCode = (int)HttpStatusCode.Unauthorized;
            await ctx.Response.WriteAsJsonAsync(new { error = "seal_required", domain });
            return;
        }

        var attester = ctx.User.FindFirst("attester")?.Value ?? "unknown";
        ctx.Request.Headers["X-Zaibatsu-Attester"] = attester;
        _log.LogDebug("gate admitted {Attester} to {Domain} via {Path}", attester, domain, path);
        await _next(ctx);
    }
}
