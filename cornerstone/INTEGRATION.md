# Cornerstone -- Integration Guide

Unlike other primitives that are _applied into_ an existing application, Cornerstone **is** the application. This guide walks through scaffolding a brand new project from the canonical files.

## Prerequisites

- Docker & Docker Compose
- Python 3.13+
- Node.js 22+ with pnpm
- Git

---

## Step 1: Create the project

```bash
mkdir my-project && cd my-project
git init
```

## Step 2: Copy the cornerstone files

Copy the three layers into your project root, placing them at the correct paths:

```
my-project/
├── docker-compose.yml          # from config/docker-compose.yml
├── docker-compose.dev.yml      # from config/docker-compose.dev.yml
├── .env.example                # from config/.env.example
├── .gitignore                  # from config/.gitignore
├── Makefile                    # from config/Makefile
├── backend/
│   ├── app/
│   │   ├── main.py             # from backend/app/main.py
│   │   ├── config.py           # from backend/app/config.py
│   │   └── db/
│   │       ├── base.py         # from backend/app/db/base.py
│   │       └── models/
│   │           └── __init__.py # from backend/app/db/models/__init__.py
│   ├── alembic.ini             # from backend/alembic.ini
│   ├── alembic/
│   │   ├── env.py              # from backend/alembic/env.py
│   │   └── script.py.mako     # from backend/alembic/script.py.mako
│   ├── entrypoint.sh           # from backend/entrypoint.sh
│   ├── Dockerfile              # from backend/Dockerfile
│   ├── Dockerfile.dev          # from backend/Dockerfile.dev
│   └── requirements.txt        # from backend/requirements.txt
└── frontend/
    ├── package.json            # from frontend/package.json
    ├── next.config.ts          # from frontend/next.config.ts
    ├── postcss.config.mjs      # from frontend/postcss.config.mjs
    ├── components.json         # from frontend/components.json
    ├── tsconfig.json           # from frontend/tsconfig.json
    ├── src/
    │   ├── app/
    │   │   ├── globals.css     # from frontend/src/app/globals.css
    │   │   ├── layout.tsx      # from frontend/src/app/layout.tsx
    │   │   ├── page.tsx        # from frontend/src/app/page.tsx
    │   │   └── providers.tsx   # from frontend/src/app/providers.tsx
    │   └── lib/
    │       ├── theme-provider.tsx  # from frontend/src/lib/theme-provider.tsx
    │       ├── query-client.ts     # from frontend/src/lib/query-client.ts
    │       ├── utils.ts            # from frontend/src/lib/utils.ts
    │       └── api-client.ts       # from frontend/src/lib/api-client.ts
    ├── Dockerfile              # from frontend/Dockerfile
    └── Dockerfile.dev          # from frontend/Dockerfile.dev
```

## Step 3: Personalize

Replace all canonical placeholders with your application's identity:

| Placeholder | Replace with | Files affected |
|---|---|---|
| `MyApp` | Your app name | `main.py`, `config.py`, `layout.tsx` |
| `myapp` | Your DB name | `docker-compose.yml`, `.env.example`, `alembic.ini`, `config.py` |
| `myapp_secret` | Your DB password | `docker-compose.yml`, `.env.example`, `alembic.ini`, `config.py` |
| `MyApp description` | Your description | `layout.tsx` |

Quick sed example:
```bash
# macOS
find . -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.yml" -o -name "*.yaml" -o -name "*.ini" -o -name "*.env*" \) \
  -exec sed -i '' 's/MyApp/Acme/g; s/myapp_secret/s3cret/g; s/myapp/acme/g' {} +
```

## Step 4: Set up environment

```bash
cp .env.example .env
# Edit .env: set real SECRET_KEY and JWT_SECRET (use `openssl rand -hex 32`)
```

## Step 5: Install shadcn components

The `components.json` is pre-configured. Install the UI components you need:

```bash
cd frontend
pnpm install
pnpm exec shadcn add button card input label sonner tooltip
# Add more as needed: dialog, dropdown-menu, table, tabs, etc.
```

## Step 6: Run with Docker Compose

```bash
# Production-like
docker compose up --build

# Development (hot reload)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Verify: `curl http://localhost:8000/api/health` should return `{"status":"ok"}`.

## Step 7: Create your first migration

```bash
cd backend
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

---

## Applying other primitives

Once Cornerstone is scaffolded, apply additional primitives in order:

1. **authentication** -- Replaces the stub `AuthProvider` in `providers.tsx` with real auth flows. Adds user model, auth routes, login/MFA pages.
2. **agentic-ai-engine** -- Adds multi-agent AI, chat interface, LLM provider management.
3. **observability** -- Adds OpenTelemetry, Grafana, Prometheus, Loki, Tempo, Langfuse.
4. **presentation-studio** -- Adds AI-generated dashboards (requires agentic-ai-engine).

Each primitive's `INTEGRATION.md` documents the specific files to copy and adaptations to make.

---

## Extension points

These are the primary files you'll modify as you build features:

### Backend

- **`app/main.py`** -- Add `app.include_router(your_router, prefix="/api")` and lifespan startup hooks.
- **`app/db/models/__init__.py`** -- Import new SQLAlchemy models so Alembic auto-detects them.
- **`app/config.py`** -- Add new `Settings` fields for your feature (they read from env vars automatically).
- **`requirements.txt`** -- Add Python packages.

### Frontend

- **`src/app/providers.tsx`** -- Wrap additional context providers around the app.
- **`src/lib/api-client.ts`** -- Add methods to the `api` object for your domain endpoints.
- **`package.json`** -- Add npm packages.

### Infrastructure

- **`docker-compose.yml`** -- Add services (Celery workers, MinIO, etc.).
- **`.env.example`** -- Document new environment variables.

---

## Design decisions

- **`get_db` auto-commits** -- The async session generator commits on success and rolls back on exception. Route handlers don't need explicit `await db.commit()`.
- **Single `providers.tsx`** -- All React context providers live in one file to minimize import trees and make the provider order explicit.
- **API rewrite proxy** -- `next.config.ts` rewrites `/api/*` to the backend in Docker/dev. `NEXT_PUBLIC_API_URL` is available for direct-access scenarios.
- **Neutral palette** -- `globals.css` uses shadcn neutral base (no branded colors). Override `--primary` and `--ring` in `:root` / `.dark` to brand your app.
- **pgvector image** -- Uses `pgvector/pgvector:pg18-trixie` so the vector extension is available if agentic-ai-engine is applied later. Fully compatible as a standard PostgreSQL instance.
