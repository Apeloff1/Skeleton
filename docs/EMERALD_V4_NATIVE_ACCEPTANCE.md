# Emerald V4 actual Unreal and RTX qualification gate

The original native C++ project and tooling are retained inside the independently SHA-pinned `emerald-atelier-fold-source.zip`. This source PR does not copy it into an unqualified Git branch.

Extract the original project into a trusted local folder and obtain all five exact V4 GLB bytes from verified operator bundles. **The installed UE engine, Visual Studio C++ toolchain, Windows host and an NVIDIA RTX device are NOT available in this CI environment.** For real native compilation and skeletal import on the proper machine:

```powershell
pwsh -File scripts/qualify_emerald_unreal_v4.ps1 `
  -EngineRoot 'C:\Program Files\Epic Games\UE_5.5' `
  -Project 'D:\EmeraldFold\Unreal\EmeraldCrawler.uproject' `
  -RepoRoot 'D:\Skeleton' `
  -Assets 'D:\EmeraldV4\Models' `
  -EvidenceDir 'D:\EmeraldV4\Evidence'
```

The procedure validates all five original-donor SHA-256 bytes against the repo manifest; compiles the actual Editor and game targets, runs a real GLB skeletal import under installed Unreal Editor, binds every source animation name to exactly one imported sequence and records a nonce-scoped receipt. The receipt remains **editor import only** and cannot establish a real GPU draw or ray dispatch. The optional `-RequirePhysicalRTX` switch is an intentionally fail-closed gate until independent physical D3D12/RTX traces, frame captures, driver details, image quality, artist acceptance and provenance evidence are supplied.

The native import verifier deliberately treats import receipts as *source-contract-consistent*, not independently cryptographically attested. It does not accept an imported animation count without exact clip-name binding. CI executes syntax and hostile synthetic receipt tests only; it never simulates UE success, RTX, artist approval or delivery.

All five V4 optional equipment models remain disabled pending direct limb/wing clearance. Source and import evidence do not remove that hold, and the original Hoarder pin is not changed.
