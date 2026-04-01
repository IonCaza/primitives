# Authentication Primitive - Integration Guide

This guide walks through integrating the full authentication stack into a
FastAPI + Next.js + PostgreSQL application.

## Prerequisites

- FastAPI backend with SQLAlchemy async (asyncpg driver)
- Next.js frontend with shadcn/ui installed
- PostgreSQL database
- Redis instance (for OIDC state + email OTP cooldown)
- A `SECRET_KEY` environment variable (used to derive Fernet encryption key)
- A `JWT_SECRET` environment variable (used for JWT signing)

## 1. Database Layer (Schema)

### 1.1 Add Models

Copy all model files from `schema/` into your app's models directory:

| Primitive path | Target path |
|---|---|
| `schema/user.py` | `app/db/models/user.py` |
| `schema/auth_settings.py` | `app/db/models/auth_settings.py` |
| `schema/oidc_provider.py` | `app/db/models/oidc_provider.py` |
| `schema/smtp_settings.py` | `app/db/models/smtp_settings.py` |
| `schema/email_template.py` | `app/db/models/email_template.py` |
| `schema/platform_credential.py` | `app/db/models/platform_credential.py` |
| `schema/ssh_credential.py` | `app/db/models/ssh_credential.py` |

**Adaptation notes:**
- Update the `from app.db.base import Base` import in each file to match your
  app's SQLAlchemy Base class location.
- If your app already has a `User` model, merge the auth-related columns into it
  (see `schema/user.py` for the full column set: `auth_provider`, `mfa_enabled`,
  `mfa_method`, `totp_secret_encrypted`, `email_mfa_enabled`,
  `mfa_recovery_codes_encrypted`, `mfa_setup_complete`, `must_change_password`,
  `oidc_provider_id`, `oidc_subject`).
- The `PlatformCredential` model uses a generic `Platform` enum. Replace it with
  your app-specific platform enum (e.g., if you support GitHub/GitLab/Azure,
  define those values). Import path: `from app.db.models.platform_credential import Platform`.
- Register all models in your `app/db/models/__init__.py`:

```python
from app.db.models.user import User
from app.db.models.auth_settings import AuthSettings
from app.db.models.oidc_provider import OidcProvider
from app.db.models.smtp_settings import SmtpSettings
from app.db.models.email_template import EmailTemplate
from app.db.models.platform_credential import PlatformCredential
from app.db.models.ssh_credential import SSHCredential
```

### 1.2 Create Migration

Run Alembic to generate a migration for the new tables:

```bash
alembic revision --autogenerate -m "add authentication tables"
alembic upgrade head
```

Tables created: `users`, `auth_settings`, `oidc_providers`, `smtp_settings`,
`email_templates`, `platform_credentials`, `ssh_credentials`.

### 1.3 Seed Email Templates

The auth system expects at least two email templates to exist in the database:

- **`otp_code`** -- Used for email-based MFA. Variables: `code`, `username`.
- **`user_invite`** -- Used when an admin creates a user with `send_invite=True`.
  Variables: `username`, `email`, `password`, `login_url`.

Create a seed script or Alembic data migration:

```python
from app.db.models.email_template import EmailTemplate

templates = [
    EmailTemplate(
        slug="otp_code",
        name="MFA Verification Code",
        subject="Your verification code: {{ code }}",
        body_html="<p>Hi {{ username }},</p><p>Your verification code is: <strong>{{ code }}</strong></p><p>This code expires in 5 minutes.</p>",
        body_text="Hi {{ username }}, your verification code is: {{ code }}. It expires in 5 minutes.",
        variables={"code": {"description": "6-digit OTP code", "sample": "123456"}, "username": {"description": "User's username", "sample": "jdoe"}},
        is_builtin=True,
    ),
    EmailTemplate(
        slug="user_invite",
        name="User Invitation",
        subject="You've been invited",
        body_html="<p>Hi {{ username }},</p><p>An account has been created for you.</p><p>Email: {{ email }}<br>Password: {{ password }}</p><p><a href=\"{{ login_url }}\">Sign in</a></p>",
        body_text="Hi {{ username }}, an account has been created for you. Email: {{ email }}, Password: {{ password }}. Sign in at: {{ login_url }}",
        variables={"username": {"description": "Username", "sample": "jdoe"}, "email": {"description": "Email", "sample": "j@example.com"}, "password": {"description": "Temporary password", "sample": "••••••"}, "login_url": {"description": "Login URL", "sample": "https://app.example.com/login"}},
        is_builtin=True,
    ),
]
```

