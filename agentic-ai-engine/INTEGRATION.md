# Agentic AI Engine -- Integration Guide

> This document is designed for AI agent consumption. Follow each section
> step-by-step. Canonical code lives in this primitive's directory tree.
> Adaptation notes explain what to change for your project.

## Prerequisites

- [ ] FastAPI backend with SQLAlchemy 2.0 async (asyncpg driver)
- [ ] Alembic for database migrations
- [ ] PostgreSQL with pgvector extension (`CREATE EXTENSION IF NOT EXISTS vector`)
- [ ] Next.js frontend with React 19, Tailwind CSS, and shadcn/ui installed
- [ ] TanStack Query configured in the frontend
- [ ] Authentication system with a `get_current_user` dependency and a `User` model
- [ ] A `settings` object (pydantic-settings) with `database_url` and `secret_key`

## 1. Database Layer

### 1.1 Models

Add these SQLAlchemy models to your project. The canonical definitions are in
`schema/models.py` (if present) or derived from the source applications.

**Required models** (create in your models directory):

1. **AiSettings** -- Singleton row (id=1) controlling AI feature flags:
   - `id` (Integer, PK, default=1), `enabled` (Boolean), `memory_enabled` (Boolean),
     `extraction_enabled` (Boolean), `extraction_provider_id` (FK to LlmProvider, nullable),
     `extraction_enable_inserts/updates/deletes` (Boolean),
     `cleanup_threshold_ratio` (Float, default=0.6),
     `summary_token_ratio` (Float, default=0.04)
   - Export `SINGLETON_ID = 1`

2. **LlmProvider** -- LLM provider configurations:
   - `id` (UUID PK), `name`, `model`, `provider_name`, `api_key_encrypted`,
     `base_url` (nullable), `model_type` (e.g., "chat", "embedding"),
     `temperature` (Float), `context_window` (Integer, nullable),
     `is_default` (Boolean), `enabled` (Boolean), timestamps

3. **AgentConfig** -- Agent definitions:
   - `id` (UUID PK), `slug` (unique), `name`, `description`, `system_prompt`,
     `agent_type` ("standard" or "supervisor"), `llm_provider_id` (FK nullable),
     `max_iterations` (Integer), `summary_token_limit` (Integer, nullable),
     `enabled` (Boolean), `is_builtin` (Boolean), timestamps
   - Relationships: `tool_assignments`, `llm_provider`, `knowledge_graph_assignments`,
     `member_agents` (self-referential M2M for supervisor type)

4. **AgentToolAssignment** -- M2M linking agents to tool slugs:
   - `agent_id` (FK), `tool_slug` (String), composite PK

5. **SupervisorMember** -- M2M linking supervisor agents to member agents:
   - Defined via SQLAlchemy `relationship` with secondary table or explicit model

6. **KnowledgeGraph** -- Injectable context blocks:
   - `id` (UUID PK), `name`, `content` (Text), `mode`, timestamps

7. **AgentKnowledgeGraphAssignment** -- M2M linking agents to knowledge graphs:
   - `agent_id` (FK), `knowledge_graph_id` (FK)

8. **ChatSession** -- Chat session metadata:
   - `id` (UUID PK), `user_id` (FK to User), `title`, `agent_id` (FK nullable),
     `archived_at` (nullable), timestamps
   - Cascade delete of messages

9. **ChatMessage** -- Individual chat messages:
   - `id` (UUID PK), `session_id` (FK), `role` (Enum: user/assistant/system),
     `content` (Text), `created_at`

10. **AgentActivity** -- Delegation activity records:
    - `id` (UUID PK), `session_id` (FK), `trigger_message_id` (UUID),
      `response_message_id` (UUID), `agent_slug`, `run_id`, `content` (Text),
      `started_at`, `finished_at` (nullable)

11. **Feedback** -- Capability gap reports:
    - `id` (UUID PK), `source`, `category`, `content`, `user_query`,
      `agent_slug`, `session_id` (UUID nullable), `created_at`

**Adaptation notes:**
- Import paths for `Base` declarative base: update to your project's location
- Foreign keys to `User`: update to your User model's table name and import
- If using a different naming convention for tables, update `__tablename__`

