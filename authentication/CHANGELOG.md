# Authentication Primitive - Changelog

## [1.1.0] - 2026-04-17
### Added
- "Remember this device for 30 days" MFA bypass. When a user ticks the checkbox during MFA verification, the server issues a 30-day opaque trust token. Subsequent logins on that device (same browser/localStorage) skip the MFA challenge entirely. Implemented as a new `TrustedDevice` table storing only SHA-256 hashes of random 32-byte url-safe tokens (raw token never persisted).
  (files: schema/trusted_device.py, schema/user.py, backend/services/trusted_device.py, backend/auth/providers/local.py, backend/api/auth.py, backend/api/mfa.py, frontend/lib/auth-context.tsx, frontend/pages/login/page.tsx)
- Self-service trusted-device management endpoints: `GET /auth/me/trusted-devices`, `DELETE /auth/me/trusted-devices/{id}`, `DELETE /auth/me/trusted-devices` (revoke all).
  (files: backend/api/auth.py)
- `TokenResponse` now optionally carries `trusted_device_token` + `trusted_device_days` when a new trust was established; `LoginRequest` accepts `trusted_device_token` from the client to skip MFA; `MfaVerifyRequest` accepts `remember_device: bool`.
  (files: backend/api/auth.py)

### Changed
- `LocalAuthProvider.authenticate` now reads `trusted_device_token` from the credentials dict and, if it validates against a non-expired `TrustedDevice` row for the authenticating user, skips the MFA challenge.
  (files: backend/auth/providers/local.py)
- All trusted devices for a user are revoked on: self-service password change, forced password change, admin user password update, admin MFA reset, user MFA disable. This keeps the trust-token surface consistent with other security-sensitive events.
  (files: backend/api/auth.py, backend/api/mfa.py)
- `auth-context.tsx` now sends any stored `trusted_device_token` with `login()` and persists the one returned by `verifyMfa()`. The token is intentionally preserved across `logout()` so "Remember me for 30 days" survives explicit sign-out. It is cleared client-side on password-change flows (server also revokes it).
  (files: frontend/lib/auth-context.tsx)
- Login page MFA form grew a "Remember this device for 30 days" checkbox on the TOTP and email tabs (deliberately omitted on the recovery-codes tab since recovery is an emergency flow).
  (files: frontend/pages/login/page.tsx)

### Fixed
- `backend/api/auth.py` now imports `verify_password` from `app.auth.security`, fixing a `NameError` in the self-service `POST /auth/me/password` endpoint that would have thrown at runtime on every call. Pre-existing bug caught while extending this file.
  (files: backend/api/auth.py)

### Migration notes
- Consumers must add a new Alembic migration that creates the `trusted_devices` table with columns: `id` (UUID pk), `user_id` (UUID, FK → users.id ON DELETE CASCADE, indexed), `token_hash` (varchar(64), unique), `device_label`, `user_agent`, `ip_address`, `created_at`, `last_used_at`, `expires_at` (indexed). See `schema/trusted_device.py`.
- Register the new model in your `app/db/models/__init__.py`: `from app.db.models.trusted_device import TrustedDevice`.
- Update the frontend `TokenResponse`, `LoginRequest`, and `MfaVerifyRequest` TypeScript types to match the new fields, and update the API client to send/receive them. See INTEGRATION.md §3.4.
- No action required if you do not use MFA; trusted devices are only ever created during a successful MFA verification.

## 1.0.0 (2026-03-31)

Initial extraction from contributr.

### Backend - Core Auth Module
- `backend/auth/providers/base.py` -- AuthProvider ABC + AuthResult dataclass
- `backend/auth/providers/local.py` -- Local username+password authentication
- `backend/auth/providers/oidc.py` -- OIDC initiate/complete with JIT user provisioning
- `backend/auth/providers/__init__.py` -- Package exports
- `backend/auth/security.py` -- JWT token creation (access, refresh, MFA challenge, MFA setup, password change), bcrypt hashing
- `backend/auth/dependencies.py` -- FastAPI dependencies (get_current_user, require_admin, get_mfa_setup_user, require_mfa_complete)

### Backend - API Routes
- `backend/api/auth.py` -- Login, register, user CRUD, MFA verify, token refresh, password change, /me profile
- `backend/api/mfa.py` -- MFA setup (TOTP init/confirm, email OTP init/confirm, disable, recovery codes)
- `backend/api/oidc_auth.py` -- OIDC authorize redirect + callback with token issuance
- `backend/api/oidc_providers.py` -- Admin CRUD for OIDC providers, discovery, connectivity test
- `backend/api/auth_settings.py` -- Global auth policy (force MFA, enable/disable local login)
- `backend/api/smtp_settings.py` -- SMTP configuration CRUD + test
- `backend/api/email_templates.py` -- Email template CRUD + preview
- `backend/api/platform_credentials.py` -- Encrypted API token vault CRUD + test (generic platform)
- `backend/api/ssh_keys.py` -- SSH key generation (Ed25519/RSA) and management

### Backend - Services
- `backend/services/encryption.py` -- Fernet encryption derived from SECRET_KEY, SSH keypair generation
- `backend/services/mfa.py` -- TOTP (pyotp), email OTP (Redis-backed with cooldown), recovery codes (bcrypt + Fernet)
- `backend/services/oidc.py` -- OIDC discovery, PKCE (S256), token exchange, JWKS caching, ID token validation, claim extraction
- `backend/services/email.py` -- SMTP sending via aiosmtplib, Jinja2 template rendering from DB

### Schema (Database Models)
- `schema/user.py` -- User model with auth_provider, MFA fields, OIDC linkage, must_change_password
- `schema/auth_settings.py` -- Singleton auth policy (force_mfa_local_auth, local_login_enabled)
- `schema/oidc_provider.py` -- OIDC provider config (endpoints, client creds, claim mapping, auto-provision)
- `schema/smtp_settings.py` -- Singleton SMTP config with encrypted password
- `schema/email_template.py` -- Jinja2 email templates with slug, variables, builtin flag
- `schema/platform_credential.py` -- Encrypted API token storage with generic Platform enum
- `schema/ssh_credential.py` -- SSH keypair storage with fingerprint

### Frontend
- `frontend/lib/auth-context.tsx` -- React AuthProvider context (login, logout, MFA flow, token refresh)
- `frontend/components/mfa-setup-dialog.tsx` -- MFA setup dialog (TOTP QR, email OTP, recovery codes)
- `frontend/pages/login/page.tsx` -- Login page with OIDC buttons + local form + inline MFA verify
- `frontend/pages/setup/page.tsx` -- First-run admin account creation
- `frontend/pages/mfa-setup/page.tsx` -- Forced MFA enrollment redirect page
- `frontend/pages/change-password/page.tsx` -- Forced password change page
- `frontend/pages/oidc-callback/page.tsx` -- OIDC callback token extraction

### Config
- `config/env.example` -- Required environment variables
- `config/docker-compose.fragment.yml` -- PostgreSQL + Redis services

### Dependencies
- `backend/requirements.txt` -- Python dependencies
- `frontend/package-deps.json` -- npm dependencies
