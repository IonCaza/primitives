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

Add these SQLAlchemy models to your project. Canonical definitions are in the
`schema/` directory: `schema/task_item.py`, `schema/agent_memory.py`,
`schema/agent_skill.py`. Remaining models are described below and derived from
the source applications.

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

12. **TaskItem** -- Structured task decomposition (canonical: `schema/task_item.py`):
    - Composite PK: `id` (String 8, e.g. "t1") + `session_id` (UUID FK to ChatSession, CASCADE)
    - `subject` (String 200), `description` (Text nullable),
      `status` (String 20, CHECK: pending/in_progress/completed/blocked/cancelled),
      `owner_agent_slug` (String 100 nullable),
      `blocked_by` (ARRAY of String, dependency IDs),
      `blocks` (ARRAY of String, reverse dependency IDs),
      `metadata` (JSON), `created_at` (timestamptz)

13. **AgentMemory** -- Structured long-term memory with taxonomy (canonical: `schema/agent_memory.py`):
    - `id` (UUID PK), `user_id` (FK to User, CASCADE), `project_id` (UUID nullable),
      `agent_slug` (String nullable, NULL = shared), `name` (String 200),
      `description` (String 500), `type` (String 20, CHECK: user/feedback/project/reference),
      `content` (Text), `created_at`, `updated_at`
    - Indexes: `ix_agent_memories_user_id`, `ix_agent_memories_user_type`

14. **AgentSkill** -- Injectable prompt fragments (canonical: `schema/agent_skill.py`):
    - `id` (UUID PK), `slug` (unique String 100), `name` (String 200),
      `description` (Text nullable), `prompt_content` (Text),
      `applicable_agents` (PostgreSQL `ARRAY(String(100))` nullable; NULL = all agents),
      `auto_inject` (Boolean), `is_active` (Boolean), `created_at` (timestamptz)

**Adaptation notes:**
- Import paths for `Base` declarative base: update to your project's location
- Foreign keys to `User`: update to your User model's table name and import
- If using a different naming convention for tables, update `__tablename__`
- **ChatSession** extensions used by memory subsystems (if you copy those modules):
  nullable `session_notes` (Text), `context_summary` (Text), and
  `notes_token_cursor` (Integer) as in `backend/agents/memory/session_notes.py`.
- **User** extension for memory consolidation (`backend/agents/memory/consolidation.py`):
  nullable `last_memory_consolidation` (DateTime with timezone).

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

### 2.2.1 Optional: agent skills, skill tools, memory consolidation

If you use the canonical modules `backend/agents/skills.py`,
`backend/agents/tools/skill_tool.py`, and/or
`backend/agents/memory/consolidation.py`:

1. Add the **AgentSkill** model (`schema/agent_skill.py`) to your models package
   and migrate the `agent_skills` table.
2. Register skill tools by importing the module from your tool registry (same
   pattern as `task_tools`):
   `import app.agents.tools.skill_tool  # noqa: F401`
3. Optionally call `seed_builtin_skills(db)` once at startup (async session)
   to upsert the builtin example skill rows from `BUILTIN_SKILLS`.
4. When assembling an agent's system prompt, append the string returned by
   `await load_active_skills(agent_slug, db)` (non-empty means auto-inject
   skills were found).
5. For **consolidation**, ensure `User` has `last_memory_consolidation` and
   `ChatSession` has `session_notes` / `context_summary` (see §1.1 adaptation
   notes). Call `maybe_consolidate(user_id, llm)` from an appropriate hook
   (e.g. after a chat turn) if you want periodic memory maintenance.

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

The primitive includes 3 reference agent implementations in
`backend/agents/builtin/`:

| File | Agent | Pattern |
|---|---|---|
| `supervisor.py` | Supervisor | Coordinator with member delegation, no direct tools |
| `text_to_sql.py` | Text to SQL | Focused agent with 3 SQL tools |
| `verification_agent.py` | Verification Agent | Tool-less QA agent for supervisor workflows |

Each module exports a `SPEC` instance of `BuiltinAgentSpec`:

```python
from app.agents.builtin import BuiltinAgentSpec

SPEC = BuiltinAgentSpec(
    slug="my-agent",              # unique identifier
    name="My Agent",              # display name
    description="...",            # shown in agent selector UI
    system_prompt=MY_PROMPT,      # full system prompt string
    tool_slugs=["tool_a"],        # registered tool slugs this agent can use
    agent_type="standard",        # "standard" or "supervisor"
    member_slugs=[],              # supervisor only: slugs of member agents
    max_iterations=25,            # 25 for standard, 50 for supervisors
)
```

Register your agents in `backend/agents/builtin/__init__.py` by importing
their `SPEC` and adding it to `get_builtin_agents()`. Standard agents should
appear before supervisors so members are seeded first.

