---
name: manage-primitives
description: >-
  Extract, apply, sync, and create full-stack reusable primitives across
  React/Python/Postgres applications. Use when the user mentions primitives,
  asks to extract shared code into a primitive, apply a primitive to an app,
  sync primitive changes, or create a new primitive.
---

# Manage Primitives

Primitives are AI-agent-readable, full-stack reusable components. Each primitive
contains canonical code, a manifest, and an integration guide spanning database
models, backend modules, frontend components, and infrastructure config.

**Primitives repo**: `~/git/primitives/`
**Tracking file**: `.primitives.yaml` in each application root

## Core Concepts

- **Primitive**: A directory in the primitives repo containing `manifest.yaml`,
  `INTEGRATION.md`, `CHANGELOG.md`, and canonical source code organized by layer
  (schema/, backend/, frontend/, config/).
- **manifest.yaml**: Machine-readable metadata -- name, version, stack, what it
  provides (models, routes, components), extension points, extraction provenance.
- **INTEGRATION.md**: Step-by-step guide an AI agent follows to introduce the
  primitive into a target app. Includes canonical code and adaptation notes.
- **CHANGELOG.md**: Versioned log of changes with affected file paths, used for
  incremental sync.
- **.primitives.yaml**: Per-app tracking file mapping primitive files to their
  locations in the app, plus version and customization notes.

## Commands

### 1. Extract

**Trigger**: User says "extract the X primitive from this app" or similar.

**Workflow**:

1. Read the current app's structure to identify files belonging to the primitive.
   Use the `manifest.yaml` file list if the primitive already exists, or ask the
   user which files/modules constitute the primitive if creating from scratch.
2. Read `~/git/primitives/<name>/manifest.yaml` if it exists. If not, scaffold
   from `~/git/primitives/templates/manifest.template.yaml`.
3. For each file in the primitive scope:
   a. Read the source file from the app.
   b. Strip domain-specific customizations (e.g., app-specific tool categories,
      domain agents). Keep only the reusable core engine/framework code.
   c. Write the canonical version to the primitive directory, preserving the
      layer-based structure (schema/, backend/, frontend/, config/).
4. If the primitive already had code, diff the old vs new canonical versions.
   Summarize what changed.
5. Update `CHANGELOG.md` with a new version entry listing affected files.
6. Update `manifest.yaml`: bump version, update `extracted_from` with the source
   repo name, current commit SHA, and today's date.
7. Write or update `INTEGRATION.md` based on how the code is actually structured.
   For each layer, document: what to copy, what imports/paths to adapt, what
   startup hooks to add, what env vars are needed.
8. Update `~/git/primitives/registry.yaml` if this is a new primitive.
9. Create or update `.primitives.yaml` in the source app with file mappings.

**Key principle**: The canonical code should be the "cleanest common version"
that works in any app of the same stack. Domain-specific agents, tools, and
customizations belong in the app, not the primitive.

### 2. Apply

**Trigger**: User says "apply the X primitive to this app" or similar.

**Workflow**:

1. Read `~/git/primitives/<name>/manifest.yaml` to understand what the primitive
   provides and its stack requirements.
2. Read `~/git/primitives/<name>/INTEGRATION.md` for step-by-step instructions.
3. Read the target app's structure: project layout, existing models, routes,
   components, package files.
4. Follow `INTEGRATION.md` section by section, adapting for the target app:

   **Database Layer**:
   - Read canonical models from `schema/models.py`.
   - Adapt Base class import, foreign key references (e.g., User model path).
   - Add models to the app's models directory.
   - Create or append an Alembic migration.

   **Backend Layer**:
   - Add Python dependencies from `requirements.txt` to the app's requirements.
   - Copy backend modules, updating `from app.` import prefixes to match the
     target's package structure.
   - Register API routers in `main.py` or equivalent.
   - Add startup lifecycle hooks (e.g., agent seeding, memory pool init).
   - Add required environment variables to `.env.example`.

   **Frontend Layer**:
   - Add npm dependencies from `package-deps.json` to `package.json`.
   - Copy components, updating import paths for the target's component structure.
   - Wire providers (e.g., AssistantRuntimeProvider) into the app's layout.
   - Add API client methods to the target's API client module.
   - Add TypeScript types to the target's types module.

   **Infrastructure**:
   - Merge docker-compose fragments into the app's docker-compose files.
   - Copy config files (e.g., otel-collector.yaml) to appropriate locations.