### 1.2 Migration

Create an Alembic migration to add all tables. Run:
```bash
alembic revision --autogenerate -m "add agentic ai engine tables"
alembic upgrade head
```

Ensure pgvector extension is enabled:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

LangGraph creates its own tables (`checkpoints`, `checkpoint_writes`, `store`)
automatically when `init_memory_pool()` is called at startup.

## 2. Backend Layer

### 2.1 Dependencies

Add the packages from `backend/requirements.txt` to your project's requirements:

```
langchain>=0.3
langchain-litellm>=0.3
langgraph>=0.4
langgraph-checkpoint-postgres>=2.0
langmem>=0.1
litellm>=1.60
psycopg[binary]>=3.2
psycopg-pool>=3.2
cryptography>=44.0
sse-starlette>=2.0
```

### 2.2 Module Placement

Copy the `backend/agents/` directory into your backend's package (e.g., `app/agents/`).
Copy `backend/api/chat.py` into your API routes directory.

**Adaptation notes for ALL Python files:**
- `from app.config import settings` -- update to your settings module path
- `from app.db.base import ...` -- update to your DB session factory path:
  - `get_db` (FastAPI dependency returning AsyncSession)
  - `async_session` (sessionmaker for standalone sessions)
  - `Base` (declarative base for knowledge graph generator)
- `from app.db.models.*` -- update to your model import paths
- `from app.auth.dependencies import get_current_user` -- update to your auth dependency

### 2.3 Register API Routers

In your `main.py` or router registration module:

```python
from app.api.chat import router as chat_router
# Also register these if you create them (not included in primitive core):
# from app.api.agents import router as agents_router
# from app.api.ai_settings import router as ai_settings_router
# from app.api.llm_providers import router as llm_providers_router
# from app.api.ai_tools import router as ai_tools_router
# from app.api.knowledge_graphs import router as knowledge_graphs_router

app.include_router(chat_router, prefix="/api/v1")
```

### 2.4 Startup Hooks

Add to your application's lifespan or startup event:

```python
from app.agents.memory.pool import init_memory_pool, close_memory_pool
from app.agents.llm.manager import build_embeddings_from_provider, get_embedding_dims

async def lifespan(app):
    # ... your existing startup ...

    # Initialize LangGraph memory pool
    # Optionally resolve an embedding provider for long-term memory:
    embed_fn = None
    embed_dims = 1536
    # If you have a default embedding provider:
    # from app.db.models.llm_provider import LlmProvider
    # async with async_session() as db:
    #     provider = (await db.execute(
    #         select(LlmProvider).where(
    #             LlmProvider.is_default.is_(True),
    #             LlmProvider.model_type == "embedding"
    #         )
    #     )).scalar_one_or_none()
    #     if provider:
    #         embed_fn = build_embeddings_from_provider(provider)
    #         embed_dims = get_embedding_dims(provider)

    await init_memory_pool(embed_fn=embed_fn, embed_dims=embed_dims)

    yield

    await close_memory_pool()
```

### 2.5 Seed Builtin Agents (Extension Point)

Create a startup function to upsert your domain-specific agents into the DB.
See `backend/agents/builtin/` in your app for examples. Each agent needs:
- A unique `slug`, `name`, `description`, `system_prompt`
- An `agent_type` ("standard" or "supervisor")
- Tool assignments (list of tool slugs)
- For supervisors: member agent references

### 2.6 Environment Variables

Required in `.env`:
- `SECRET_KEY` -- Used for Fernet encryption of LLM API keys
- `DATABASE_URL` -- PostgreSQL connection string

## 3. Frontend Layer

### 3.1 Dependencies

Install from `frontend/package-deps.json`:

```bash
pnpm add @assistant-ui/react @assistant-ui/core assistant-stream \
  react-markdown remark-gfm react-resizable-panels lucide-react
```

### 3.2 Component Placement

Copy `frontend/components/` into your `src/components/` directory:
- `chat-runtime.tsx` -- The SSE adapter (rename export for your app if desired)
- `chat-panel.tsx` -- The full chat panel with thread list and activity
- `agent-activity-panel.tsx` -- The delegation tracking side panel
- `assistant-ui/` -- The assistant-ui component overrides (thread, markdown, etc.)