Create a startup function that calls `get_builtin_agents()` and upserts each
spec into the `AgentConfig` table on boot (see `main.py` lifespan).

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

// Task board
getSessionTasks(sessionId: string): Promise<TaskItem[]>
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

interface TaskItem {
  id: string;
  subject: string;
  description: string | null;
  status: "pending" | "in_progress" | "completed" | "blocked" | "cancelled";
  owner_agent_slug: string | null;
  blocked_by: string[];
  blocks: string[];
  created_at: string;
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

## 6. Structured Memory (Track 3)

The engine includes a taxonomy-based structured memory system with four types:
- **user** -- preferences, expertise, communication style
- **feedback** -- corrections and confirmed approaches
- **project** -- business context, decisions, team structure
- **reference** -- pointers to external systems

### 6.1 Memory Tools

Four tools are registered in the slug registry (category: `memory`):
- `save_memory` -- persist a typed memory with name, description, content
- `search_memories` -- keyword search with optional type filter
- `update_memory` -- update content of an existing memory by ID
- `forget_memory` -- delete an outdated or incorrect memory

Tools use `current_user_id` ContextVar for user scoping. Assign them to
agents via the admin UI or include in tool_slugs.

### 6.2 Memory Recall Pre-flight

Before each agent turn, the runner loads all user memories and asks a fast
LLM to select the most relevant ones (up to 5). Selected memories are injected
into the system prompt as a "Recalled Context" section. If <5 memories exist,
all are injected without an LLM call. Staleness warnings appear for memories
older than 7 days.

### 6.3 Background Extraction

After each agent turn, a background task reviews the conversation against
existing memories using the 4-type taxonomy. The extraction LLM outputs
structured save/update/delete actions. This runs asynchronously and fails
silently if the extraction model is not configured.

## 7. Session Memory (Track 4)

Session notes are a structured document maintained incrementally throughout
a conversation. Unlike `context_summary` (regenerated on each compaction),
session notes persist across compaction events and accumulate detail.

### 7.1 Schema Changes

Add two columns to `ChatSession`:

```python
session_notes: Mapped[str | None] = mapped_column(
    Text, nullable=True,
    comment="Structured session notes maintained across compaction events",
)
notes_token_cursor: Mapped[int] = mapped_column(
    default=0,
    comment="Message index up to which session notes have been extracted",
)
```

Also add `session_notes: str | None = None` to `AgentState`.

### 7.2 How It Works

1. **Pre-load**: Before each agent turn, existing notes and cursor are loaded
   from the `ChatSession` row and injected into checkpoint state.
2. **Modifier**: Session notes are injected as a system message between the
   main system prompt and the context summary, with token budget accounting.
3. **Post-turn extraction**: After streaming, if 8000+ new tokens AND 2+
   tool calls have accumulated since the last extraction, an LLM updates the
   notes. The structured template has sections for Current Focus, User's
   Request, Data Landscape, Agent Activity, Corrections, Insights, and
   Deliverables.
4. **Compaction shortcut**: When session notes exist, `cleanup_checkpoint`
   uses them directly as the summary instead of running the expensive LLM
   summarization call.

### 7.3 Adaptation Notes

- The `SESSION_NOTES_TEMPLATE` sections (Data Landscape, Agent Activity,
  etc.) are tuned for data/analytics use cases. Modify the template in
  `session_notes.py` if your domain differs.
- Thresholds (`NEW_TOKEN_THRESHOLD = 8000`, `MIN_TOOL_CALLS = 2`) can be
  tuned per deployment. Lower thresholds produce more frequent updates at
  higher LLM cost.

## 8. Context Management Pipeline (Track 5)

The modifier now applies a multi-stage pipeline before trimming messages.
This preserves more useful context by running cheap transformations first.

### 8.1 Stage 1: Tool Result Budgeting

Any `ToolMessage` exceeding `MAX_TOOL_RESULT_TOKENS` (2500, ~10K chars)
is truncated with a `[... result truncated ...]` suffix. This prevents
one large SQL result from crowding out the rest of the conversation.

### 8.2 Stage 2: Microcompact

Old results from read-only tools are replaced with lightweight placeholders
like `[Previous run_sql_query result cleared to save context]`. The most
recent 5 results per tool category are preserved. The set of eligible
tools is defined in `COMPACTABLE_TOOLS`.

### 8.3 Stage 3: Session-Memory-Aware Compaction

Covered in Track 4 -- when session notes exist, the compaction path
uses them directly as the summary instead of calling the LLM.

### 8.4 Stage 4: Reactive Recovery

If the LLM returns a prompt-too-long error, the runner catches it,
runs `cleanup_checkpoint(force=True)` to aggressively evict messages,
and retries the stream once. If the retry also fails, the error is logged.

### 8.5 Adaptation Notes

- **Extend `COMPACTABLE_TOOLS`** in your local `modifier.py` with any
  domain-specific read-only tools. The primitive ships with a generic
  set (sql, memory, task, presentation tools). For example, contributr
  adds delivery analytics tools (`find_work_item`, `get_sprint_*`, etc.).
- `MAX_TOOL_RESULT_TOKENS` and `KEEP_RECENT_RESULTS` can be tuned.
  Lower budgets save context but risk losing useful detail.

## 9. Tool Execution Optimization (Track 6)

`ParallelToolNode` replaces LangGraph's default `ToolNode` to add
**concurrency-aware batching**. Read-only tools execute in parallel via
`asyncio.gather`; stateful tools execute sequentially, preserving the
model's intended ordering.

### 9.1 Marking Tools as Concurrency-Safe

There are two granularities:

**Category-level** -- marks *every* tool in the category:

```python
register_tool_category(
    "delivery_analytics", DEFINITIONS, _build_tools,
    concurrency_safe=True,   # all tools in this category are read-only
)
```

**Per-tool** -- for mixed categories (read + write tools):

```python
DEFINITIONS = [
    ToolDefinition(..., concurrency_safe=True),   # read-only
    ToolDefinition(...),                           # write -- left serial
]
```

The registry function `is_tool_concurrency_safe(slug)` returns True if
*either* the tool's definition or its category is flagged.

### 9.2 How ParallelToolNode Works

When the model emits multiple tool calls in one turn, `ParallelToolNode`
partitions them into alternating batches:

1. **Concurrent batch** -- adjacent concurrency-safe calls grouped and
   dispatched via `asyncio.gather`.
2. **Serial batch** -- a single non-safe call that runs alone.

Batches execute in list order so the overall call sequence stays
deterministic. If every call is safe, they all run concurrently. If none
are safe, they run one-at-a-time (matching the old serial behavior).

### 9.3 Integration

`build_agent()` and `build_coordinator()` automatically wrap the tools
list in a `ParallelToolNode` before passing it to `create_react_agent`.
No agent-level opt-in is required -- all agents benefit immediately.

### 9.4 Adaptation Notes

- **Mark your read-only categories** with `concurrency_safe=True` in the
  `register_tool_category()` call. Good candidates: analytics queries,
  search endpoints, code-read tools.
- **Mark individual read-only tools** in mixed categories via
  `ToolDefinition(..., concurrency_safe=True)`. Good candidates:
  `list_*`, `get_*`, `search_*` tools that share a category with write
  tools.
- Do **not** mark tools that write to the database, call external
  mutation APIs, or depend on ordering relative to other tools.
- The `ParallelToolNode` is a subclass of LangGraph's `ToolNode`. If a
  future LangGraph version changes the `ToolNode` API, fall back to
  passing the plain tools list to `create_react_agent`.

## 10. Skills / Prompt Extension System (Track 8)

The skills system lets you define injectable prompt fragments that are either
auto-injected into matching agents' system prompts or activated on-demand
via tool calls.

### 10.1 Database Setup

Create the `agent_skills` table from `schema/agent_skill.py`:

```sql
CREATE TABLE agent_skills (
    id UUID PRIMARY KEY,
    slug VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    prompt_content TEXT NOT NULL,
    applicable_agents VARCHAR(100)[],
    auto_inject BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);
```

### 10.2 Skill Loading and Injection

Skills are loaded in the runner and injected into the system prompt:

1. `load_active_skills(agent_slug, db)` queries auto-inject skills matching
   the agent. Returns formatted prompt sections.
2. The runner passes the result as `skill_context` to `build_agent()` /
   `build_coordinator()`, which appends it under `## Activated Skills`.

### 10.3 On-Demand Skill Tools

Two tools are registered under the `skills` category:

- **`list_skills`** -- lists available non-auto-inject skills
- **`use_skill(skill_slug)`** -- loads a skill's prompt into the conversation

Assign these tool slugs to agents that should have on-demand skill access.

### 10.4 Seeding Builtin Skills

Call `seed_builtin_skills(db)` at startup (after DB is ready). The
primitive includes a generic `data-exploration-workflow` skill as an
example. Add domain-specific skills to the `BUILTIN_SKILLS` list in your
fork of `skills.py`.

### 10.5 Adaptation Notes

- `applicable_agents` is a Postgres ARRAY. `NULL` means the skill
  targets all agents; a non-NULL array like `["my-agent"]` restricts it.
- Skills with `auto_inject=True` are injected into every matching agent's
  prompt automatically. Use sparingly -- each one adds tokens.
- Skills with `auto_inject=False` are only loaded when the agent
  explicitly calls `use_skill`.
- Add `import app.agents.tools.skill_tool` at the end of your
  `tools/registry.py` (after `register_tool_category` is defined) to
  trigger self-registration.

## 11. Memory Consolidation (Track 9)

Periodic LLM-driven maintenance of long-term memories. Reviews existing
`AgentMemory` entries against recent session summaries and decides what to
keep, update, merge, or delete.

### 11.1 Database Setup

Add a column to your `User` model:

```python
last_memory_consolidation: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True,
)
```

### 11.2 How It Works

`maybe_consolidate(user_id, llm)` is scheduled as a fire-and-forget task
after each successful agent turn (alongside `extract_memories`). It:

1. **Gate check** -- skips if less than 24 hours since last consolidation
   or fewer than 5 new sessions since then.
2. **Loads memories** -- fetches all `AgentMemory` rows for the user.
3. **Loads session context** -- fetches up to 10 recent `ChatSession`
   summaries (using `session_notes` or `context_summary`).
4. **LLM review** -- sends memories + session summaries to the LLM with
   instructions to keep, update, merge, or delete.
5. **Applies actions** -- updates, merges, or deletes memories as directed.
6. **Stamps cooldown** -- sets `User.last_memory_consolidation`.

### 11.3 Adaptation Notes

- The consolidation module expects `ChatSession.user_id`,
  `ChatSession.session_notes`, and `ChatSession.context_summary` fields.
  Ensure your ChatSession model has these.
- Tune `CONSOLIDATION_COOLDOWN_HOURS` (default 24) and
  `MIN_SESSIONS_BEFORE_CONSOLIDATION` (default 5) in your fork.
- Consolidation is non-critical -- failures are logged and silently
  swallowed to avoid disrupting the user's session.

## 12. Enhanced Presentation Designer Workflow (Track 10)

The presentation designer prompt now uses a structured 4-phase workflow:

1. **EXPLORE** -- schema discovery, sample data, delegation to specialists
2. **DESIGN** -- layout selection, chart type matching, query planning
3. **BUILD** -- component generation with loading/error states
4. **VERIFY** -- post-save validation checklist

The prompt also references the skills system (`list_skills` / `use_skill`)
so the designer can activate layout patterns and chart selection guides
on demand.

### 12.1 Adaptation Notes

- The prompt references `ask_*` delegation tools specific to your domain.
  Update the tool names in the Phase 1 section to match your specialist
  agents.
- Assign `list_skills` and `use_skill` to your presentation designer
  agent's `tool_slugs` in its `BuiltinAgentSpec`.
- Seed domain-specific skills (layout patterns, chart guides) via
  `BUILTIN_SKILLS` in `skills.py` with
  `applicable_agents=["presentation-designer"]`.

## 13. Verification

- [ ] Database migrations run successfully (including `agent_memories`, `agent_skills`, `session_notes`, `last_memory_consolidation` columns)
- [ ] Application starts without errors (memory pool initializes, skills seeded)
- [ ] POST `/api/v1/chat` returns SSE events (requires at least one LLM provider and enabled agent in the DB)
- [ ] Frontend chat panel renders and connects to the SSE stream
- [ ] Agent activity panel shows delegation events for supervisor agents
- [ ] Memory tools: `save_memory` creates rows in `agent_memories`
- [ ] Memory recall: relevant memories appear in agent responses when context matches
- [ ] Background extraction: memories are created/updated after conversations
- [ ] Session notes: `session_notes` column populated after substantial conversations (8000+ tokens, 2+ tool calls)
- [ ] Compaction shortcut: when session notes exist, cleanup logs "Using session notes as compaction summary"
- [ ] Tool budgeting: large tool results are truncated in agent prompts (check logs for conversations with big SQL results)
- [ ] Microcompact: old read-only tool results replaced with placeholders after 5+ accumulate
- [ ] Reactive recovery: if you deliberately overflow the context, logs show "Prompt too long -- attempting emergency compaction"
- [ ] ParallelToolNode: when an agent emits multiple read-only tool calls, logs show "ParallelToolNode: N concurrent, M serial"
- [ ] Concurrency marking: `is_tool_concurrency_safe("list_tasks")` returns True; `is_tool_concurrency_safe("create_task")` returns False
- [ ] Skills: `agent_skills` table created, builtin skills seeded on startup
- [ ] Skill auto-inject: agents with matching skills have `## Activated Skills` in their prompt (check logs)
- [ ] Skill tools: `list_skills` returns available skills; `use_skill("data-exploration-workflow")` returns the prompt
- [ ] Consolidation: after 5+ sessions, `maybe_consolidate` runs and logs "Memory consolidation for user X: N actions"
- [ ] Presentation designer: 4-phase workflow reflected in agent behavior (explore before building)