## 2. Backend Layer

### 2.1 Add Python Dependencies

Merge dependencies from `backend/requirements.txt` into your app's requirements:

```
bcrypt
cryptography
httpx
PyJWT
pyotp
qrcode[pil]
redis
aiosmtplib
jinja2
```

### 2.2 Copy Backend Modules

| Primitive path | Target path |
|---|---|
| `backend/services/encryption.py` | `app/services/encryption.py` |
| `backend/services/mfa.py` | `app/services/mfa.py` |
| `backend/services/oidc.py` | `app/services/oidc.py` |
| `backend/services/email.py` | `app/services/email.py` |
| `backend/auth/providers/base.py` | `app/auth/providers/base.py` |
| `backend/auth/providers/local.py` | `app/auth/providers/local.py` |
| `backend/auth/providers/oidc.py` | `app/auth/providers/oidc.py` |
| `backend/auth/providers/__init__.py` | `app/auth/providers/__init__.py` |
| `backend/auth/security.py` | `app/auth/security.py` |
| `backend/auth/dependencies.py` | `app/auth/dependencies.py` |
| `backend/api/auth.py` | `app/api/auth.py` |
| `backend/api/mfa.py` | `app/api/mfa.py` |
| `backend/api/oidc_auth.py` | `app/api/oidc_auth.py` |
| `backend/api/oidc_providers.py` | `app/api/oidc_providers.py` |
| `backend/api/auth_settings.py` | `app/api/auth_settings.py` |
| `backend/api/smtp_settings.py` | `app/api/smtp_settings.py` |
| `backend/api/email_templates.py` | `app/api/email_templates.py` |
| `backend/api/platform_credentials.py` | `app/api/platform_credentials.py` |
| `backend/api/ssh_keys.py` | `app/api/ssh_keys.py` |

**Adaptation notes:**
- All files use `from app.` imports. If your package root differs (e.g.,
  `from myapp.`), do a find-and-replace on `from app.` → `from yourpkg.`.
- The `encryption.py` service derives a Fernet key from `settings.secret_key`.
  Ensure your `config.py` / Settings class exposes `secret_key`.
- The `mfa.py` and `oidc.py` services use `settings.redis_url`. Ensure your
  config exposes this.
- The `security.py` module uses `settings.jwt_secret`,
  `settings.jwt_access_token_expire_minutes`, and
  `settings.jwt_refresh_token_expire_days`. Add these to your Settings.
- The `oidc_auth.py` API uses `settings.backend_url` and `settings.frontend_url`
  for OIDC redirect construction. Add these to your Settings.
- The `platform_credentials.py` API imports `Platform` from
  `app.db.models.platform_credential`. If you placed the Platform enum elsewhere,
  update the import.
- The `platform_credentials.py` has a stub `_test_platform_connectivity()`
  function. Implement platform-specific tests for each platform you support.

### 2.3 Register API Routers

In your `main.py` (or wherever you mount FastAPI routers), add:

```python
from app.api.auth import router as auth_router
from app.api.mfa import router as mfa_router
from app.api.oidc_auth import router as oidc_auth_router
from app.api.oidc_providers import router as oidc_providers_router
from app.api.auth_settings import router as auth_settings_router
from app.api.smtp_settings import router as smtp_settings_router
from app.api.email_templates import router as email_templates_router
from app.api.platform_credentials import router as platform_credentials_router
from app.api.ssh_keys import router as ssh_keys_router

app.include_router(auth_router, prefix="/api")
app.include_router(mfa_router, prefix="/api")
app.include_router(oidc_auth_router, prefix="/api")
app.include_router(oidc_providers_router, prefix="/api")
app.include_router(auth_settings_router, prefix="/api")
app.include_router(smtp_settings_router, prefix="/api")
app.include_router(email_templates_router, prefix="/api")
app.include_router(platform_credentials_router, prefix="/api")
app.include_router(ssh_keys_router, prefix="/api")
```

