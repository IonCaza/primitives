# Changelog

## [1.0.1] - 2026-04-04
### Fixed
- Postgres volume mounted at `/var/lib/postgresql` instead of `/var/lib/postgresql/data`, which is the actual `PGDATA` directory in the official image. Data survived `docker compose down` by accident (parent dir includes the subdir) but the mount was non-standard and could cause issues with image variants that set a different `PGDATA`.
  (files: config/docker-compose.yml)

## 1.0.0 -- 2026-03-31

Initial extraction from contributr and uad36.

### Canonical structure

- **Config layer** (5 files): Docker Compose (postgres pgvector/pg18 + redis + backend + frontend), dev compose overlay with hot reload, `.env.example`, `.gitignore`, `Makefile` with test targets.
- **Backend layer** (11 files): FastAPI app with CORS + lifespan + health endpoint, Pydantic Settings, async SQLAlchemy engine/session/Base with auto-commit `get_db`, empty model barrel, Alembic config + env + migration template, conditional-migration entrypoint, prod and dev Dockerfiles, base requirements.
- **Frontend layer** (15 files): Next.js 16 + React 19 + pnpm, Tailwind v4 via PostCSS, shadcn/ui (new-york, neutral base), Geist fonts, combined providers (Theme + QueryClient + Auth stub + Tooltip + Toaster), API client with token refresh infrastructure, root redirect page, multi-stage prod Dockerfile + dev Dockerfile.

### Canonicalization applied

- App name: `MyApp` (global grep-and-replace target).
- DB credentials: `myapp` / `myapp_secret` / `myapp`.
- Primary palette changed from orange (contributr) to neutral gray.
- Removed all domain-specific models, routes, services, and API methods.
- Removed Celery worker (contributr) and MinIO (uad36) -- not universal.
- Removed observability stack (uad36) -- separate `observability` primitive.
- AuthProvider is a pass-through stub; replaced by `authentication` primitive.
- `get_db` includes auto-commit/rollback (uad36 pattern, safer default).
- Single `providers.tsx` file (uad36 pattern) instead of split provider files.
- `api-client.ts` exports infrastructure only (`request`, `buildQuery`, `ApiError`, `getToken`).
- `globals.css` stripped of domain-specific overrides (ADO prose styles, thinking block CSS).
