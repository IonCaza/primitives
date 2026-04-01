# Presentation Studio — Integration Guide

This primitive adds an AI-powered presentation studio that generates interactive
dashboards as React component code, rendered inside sandboxed iframes with live
data access via a PostMessage bridge.

**Prerequisite**: The `agentic-ai-engine` primitive must be installed first. It
provides the agent runner, chat infrastructure, tool registry, and ChatRuntime
component that the presentation studio depends on.

---

## 1. Database Layer

### 1a. Add the presentation model

Copy `schema/presentation.py` to your models directory (e.g.,
`backend/app/db/models/presentation.py`).

**Adaptation notes:**
- Update the `from app.db.base import Base` import to match your project's Base class location.
- The `Presentation` model has foreign keys to `projects.id`, `chat_sessions.id`, and `users.id`. Ensure these tables exist (projects and users are app-specific; chat_sessions comes from agentic-ai-engine).
- Register all three models in your `__init__.py` model barrel file:
  ```python
  from app.db.models.presentation import Presentation, PresentationTemplate, PresentationVersion
  ```

### 1b. Create an Alembic migration

Create a migration that:
1. Creates `presentation_templates` table (id UUID PK, version INT UNIQUE, template_html TEXT, description VARCHAR(1024), created_at TIMESTAMPTZ)
2. Creates `presentations` table (id UUID PK, project_id UUID FK→projects, title, description, component_code TEXT, template_version INT, prompt TEXT, chat_session_id UUID FK→chat_sessions, created_by_id UUID FK→users, status VARCHAR(32), created_at, updated_at)
3. Creates `presentation_versions` table (id UUID PK, presentation_id UUID FK→presentations CASCADE, version_number INT, component_code TEXT, template_version INT, change_summary, created_at)
4. Seeds the v1 template from `config/v1-template.html`:
   ```python
   op.execute(
       sa.text(
           "INSERT INTO presentation_templates (id, version, template_html, description) "
           "VALUES (gen_random_uuid(), 1, :html, 'Initial v1 template with bridge protocol v1, useQuery, useMultiQuery, Skeleton, MetricCard, ErrorCard, Section')"
       ).bindparams(html=V1_TEMPLATE_HTML)
   )
   ```

See the canonical migration in the source repo (`alembic/versions/h5i6j7k8l9m0_add_presentations.py`) for the full DDL.

---

## 2. Backend Layer

### 2a. Copy backend modules

| Primitive path | Target path |
|---|---|
| `backend/api/presentations.py` | `backend/app/api/presentations.py` |
| `backend/agents/tools/presentation.py` | `backend/app/agents/tools/presentation.py` |
| `backend/agents/builtin/presentation_designer.py` | `backend/app/agents/builtin/presentation_designer.py` |
| `backend/agents/prompts/presentation_designer.py` | `backend/app/agents/prompts/presentation_designer.py` |

**Adaptation notes for each file:**

**`presentations.py` (API)**:
- Update all `from app.` imports to match your project structure.
- The `ALLOWED_TOOL_CATEGORIES` frozenset defaults to `{"sql_query"}`. Add your domain-specific tool categories here (e.g., `"contribution_analytics"`, `"delivery_analytics"`).
- The `_execute_sql_json()` function imports `_validate_select_only` from `app.agents.tools.sql_query`. This tool module comes from the agentic-ai-engine primitive.

**`presentation.py` (agent tools)**:
- Update `from app.` imports.
- The `_build_presentation_tools` function uses `_session_factory` from your DB module. Ensure the import `from app.db.base import async_session as _session_factory` is correct.
- The `save_presentation` tool imports `Project` from your models — update to match your Project model location.

**`presentation_designer.py` (builtin agent)**:
- Update the prompt import path: `from app.agents.prompts.presentation_designer import PRESENTATION_DESIGNER_PROMPT`
- **Add domain-specific member agents** to `member_slugs` if you have specialist analysts. E.g.:
  ```python
  member_slugs=[
      "contribution-analyst",
      "delivery-analyst",
  ],
  ```

**`presentation_designer.py` (prompt)**:
- The canonical prompt references `bridge.query()` as the data access function. If your template HTML uses a different bridge namespace, update accordingly.
- **Add domain-specific delegation instructions** to the prompt if you added member agents. E.g., add a section listing `ask_contribution_analyst`, `ask_delivery_analyst`, etc.

### 2b. Register the presentation tool category

In your agent tool registry file (e.g., `backend/app/agents/registry.py`), add:
```python
import app.agents.tools.presentation  # noqa: F401 — registers tools
```

### 2c. Register the builtin agent

Ensure `presentation_designer.py` is imported in your builtin agents `__init__.py` so it gets seeded on startup.

### 2d. Register the API router

In your `main.py`:
```python
from app.api import presentations as presentations_api
app.include_router(presentations_api.router, prefix="/api")
```

### 2e. SSE event wiring (already in agentic-ai-engine)

The agent runner from `agentic-ai-engine` already emits `presentation_update` SSE events when `save_presentation` or `update_presentation` tools complete successfully. No additional backend wiring needed.

---

## 3. Frontend Layer

### 3a. Copy frontend files

| Primitive path | Target path |
|---|---|
| `frontend/components/presentation-studio.tsx` | `src/components/presentation-studio.tsx` |
| `frontend/components/presentation-sandbox.tsx` | `src/components/presentation-sandbox.tsx` |
| `frontend/hooks/use-presentations.ts` | `src/hooks/use-presentations.ts` |
| `frontend/pages/presentations/page.tsx` | `src/app/(dashboard)/projects/[projectId]/presentations/page.tsx` |
| `frontend/pages/presentations/new/page.tsx` | `src/app/(dashboard)/projects/[projectId]/presentations/new/page.tsx` |
| `frontend/pages/presentations/[presentationId]/page.tsx` | `src/app/(dashboard)/projects/[projectId]/presentations/[presentationId]/page.tsx` |

