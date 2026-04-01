# Authentication Primitive - Changelog

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
