using Serilog;
using Zaibatsu.Gate.Audit;
using Zaibatsu.Gate.Auth;
using Zaibatsu.Gate.Middleware;

var builder = WebApplication.CreateBuilder(args);

builder.Host.UseSerilog((ctx, cfg) => cfg.ReadFrom.Configuration(ctx.Configuration));

builder.Services.AddControllers();
builder.Services.AddEndpointsApiExplorer();

builder.Services
    .AddReverseProxy()
    .LoadFromConfig(builder.Configuration.GetSection("ReverseProxy"));

builder.Services.AddHttpClient("rust", c =>
{
    c.BaseAddress = new Uri(builder.Configuration["Gate:RustBackend"] ?? "http://localhost:8001");
    c.Timeout = TimeSpan.FromSeconds(10);
});

builder.Services.AddSingleton<IWormAuditLog, WormAuditLog>();
builder.Services.AddSingleton<IGatePolicy, GatePolicy>();

builder.Services
    .AddAuthentication(PrincipalAuthentication.Scheme)
    .AddScheme<PrincipalAuthenticationOptions, PrincipalAuthenticationHandler>(
        PrincipalAuthentication.Scheme, _ => { });

builder.Services.AddAuthorization(options =>
{
    options.FallbackPolicy = new Microsoft.AspNetCore.Authorization.AuthorizationPolicyBuilder()
        .RequireAuthenticatedUser()
        .Build();
});

var app = builder.Build();

app.UseMiddleware<RequestSealMiddleware>();
app.UseMiddleware<BodyBoundMiddleware>();
app.UseMiddleware<WormAuditMiddleware>();
app.UseAuthentication();
app.UseMiddleware<PolicyGateMiddleware>();
app.UseAuthorization();

app.MapControllers();
app.MapReverseProxy();

app.Run();
