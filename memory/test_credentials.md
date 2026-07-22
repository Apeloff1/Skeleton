# Test Credentials

## GameForge Studio — RBAC / Auth
- **Enforcement is now ON** (`GAMEFORGE_AUTH_ENFORCE=1`). The `/gameforge-studio` route is gated by a login screen.
- Admin (role=admin): `admin@gameforge.io` / `GameForge#Admin2026`
- Email login: `POST /api/auth/login {email,password}` → returns `access_token` (JWT) + `role`
- Register (viewer): `POST /api/auth/register {email,password}`
- **Google Sign-In (Emergent-managed):** frontend opens `https://auth.emergentagent.com/?redirect=...`, gets a `session_id`, then `POST /api/auth/session {session_id}` → backend verifies with Emergent, upserts user (role=viewer by default), returns opaque `access_token` (7-day session). Stored in expo-secure-store (native) / localStorage (web).
- `POST /api/auth/logout` revokes the Google session (JWTs are stateless).
- Send token as `Authorization: Bearer <token>` on protected endpoints. Backend accepts BOTH JWTs and Google session tokens.
- Guarded endpoints: `/api/gameforge/studio/vault/put` (editor), `/vault/{id}/rollback` (admin),
  `/deploy` (editor), `/git/commit-from-vault` (editor), `/git/push` (admin).
- NOTE: `EmailStr` rejects `.local` TLDs — use real-looking domains (e.g. `@gameforge.io`).
- X (Twitter) sign-in: intentionally deferred (user will supply developer keys later).

## Google test identities
- Any Google account works; first login is provisioned as `viewer`. Promote to editor/admin by
  updating `gameforge_users.role` in Mongo if a test needs write access.