**Adaptation notes:**

**`presentation-studio.tsx`**:
- Update the ChatRuntime import to your app's chat runtime component name:
  ```typescript
  import { ChatRuntime, useChildAgentActivity } from "@/components/chat-runtime";
  // or if your app uses a branded name:
  import { ContributrChatRuntime as ChatRuntime, useChildAgentActivity } from "@/components/contributr-chat-runtime";
  ```
- Update `useProject` hook import if your project hook has a different name/path.

**`presentation-sandbox.tsx`**:
- The sandbox listens for `presentation_query` PostMessage events. If your template HTML uses a different protocol type, update the event type check to match.

**`new/page.tsx`**:
- Replace `EXAMPLE_PROMPTS` with domain-specific examples for your application.
- Optionally replace `DEFAULT_PALETTE` with your app's brand colors.
- Optionally rename the "Default" palette preset label.

### 3b. Add API client methods

Add these methods to your API client (e.g., `src/lib/api-client.ts`):

```typescript
// Presentations
listPresentations: (projectId: string) =>
  request<PresentationListItem[]>(`/projects/${projectId}/presentations`),
createPresentation: (projectId: string, data: { title: string; description?: string; component_code?: string; prompt?: string; chat_session_id?: string; status?: string }) =>
  request<PresentationDetail>(`/projects/${projectId}/presentations`, { method: "POST", body: JSON.stringify(data) }),
getPresentation: (projectId: string, presId: string) =>
  request<PresentationDetail>(`/projects/${projectId}/presentations/${presId}`),
updatePresentation: (projectId: string, presId: string, data: { title?: string; description?: string; component_code?: string; template_version?: number; status?: string }) =>
  request<PresentationDetail>(`/projects/${projectId}/presentations/${presId}`, { method: "PATCH", body: JSON.stringify(data) }),
deletePresentation: (projectId: string, presId: string) =>
  request<void>(`/projects/${projectId}/presentations/${presId}`, { method: "DELETE" }),
listPresentationVersions: (projectId: string, presId: string) =>
  request<PresentationVersion[]>(`/projects/${projectId}/presentations/${presId}/versions`),
getPresentationTemplate: (version: number) =>
  request<PresentationTemplate>(`/presentations/templates/${version}`),
getLatestPresentationTemplate: () =>
  request<PresentationTemplate>(`/presentations/templates/latest`),
executePresentationQuery: (projectId: string, toolSlug: string, params: Record<string, unknown>) =>
  request<{ result: unknown }>(`/projects/${projectId}/presentations/data`, { method: "POST", body: JSON.stringify({ tool_slug: toolSlug, params }) }),
```

### 3c. Add TypeScript types

Add to your types file (e.g., `src/lib/types.ts`):

```typescript
// ── Presentations ──────────────────────────────────────────────────

export interface PresentationListItem {
  id: string;
  title: string;
  description: string | null;
  prompt: string;
  status: string;
  template_version: number;
  created_at: string;
  updated_at: string | null;
}

export interface PresentationDetail {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  component_code: string;
  template_version: number;
  prompt: string;
  chat_session_id: string | null;
  created_by_id: string;
  status: string;
  created_at: string;
  updated_at: string | null;
}

export interface PresentationVersion {
  id: string;
  presentation_id: string;
  version_number: number;
  component_code: string;
  template_version: number;
  change_summary: string | null;
  created_at: string;
}

export interface PresentationTemplate {
  id: string;
  version: number;
  template_html: string;
  description: string;
  created_at: string;
}
```

### 3d. Add query keys

Add to your query keys file (e.g., `src/lib/query-keys.ts`):

```typescript
presentations: {
  list: (projectId: string) => ["presentations", projectId, "list"] as const,
  detail: (projectId: string, presId: string) => ["presentations", projectId, presId] as const,
  versions: (projectId: string, presId: string) => ["presentations", projectId, presId, "versions"] as const,
  template: (version: number) => ["presentationTemplates", version] as const,
  templateLatest: ["presentationTemplates", "latest"] as const,
},
```

### 3e. Add navigation link

Add a presentations nav link to your project layout/sidebar pointing to
`/projects/${projectId}/presentations`.

### 3f. Confirm dialog component

The presentations list page uses a `<ConfirmDialog>` component. Ensure your app has
this component or create one using shadcn/ui's AlertDialog.

---

## 4. Infrastructure

No additional infrastructure beyond what `agentic-ai-engine` provides.

---

## 5. Post-Integration Checklist

- [ ] Alembic migration created and applied (3 tables + v1 template seed)
- [ ] Presentation models registered in model barrel file
- [ ] API router registered in main.py with `/api` prefix
- [ ] Presentation tool category imported in agent registry
- [ ] Presentation designer builtin agent imported and seedable
- [ ] Frontend pages placed in correct Next.js route structure
- [ ] API client methods added
- [ ] TypeScript types added
- [ ] Query keys added
- [ ] ALLOWED_TOOL_CATEGORIES extended with domain-specific categories
- [ ] presentation-designer member_slugs populated with domain agents
- [ ] EXAMPLE_PROMPTS customized for your domain
- [ ] Navigation link added to project layout
- [ ] PostMessage protocol type matches between template HTML and sandbox (`presentation_query`)