5. Create `.primitives.yaml` in the target app root with:
   - Primitive name and version
   - File mapping (primitive path -> app path for every file placed)
   - Customization notes (initially empty)
6. List any remaining manual steps (e.g., "set OPENAI_API_KEY in .env").

### 3. Sync

**Trigger**: User says "sync the X primitive" or "port X changes to primitive".

**Two directions**:

**App -> Primitive** (contribute changes back):
1. Read `.primitives.yaml` to get file mappings and current version.
2. For each mapped file, diff the app's version against the primitive's canonical
   version.
3. Present the diffs to the user. Ask which changes are "core improvements" vs
   "app-specific customizations".
4. Apply core improvements to the primitive's canonical code.
5. Bump primitive version and update CHANGELOG.md.
6. Update `.primitives.yaml` version in the source app.

**Primitive -> App** (pull updates into app):
1. Read `.primitives.yaml` to get file mappings and installed version.
2. Read CHANGELOG.md entries from the installed version to the current version.
3. For each changed file listed in the changelog:
   a. Read the primitive's current canonical version.
   b. Read the app's current version of that file.
   c. Identify what changed in the primitive since the installed version.
   d. Apply those changes to the app's version, preserving any app-specific
      customizations (guided by the `customizations` list in .primitives.yaml).
4. Update `.primitives.yaml` version to the primitive's current version.

### 4. Create

**Trigger**: User says "create a new primitive called X" or similar.

**Workflow**:

1. Ask the user for: name, description, which stack layers are involved.
2. Create directory `~/git/primitives/<name>/`.
3. Copy and fill `manifest.template.yaml` -> `manifest.yaml`.
4. Copy `INTEGRATION.template.md` -> `INTEGRATION.md`.
5. Copy `CHANGELOG.template.md` -> `CHANGELOG.md`.
6. Create subdirectories based on stack layers:
   - `schema/` if persistence layer involved
   - `backend/` if backend involved
   - `frontend/` if frontend involved
   - `config/` if infrastructure involved
7. Add entry to `~/git/primitives/registry.yaml`.
8. Tell the user the primitive is scaffolded and ready for extraction.

## File Structure Reference

```
~/git/primitives/
  registry.yaml                 # Index of all primitives
  templates/                    # Scaffolding templates
    manifest.template.yaml
    INTEGRATION.template.md
    CHANGELOG.template.md
  <primitive-name>/
    manifest.yaml               # Metadata, version, provides, extension points
    INTEGRATION.md              # AI-readable integration guide
    CHANGELOG.md                # Version history with affected files
    schema/                     # Database models and migrations
    backend/                    # Python backend code
    frontend/                   # React frontend code
    config/                     # Infrastructure configs, docker fragments, env
```

## .primitives.yaml Schema

```yaml
primitives_repo: ~/git/primitives

installed:
  <primitive-name>:
    version: "1.0.0"
    applied_at: "YYYY-MM-DD"
    file_mapping:
      <primitive-path>: <app-path>
    customizations:
      - "Description of app-specific customization"
```

## Guidelines

- **Canonical code is real code**, not templates with placeholders. It should be
  the cleanest common version extracted from actual applications.
- **INTEGRATION.md is the most important document.** It must be specific enough
  for an AI agent to follow mechanically, with exact code snippets and clear
  adaptation notes.
- **Extension points, not forks.** Domain-specific agents, tools, and UI
  customizations are expected to differ per app. The primitive provides the
  engine and framework; the app provides the domain specifics.
- **CHANGELOG.md enables incremental sync.** Every change must list affected
  files so the sync command knows exactly what to diff.
- **File mappings enable precision.** The `.primitives.yaml` file_mapping is
  what makes sync work -- it tells the agent exactly where each primitive file
  lives in the app.
- For detailed manifest.yaml schema, see [reference/manifest-schema.md](reference/manifest-schema.md).