**Adaptation notes:**
- `@/lib/api-client` import -- update to your API client's path
- `@/lib/types` import -- update to your types module
- `@/hooks/use-settings` import -- create a hook that fetches agent list:
  ```typescript
  export function useAgents() {
    return useQuery({ queryKey: ["agents"], queryFn: () => api.listAgents() });
  }
  ```
- `@/hooks/use-chat-trigger` import -- optional, for programmatic chat triggers.
  Remove if not needed.
- `@/lib/utils` import (`cn` function) -- standard shadcn/ui utility
- `@/components/ui/*` imports -- ensure shadcn Button, Select, etc. are installed

### 3.3 Provider Wiring

Wrap your authenticated layout with the ChatRuntime provider. In your
dashboard layout (e.g., `app/(dashboard)/layout.tsx`):

```tsx
import { ChatRuntime } from "@/components/chat-runtime";

// Inside the layout's JSX:
<ChatRuntime agentSlug="your-default-agent-slug">
  {children}
  <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />
</ChatRuntime>
```

### 3.4 API Client Methods

Add these methods to your API client (or create a new chat API module):

```typescript
// Chat sessions
listChatSessions(): Promise<ChatSession[]>
createChatSession(): Promise<ChatSession>
getChatSessionMessages(sessionId: string): Promise<ChatMessage[]>
renameChatSession(sessionId: string, title: string): Promise<ChatSession>
archiveChatSession(sessionId: string): Promise<ChatSession>
unarchiveChatSession(sessionId: string): Promise<ChatSession>
deleteChatSession(sessionId: string): Promise<void>

// Agent management
listAgents(): Promise<AgentConfig[]>
```

The chat send itself is handled by the ChatRuntime's SSE adapter (direct
fetch to `/api/v1/chat`), not through the API client.

### 3.5 Types

Add these TypeScript types:

```typescript
interface ChatSession {
  id: string;
  title: string;
  agent_slug: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  agent_activities?: AgentActivityRecord[];
}

interface AgentActivityRecord {
  id: string;
  trigger_message_id: string;
  agent_slug: string;
  run_id: string;
  content: string;
  started_at: string;
  finished_at: string | null;
}

interface AgentConfig {
  id: string;
  slug: string;
  name: string;
  description: string;
  agent_type: "standard" | "supervisor";
  enabled: boolean;
  // ... additional fields as needed
}
```

## 4. Infrastructure

Merge `config/docker-compose.fragment.yml` into your project's docker-compose:
- Use `pgvector/pgvector:pg18-trixie` instead of plain `postgres`
- Add `redis` if not already present

## 5. Extension Points

### Adding Domain-Specific Tools

1. Create a new module in `app/agents/tools/` (e.g., `my_tools.py`)
2. Define tool functions using LangChain's `@tool` decorator
3. Register them using the tool registry pattern:

```python
from app.agents.tools.base import ToolDefinition
from app.agents.tools.registry import register_tool_category

DEFINITIONS = [
    ToolDefinition(slug="my_tool", name="my_tool", description="...", category="my_domain"),
]

def _factory(db):
    @tool
    async def my_tool(query: str) -> str:
        # ... implementation using db session ...
        return result
    return [my_tool]

register_tool_category("my_domain", DEFINITIONS, _factory)
```

4. Import the module in `app/agents/registry.py` to trigger registration:
```python
import app.agents.tools.my_tools  # noqa: F401
```

### Adding Domain-Specific Agents

Create agent definition files in `app/agents/builtin/` and seed them on startup.
Each agent needs a slug, prompt, and tool assignments.

## 6. Verification

- [ ] Database migrations run successfully
- [ ] Application starts without errors (memory pool initializes)
- [ ] POST `/api/v1/chat` returns SSE events (requires at least one LLM provider and enabled agent in the DB)
- [ ] Frontend chat panel renders and connects to the SSE stream
- [ ] Agent activity panel shows delegation events for supervisor agents
- [ ] Long-term memory saves and searches work (requires embedding provider)
