# Primitives

Reusable, full-stack building blocks for applications. Each primitive is a self-contained module -- spanning database models, backend services, frontend components, and infrastructure config -- that can be applied to any application built on the same stack.

Primitives are not libraries you `npm install`. They are **canonical source code** extracted from production applications, stripped of domain-specific logic, and packaged with machine-readable metadata and integration guides that AI agents (or humans) can follow to introduce the capability into a new or existing project.

## The Stack

All primitives in this repository target the same technology stack:

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy (async), Alembic, Pydantic Settings |
| Frontend | Next.js 16, React 19, Tailwind CSS v4, shadcn/ui, pnpm |
| Database | PostgreSQL 18 (pgvector), Redis 8 |
| Infrastructure | Docker, Docker Compose |

## Available Primitives

```
cornerstone (root -- no dependencies)
├── authentication
├── agentic-ai-engine
│   ├── presentation-studio
│   └── observability (optional dep)
```

| Primitive | Description | Dependencies |
|---|---|---|
| **cornerstone** | Application scaffold: monorepo structure, Docker Compose orchestration, FastAPI backend skeleton, Next.js frontend skeleton, dev/prod Dockerfiles, API proxy, env management. | None (root) |
| **authentication** | Pluggable auth providers (local + OIDC/OAuth2), MFA (TOTP + email OTP + recovery codes), JWT tokens, Fernet credential vaulting, admin user management, SMTP email, complete login/MFA UI. | None |
| **agentic-ai-engine** | Multi-agent AI with LangGraph supervisor pattern, DB-driven agent config, 3-tier memory, SSE streaming chat, assistant-ui chat interface, LiteLLM integration, self-registering tools, knowledge graphs. | None |
| **observability** | OpenTelemetry SDK + Collector, Grafana Tempo (tracing), Prometheus (metrics), Loki (logs), Grafana (dashboards), LangFuse (LLM tracing). | agentic-ai-engine (optional) |
| **presentation-studio** | AI-powered dashboard generation with React component code in sandboxed iframe, PostMessage data bridge, versioned templates, palette picker, CRUD with version history. | agentic-ai-engine |

## How to Use Primitives

There are four operations: **scaffold**, **apply**, **extract**, and **sync**.

### Scaffold a New Application

The `cornerstone` primitive is different from the others -- it _is_ the application. To start a new project:

1. Create a new directory and initialize git.
2. Copy the cornerstone files into your project, placing `config/` files at the root, `backend/` and `frontend/` as subdirectories.
3. Find-and-replace the placeholders (`MyApp`, `myapp`, `myapp_secret`) with your application's name and credentials.
4. Copy `.env.example` to `.env` and set real secrets.
5. Install shadcn components: `cd frontend && pnpm install && pnpm exec shadcn add button card input label sonner tooltip`
6. Run: `docker compose up --build`

See [`cornerstone/INTEGRATION.md`](cornerstone/INTEGRATION.md) for the full walkthrough.

### Apply a Primitive to an Existing App

Each primitive has an `INTEGRATION.md` with step-by-step instructions. The general pattern:

1. **Read the manifest** (`manifest.yaml`) to understand what the primitive provides -- models, routes, components, extension points.
2. **Follow the integration guide** (`INTEGRATION.md`) section by section:
   - Add database models and create migrations.
   - Copy backend modules, adapting import paths.
   - Register API routers and startup hooks in `main.py`.
   - Add frontend components, hooks, and pages.
   - Wire providers into the app's provider tree.
   - Add API client methods.
   - Merge Docker Compose fragments and environment variables.
3. **Customize the extension points** documented in the manifest -- add your domain-specific agents, tools, prompts, platform integrations, etc.
4. **Create `.primitives.yaml`** in your app root to track what was applied, the file mappings, and your customizations.

### Extract a Primitive from an App

When you've built something reusable, extract it:

1. Identify the files that constitute the primitive across all layers.
2. Read each file and strip domain-specific logic -- keep only the reusable engine/framework code. This is called **canonicalization**.
3. Write the canonical files to a new directory under `~/git/primitives/<name>/`.
4. Create `manifest.yaml`, `INTEGRATION.md`, and `CHANGELOG.md`.
5. Add the primitive to `registry.yaml`.
6. Create `.primitives.yaml` entries in the source application(s) to document the mapping.

### Sync Changes

Primitives evolve as their source applications evolve. Sync goes in two directions:

**App -> Primitive** (contribute improvements back): Diff the app's files against the canonical versions. Changes that are "core improvements" (not domain-specific) get applied to the primitive, bumping its version.

**Primitive -> App** (pull updates into app): Read the `CHANGELOG.md` entries since the installed version. Apply the canonical changes to the app's files, preserving app-specific customizations listed in `.primitives.yaml`.

## Repository Structure