### 2.4 Add Config Settings

Ensure your `config.py` Settings class has:

```python
class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/myapp"
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str = "change-me"
    jwt_secret: str = "change-me"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"
```

### 2.5 Environment Variables

Copy variables from `config/env.example` into your `.env` file and set
appropriate values. **Critical:** `SECRET_KEY` must be consistent across
deployments -- changing it will invalidate all encrypted credentials.

## 3. Frontend Layer

### 3.1 Add npm Dependencies

Ensure these are installed (most are likely already present with shadcn/ui):

```bash
npm install lucide-react
```

Required shadcn/ui components: `Button`, `Card`, `Input`, `Label`, `Tabs`,
`Separator`, `Dialog`. Install any missing ones via `npx shadcn@latest add <name>`.

### 3.2 Copy Frontend Files

| Primitive path | Target path |
|---|---|
| `frontend/lib/auth-context.tsx` | `src/lib/auth-context.tsx` |
| `frontend/components/mfa-setup-dialog.tsx` | `src/components/mfa-setup-dialog.tsx` |
| `frontend/pages/login/page.tsx` | `src/app/(auth)/login/page.tsx` |
| `frontend/pages/setup/page.tsx` | `src/app/(auth)/setup/page.tsx` |
| `frontend/pages/mfa-setup/page.tsx` | `src/app/(auth)/mfa-setup/page.tsx` |
| `frontend/pages/change-password/page.tsx` | `src/app/(auth)/change-password/page.tsx` |
| `frontend/pages/oidc-callback/page.tsx` | `src/app/(auth)/auth/oidc/callback/page.tsx` |

**Adaptation notes:**
- The `auth-context.tsx` imports `api` from `./api-client` and `queryClient`
  from `./query-client`. You need to add the auth-related API methods to your
  app's API client (see section 3.3).
- The login page imports `useAuthProviders` from `@/hooks/use-settings`. You
  need a TanStack Query hook that calls `api.getAuthProviders()`.
- The login page uses `router.push("/dashboard")` after login. Change to your
  app's main authenticated route.
- The setup page uses `router.push("/dashboard")`. Same adaptation.
- The `mfa-setup-dialog.tsx` imports types `MfaTotpInitResponse` from
  `@/lib/types`. Add these types to your app's types file.
- The login page icon is `Lock` from lucide-react. Replace with your app's
  branding icon if desired.
- Create an `(auth)` route group in your Next.js app directory if one doesn't
  exist. Auth pages don't use the dashboard layout.

### 3.3 Add API Client Methods

Add these methods to your API client module. They correspond to the backend
routes registered in step 2.3:

```typescript
// Auth
register: (data) => request<User>("/auth/register", { method: "POST", body: JSON.stringify(data) }),
login: (data) => request<LoginResponse>("/auth/login", { method: "POST", body: JSON.stringify(data) }),
refresh: (rt) => request<TokenResponse>(`/auth/refresh?refresh_token=${rt}`, { method: "POST" }),
me: () => request<User>("/auth/me"),
updateProfile: (data) => request<User>("/auth/me", { method: "PUT", body: JSON.stringify(data) }),
changeOwnPassword: (data) => request<{ detail: string }>("/auth/me/password", { method: "POST", body: JSON.stringify(data) }),
listUsers: () => request<User[]>("/auth/users"),
createUser: (data) => request<User>("/auth/users", { method: "POST", body: JSON.stringify(data) }),
updateUser: (id, data) => request<User>(`/auth/users/${id}`, { method: "PUT", body: JSON.stringify(data) }),
resetUserMfa: (id) => request<User>(`/auth/users/${id}/mfa/reset`, { method: "POST" }),
deleteUser: (id) => request<void>(`/auth/users/${id}`, { method: "DELETE" }),
changePassword: (data) => request<TokenResponse>("/auth/change-password", { method: "POST", body: JSON.stringify(data) }),

// MFA
mfaVerify: (data) => request<TokenResponse>("/auth/mfa/verify", { method: "POST", body: JSON.stringify(data) }),
mfaSendEmailOtp: (data) => request<{ detail: string }>("/auth/mfa/send-email-otp", { method: "POST", body: JSON.stringify(data) }),
mfaSetupOptions: (token?) => { /* pass token as Bearer header */ },
mfaTotpInit: (token?) => { /* pass token as Bearer header */ },
mfaTotpConfirm: (data, token?) => { /* pass token as Bearer header */ },
mfaEmailInit: (token?) => { /* pass token as Bearer header */ },
mfaEmailConfirm: (data, token?) => { /* pass token as Bearer header */ },
mfaDisable: (data) => request<{ detail: string }>("/auth/mfa/disable", { method: "POST", body: JSON.stringify(data) }),
mfaRegenerateRecoveryCodes: (data) => request<RecoveryCodesResponse>("/auth/mfa/recovery-codes", { method: "POST", body: JSON.stringify(data) }),

// SMTP / Email Templates / Auth Settings / OIDC Providers
getSmtpSettings: () => request<SmtpSettings>("/settings/smtp"),
updateSmtpSettings: (data) => request<SmtpSettings>("/settings/smtp", { method: "PUT", body: JSON.stringify(data) }),
testSmtp: (data?) => request<{ detail: string }>("/settings/smtp/test", { method: "POST", body: JSON.stringify(data ?? {}) }),
listEmailTemplates: () => request<EmailTemplate[]>("/settings/email-templates"),
getEmailTemplate: (slug) => request<EmailTemplate>(`/settings/email-templates/${slug}`),
updateEmailTemplate: (slug, data) => request<EmailTemplate>(`/settings/email-templates/${slug}`, { method: "PUT", body: JSON.stringify(data) }),
previewEmailTemplate: (slug, variables?) => request(`/settings/email-templates/${slug}/preview`, { method: "POST", body: JSON.stringify({ variables }) }),
getAuthSettings: () => request<AuthSettingsConfig>("/settings/auth"),
updateAuthSettings: (data) => request<AuthSettingsConfig>("/settings/auth", { method: "PUT", body: JSON.stringify(data) }),
getAuthProviders: () => request<AuthProvidersResponse>("/auth/providers"),
listOidcProviders: () => request<OidcProviderListItem[]>("/settings/oidc-providers"),
getOidcProvider: (id) => request<OidcProvider>(`/settings/oidc-providers/${id}`),
createOidcProvider: (data) => request<OidcProvider>("/settings/oidc-providers", { method: "POST", body: JSON.stringify(data) }),
updateOidcProvider: (id, data) => request<OidcProvider>(`/settings/oidc-providers/${id}`, { method: "PUT", body: JSON.stringify(data) }),
deleteOidcProvider: (id) => request<void>(`/settings/oidc-providers/${id}`, { method: "DELETE" }),
discoverOidcProvider: (id, url) => request(`/settings/oidc-providers/${id}/discover`, { method: "POST", body: JSON.stringify({ discovery_url: url }) }),
discoverOidcNew: (url) => request("/settings/oidc-providers/discover", { method: "POST", body: JSON.stringify({ discovery_url: url }) }),
testOidcProvider: (id) => request(`/settings/oidc-providers/${id}/test`, { method: "POST" }),

// Credential Vault
listPlatformCredentials: () => request<PlatformCredential[]>("/platform-credentials"),
createPlatformCredential: (data) => request<PlatformCredential>("/platform-credentials", { method: "POST", body: JSON.stringify(data) }),
deletePlatformCredential: (id) => request<void>(`/platform-credentials/${id}`, { method: "DELETE" }),
testPlatformCredential: (id) => request(`/platform-credentials/${id}/test`, { method: "POST" }),

// SSH Keys
listSSHKeys: () => request<SSHKey[]>("/ssh-keys"),
createSSHKey: (data) => request<SSHKey>("/ssh-keys", { method: "POST", body: JSON.stringify(data) }),
deleteSSHKey: (id) => request<void>(`/ssh-keys/${id}`, { method: "DELETE" }),
```

