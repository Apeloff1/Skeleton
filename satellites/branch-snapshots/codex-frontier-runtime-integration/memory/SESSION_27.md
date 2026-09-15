# Session 27 (2026-06) — Auto-loop + 10 big wins + 4K-master compare

## Backend (registered=126; all curl-verified 200)
- **Auto-loop to 95** (snowball_improve.py): `POST /api/snowball/{pid}/auto-improve/auto-loop?max_passes=N`
  → bg task loops audit→improve→retry-regen→re-audit until gate≥95 or N passes.
  `GET /api/snowball/auto-loop/{loop_id}` polls status+passes. Verified running (o3 audit + claude regen).
- **Vault inline** (feature 1): `GET /{pid}/vault` (all stages) + `GET /{pid}/vault-digest` (1-line/stage).
- **10 big wins** (snowball_bigwins.py): leaderboard, badge.svg (embeddable), audit/diff,
  audit/stats, ship-checklist, polish-all (mark all stale+regen), vault-digest; plus
  snowball_improve: vault(all), plan.md, auto-loop. All 200.
- **IMPORTANT registry fix:** snowball_bigwins MUST be registered BEFORE snowball in
  core/routes_registry.py — snowball's `/{pid}` catch-all otherwise swallows literal `/leaderboard`.

## Frontend
- /render-compare.tsx: Pane B now shows the **4096px master** (master=true) with a circular
  ActivityIndicator loader overlay; Pane A stays fast 768px preview (master=false). Both panes get
  a "⬇️ Download 4K master" button. (worldforge /render gained `master` bool query param.)
- /scorecard.tsx: "🔁 Auto-loop to 95" button + live pass status; "🧠 Stage knowledge (vault)"
  inline tips section (from /vault-digest).

## Not yet done
- testing_agent e2e pass on Session 27 UI (budget). Backend fully curl-verified; frontend lint clean
  (only harmless `api` default-import + unused `gameId` warnings).