```
primitives/
├── registry.yaml                    # Index of all primitives
├── templates/                       # Scaffolding templates for new primitives
│   ├── manifest.template.yaml
│   ├── INTEGRATION.template.md
│   └── CHANGELOG.template.md
├── cornerstone/                     # Application scaffold (root primitive)
│   ├── manifest.yaml
│   ├── INTEGRATION.md
│   ├── CHANGELOG.md
│   ├── config/                      # docker-compose, .env, .gitignore, Makefile
│   ├── backend/                     # FastAPI app skeleton, Alembic, Dockerfiles
│   └── frontend/                    # Next.js app skeleton, providers, api-client
├── authentication/                  # Auth primitive
│   ├── manifest.yaml
│   ├── INTEGRATION.md
│   ├── CHANGELOG.md
│   ├── schema/                      # User, AuthSettings, OidcProvider, etc.
│   ├── backend/                     # Auth providers, MFA, OIDC, email services
│   ├── frontend/                    # Login, MFA setup, OIDC callback pages
│   └── config/                      # Env vars, docker fragments
├── agentic-ai-engine/              # Multi-agent AI engine
│   ├── manifest.yaml
│   ├── INTEGRATION.md
│   ├── CHANGELOG.md
│   ├── schema/                      # AgentConfig, LlmProvider, ChatSession, etc.
│   ├── backend/                     # Agents, memory, tools, LLM manager, chat API
│   └── frontend/                    # ChatRuntime, ChatPanel, assistant-ui components
├── observability/                   # Telemetry and monitoring stack
│   ├── manifest.yaml
│   ├── INTEGRATION.md
│   ├── CHANGELOG.md
│   ├── backend/                     # OpenTelemetry SDK integration
│   └── config/                      # Collector, Grafana, Tempo, Prometheus, Loki configs
└── presentation-studio/            # AI dashboard generator
    ├── manifest.yaml
    ├── INTEGRATION.md
    ├── CHANGELOG.md
    ├── schema/                      # Presentation, PresentationVersion, Template
    ├── backend/                     # API, agent tools, designer prompt
    ├── frontend/                    # Studio component, sandbox iframe, hooks, pages
    └── config/                      # HTML template, env vars
```

## Anatomy of a Primitive

Every primitive directory contains three required files and organized source code:

### `manifest.yaml`

Machine-readable metadata. An AI agent reads this first to understand what the primitive does.

```yaml
name: authentication
version: "1.0.0"
description: "Full-stack authentication with pluggable providers..."

stack:
  backend: [python, fastapi, sqlalchemy]
  frontend: [react, next.js, shadcn]
  persistence: [postgresql, redis]

provides:
  models: [User, AuthSettings, OidcProvider, ...]
  routes: [POST /auth/login, POST /auth/mfa/verify, ...]
  components: [AuthProvider, LoginPage, MfaSetupDialog, ...]

extension_points:
  - "Platform enum: Override with your app-specific platforms"
  - "Login page icon: Replace Lock with your branding"

extracted_from:
  - repo: contributr
    commit: fab41bb...
    date: "2026-03-31"
```

### `INTEGRATION.md`

Step-by-step instructions for applying the primitive to a target app. Written to be precise enough for an AI agent to follow mechanically: exact file paths, code snippets, import patterns, and adaptation notes.

### `CHANGELOG.md`

Version history with affected file paths. Each entry lists exactly which files changed, enabling incremental sync rather than full re-application.

### Source Code Layers

Code is organized by layer, mirroring how it maps into a target app:

| Directory | Contents |
|---|---|
| `schema/` | SQLAlchemy models and migration helpers |
| `backend/` | Python modules: API routes, services, agents, tools |
| `frontend/` | TypeScript/React: components, hooks, pages, lib utilities |
| `config/` | Docker fragments, env templates, infrastructure configs |

## Tracking: `.primitives.yaml`

Each application that uses primitives has a `.primitives.yaml` file at its root. This is the bridge between the canonical code and the app-specific implementation.

```yaml
primitives_repo: ~/git/primitives

installed:
  authentication:
    version: "1.0.0"
    applied_at: "2026-03-31"
    file_mapping:
      # primitive path: app path
      schema/user.py: backend/app/db/models/user.py
      backend/api/auth.py: backend/app/api/auth.py
      frontend/pages/login/page.tsx: frontend/src/app/(auth)/login/page.tsx
      # ... every file tracked
    customizations:
      - "TOTP issuer is 'MyBrand' instead of generic 'MyApp'"
      - "Login page uses custom BrandIcon instead of Lock"
      - "Platform enum includes GitHub, GitLab, Azure values"
```

**Why this matters**: The file mapping makes sync precise -- the agent knows exactly where each canonical file landed in your app. The customizations list tells the agent what _not_ to overwrite during a sync.

## Design Philosophy

**Canonical code is real code, not templates.** Every file in a primitive is extracted from a production application and canonicalized (domain logic stripped, placeholders standardized). It compiles, it runs, it's the cleanest common version.

**Extension points, not forks.** Primitives provide the engine; your app provides the domain specifics. The `authentication` primitive gives you login flows and MFA -- your app configures which platforms to support and what your login page looks like. The `agentic-ai-engine` gives you the agent framework -- your app defines the domain-specific agents, tools, and prompts.

**AI-agent-first design.** Every file is structured so an AI coding agent can read the manifest, follow the integration guide, and apply the primitive without ambiguity. The metadata is machine-readable YAML, the integration guides are procedural, and the file mappings are explicit.

**Primitives compose.** Start with `cornerstone` for the app skeleton. Layer `authentication` for user management. Add `agentic-ai-engine` for AI capabilities. Stack `presentation-studio` on top for dashboards. Each primitive's `INTEGRATION.md` assumes the prior primitives are in place and documents exactly where to hook in.

## Cursor Skill

The [`manage-primitives`](https://github.com/IonCaza/primitives) Cursor skill automates the four operations. Invoke it by mentioning `/manage-primitives` in Cursor chat:

- `/manage-primitives extract the auth module as a primitive`
- `/manage-primitives apply authentication to this app`
- `/manage-primitives sync agentic-ai-engine from this app`
- `/manage-primitives create a new primitive called notifications`

The skill reads the manifests, follows the integration guides, and updates all tracking files automatically.