### 3.4 Add TypeScript Types

Add these types to your types module:

```typescript
interface User {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  is_admin: boolean;
  is_active: boolean;
  auth_provider: string;
  mfa_enabled: boolean;
  mfa_method: string | null;
  mfa_methods: string[];
  mfa_setup_complete: boolean;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

interface MfaChallengeResponse {
  requires_mfa: boolean;
  mfa_token: string;
  mfa_method: string | null;
  mfa_methods: string[];
}

interface MfaSetupRequiredResponse {
  requires_mfa_setup: boolean;
  mfa_setup_token: string;
}

interface PasswordChangeRequiredResponse {
  password_change_required: boolean;
  password_change_token: string;
}

type LoginResponse = TokenResponse | MfaChallengeResponse | MfaSetupRequiredResponse | PasswordChangeRequiredResponse;

interface MfaTotpInitResponse {
  secret: string;
  provisioning_uri: string;
  qr_code_base64: string;
}

interface MfaSetupCompleteResponse {
  recovery_codes: string[];
  mfa_method: string;
  access_token: string | null;
  refresh_token: string | null;
  token_type: string;
}

interface RecoveryCodesResponse {
  recovery_codes: string[];
}

interface AuthSettingsConfig {
  force_mfa_local_auth: boolean;
  local_login_enabled: boolean;
}

interface AuthProvidersResponse {
  local_login_enabled: boolean;
  oidc_providers: OidcProviderPublicItem[];
}

interface OidcProviderPublicItem {
  slug: string;
  name: string;
  provider_type: string;
}
```

### 3.5 Add useAuthProviders Hook

The login page expects a `useAuthProviders` hook. Add to your hooks file:

```typescript
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api-client";

export function useAuthProviders() {
  return useQuery({
    queryKey: ["auth-providers"],
    queryFn: () => api.getAuthProviders(),
    staleTime: 60_000,
  });
}
```

### 3.6 Wire AuthProvider into Layout

Wrap your app in the `AuthProvider` context. In your root layout or `(auth)` layout:

```tsx
import { AuthProvider } from "@/lib/auth-context";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      {children}
    </AuthProvider>
  );
}
```

### 3.7 Add Token Refresh Logic to API Client

The `auth-context.tsx` expects your API client to support a
`setSessionExpiredHandler(callback)` export that is called when a 401 cannot be
recovered via token refresh. See the canonical `api-client.ts` in contributr for
the full implementation pattern (automatic 401 → refresh → retry).

## 4. Infrastructure

### 4.1 PostgreSQL + Redis

Merge `config/docker-compose.fragment.yml` into your project's docker-compose
if you don't already have PostgreSQL and Redis services.

### 4.2 Next.js API Proxy

Ensure your Next.js `next.config.js` proxies `/api` requests to the FastAPI
backend (or use a reverse proxy like nginx/caddy):

```javascript
async rewrites() {
  return [{ source: "/api/:path*", destination: "http://localhost:8000/api/:path*" }];
}
```

## 5. Post-Integration Checklist

- [ ] Set strong `SECRET_KEY` and `JWT_SECRET` in `.env`
- [ ] Run Alembic migration to create auth tables
- [ ] Seed `otp_code` and `user_invite` email templates
- [ ] Visit `/setup` to create the first admin user
- [ ] Test local login flow at `/login`
- [ ] Configure SMTP in admin settings (required for email MFA and invites)
- [ ] (Optional) Add OIDC providers in admin settings
- [ ] (Optional) Enable forced MFA in auth settings
- [ ] (Optional) Implement platform-specific credential tests
- [ ] (Optional) Replace login page icon with your app's branding
