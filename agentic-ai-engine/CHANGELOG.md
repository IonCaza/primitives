# Changelog

All notable changes to the agentic-ai-engine primitive will be documented here.

## [1.8.1] - 2026-04-02
### Added
- **TaskItem** schema: canonical model for structured task decomposition
  with composite PK `(id, session_id)`, status constraint, and
  `blocked_by` / `blocks` dependency arrays.
  (files: schema/task_item.py)
- **AgentMemory** schema: canonical model for structured long-term memory
  with 4-type taxonomy (`user`, `feedback`, `project`, `reference`),
  per-user/per-agent scoping, and description-based recall ranking.
  (files: schema/agent_memory.py)
- **Example builtin agents**: 3 reference implementations demonstrating
  the `BuiltinAgentSpec` pattern:
  - **Supervisor**: coordinator pattern with member delegation, no direct
    tools, max_iterations=50, uses `COORDINATOR_SYSTEM_PROMPT`.
  - **Text-to-SQL**: focused standard agent with 3 SQL tools, generic
    read-only prompt, knowledge-graph-aware schema discovery.
  - **Verification Agent**: tool-less QA agent that independently confirms
    work products with PASS/PARTIAL/FAIL verdicts.
  (files: backend/agents/builtin/__init__.py, backend/agents/builtin/supervisor.py,
   backend/agents/builtin/text_to_sql.py, backend/agents/builtin/verification_agent.py)

### Changed
- **chat-panel.tsx**: default agent selection now persisted to localStorage.
  On load, restores the last selected agent; falls back to the first
  enabled agent if the stored slug no longer exists.
  (files: frontend/components/chat-panel.tsx)
- **skills.py**: enhanced `data-exploration-workflow` builtin skill with
  more actionable steps (Step 5: Query Plan, richer anomaly checks,
  explicit LIMIT/GROUP BY guidance).
  (files: backend/agents/skills.py)
- **api/chat.py**: compact query style for task listing endpoint using
  `db.scalars()` and inline `scalar_one_or_none()`.
  (files: backend/api/chat.py)
- **memory/tools.py**: added `MEMORY_TYPE_GUIDANCE` constant documenting
  the 4-type taxonomy and what not to save, for future injection into
  tool descriptions or system prompts.
  (files: backend/agents/memory/tools.py)

### Fixed
- **chat-runtime.tsx**: ported `currentSessionId` state fix. The task
  board pane now correctly clears and refreshes when switching threads.
  Previously, `sessionIdRef.current` was used directly in `useMemo`,
  which did not trigger re-renders on thread switch.
  (files: frontend/components/chat-runtime.tsx)
- **tools/registry.py**: removed duplicate `skill_tool` import that was
  appended at file end. The canonical import already lives in
  `agents/registry.py` alongside other tool module registrations.
  (files: backend/agents/tools/registry.py)
- **recall.py**: improved type annotation for `_llm_rank_memories`
  parameter from bare `list` to `list[AgentMemory]`.
  (files: backend/agents/memory/recall.py)
- **consolidation.py**: added missing `update` and `AsyncSession` imports
  that were absent from the primitive but present in contributr.
  (files: backend/agents/memory/consolidation.py)

## [1.8.0] - 2026-04-01
### Added
- **AgentSkill** SQLAlchemy model: DB-backed injectable prompt fragments with
  per-agent targeting (`applicable_agents`, `auto_inject`).
  (files: schema/agent_skill.py)
- **skills** module: `load_active_skills`, `list_available_skills`,
  `seed_builtin_skills`, and a generic `BUILTIN_SKILLS` example
  (`data-exploration-workflow`).
  (files: backend/agents/skills.py)
- **skill_tool** category: `use_skill` and `list_skills` LangChain tools for
  on-demand skill activation (registers via `register_tool_category`).
  (files: backend/agents/tools/skill_tool.py)
- **consolidation** module: periodic LLM-driven memory maintenance
  (`should_consolidate`, `consolidate_memories`, `maybe_consolidate`).
  (files: backend/agents/memory/consolidation.py)
- `app.agents.tools.registry` loads `skill_tool` at module end (after
  `register_tool_category` exists) so `use_skill` / `list_skills`
  self-register without circular imports.
  (files: backend/agents/tools/registry.py)

### Changed
- `build_agent` / `build_coordinator`: optional `skill_context` appends
  `## Activated Skills` to the system prompt when non-empty.
  (files: backend/agents/base.py, backend/agents/coordinator.py)
- `run_agent_stream`: loads auto-inject skills via `load_active_skills`,
  passes `skill_context` into both builders, and schedules
  `maybe_consolidate` after memory extraction on successful turns.
  (files: backend/agents/runner.py)

### Migration notes
- Add an `agent_skills` table from `schema/agent_skill.py` (Alembic autogenerate
  or equivalent). Assign `use_skill` and `list_skills` to agents that should
  use the skill tools.
- If you maintain a fork of `tools/registry.py` without the new import, add
  `import app.agents.tools.skill_tool  # noqa: F401, E402` at the **end** of
  the file (after `register_tool_category` is defined) so the category
  self-registers without circular imports.
- Call `seed_builtin_skills` once at startup (after DB is ready) if you want the
  builtin example skill rows.
- To merge auto-injected skills into the system prompt, call
  `load_active_skills(agent_slug, db)` where you assemble the agent prompt
  (see INTEGRATION.md).
- **consolidation.py** expects `User.last_memory_consolidation` (nullable
  `DateTime(timezone=True)`) and `ChatSession.session_notes` /
  `ChatSession.context_summary` (nullable `Text`) on your ORM models if you
  use that module; extend your `User` / `ChatSession` definitions accordingly.

## [1.7.0] - 2026-04-01
### Added
- **ParallelToolNode**: custom `ToolNode` subclass that partitions tool calls
  by concurrency safety. Read-only (concurrency-safe) tools run via
  `asyncio.gather`; stateful tools execute sequentially in the model's
  intended order. Replaces LangGraph's default all-parallel execution.
  (files: backend/agents/tools/parallel_node.py)
- `concurrency_safe` field on `ToolDefinition` dataclass, allowing per-tool
  opt-in to concurrent execution independent of category.
  (files: backend/agents/tools/base.py)
- `concurrency_safe` keyword on `register_tool_category()` for marking
  entire categories as safe for concurrent execution (all analytics,
  code-access categories are natural candidates).
  (files: backend/agents/tools/registry.py)
- `is_tool_concurrency_safe(slug)` registry function: returns True if
  either the tool's definition or its category is marked safe.
  (files: backend/agents/tools/registry.py)

### Changed
- `build_agent()` and `build_coordinator()` now wrap the tools list in a
  `ParallelToolNode` before passing to `create_react_agent`, giving all
  agents smart concurrent/serial tool execution without opt-in.
  (files: backend/agents/base.py, backend/agents/coordinator.py)
- Primitive task tools `list_tasks` and `get_task` marked
  `concurrency_safe=True` (read-only operations).
  (files: backend/agents/tools/task_tools.py)
- Primitive memory tool `search_memories` marked `concurrency_safe=True`.
  (files: backend/agents/memory/tools.py)

### Migration notes
- No schema changes. Purely additive behavior change.
- Consuming apps should mark their read-only tool categories with
  `concurrency_safe=True` in `register_tool_category()` calls and/or
  set `concurrency_safe=True` on individual `ToolDefinition` instances
  for read-only tools in mixed-access categories.
- If `create_react_agent` in a future LangGraph version no longer accepts
  a `ToolNode`, revert to passing the plain tools list in `build_agent`
  and `build_coordinator`.

## [1.6.0] - 2026-04-01
### Added
- **Multi-stage context management pipeline** in the modifier with three
  pre-processing stages that run before the existing trim-from-back logic:
  - Stage 1 (Tool result budgeting): caps any ToolMessage exceeding 2500
    tokens (~10K chars), preventing one large SQL result from crowding
    out useful conversation context.
  - Stage 2 (Microcompact): replaces old read-only tool results with
    lightweight placeholders, keeping only the 5 most recent results for
    each compactable tool category.
  (files: backend/agents/memory/modifier.py)
- **Reactive recovery** in the runner: catches prompt-too-long errors from
  the LLM provider, triggers emergency compaction (force=True), and retries
  the stream once. Prevents total failure on context overflow.
  (files: backend/agents/runner.py)
- `COMPACTABLE_TOOLS` frozenset defining which read-only tools are eligible
  for microcompaction. Apps should extend this set with domain-specific
  read-only tools.
  (files: backend/agents/memory/modifier.py)

### Changed
- `cleanup_checkpoint` now accepts a `force` keyword argument. When True,
  bypasses the token threshold check and evicts aggressively, used by the
  reactive-recovery path.
  (files: backend/agents/memory/cleanup.py)
- Runner streaming loop refactored into `_consume_stream()` async generator
  to support retry-after-compaction without duplicating the event dispatch.
  (files: backend/agents/runner.py)

### Migration notes
- No schema changes. Purely additive behavior.
- Apps with domain-specific read-only tools should add them to
  `COMPACTABLE_TOOLS` in their local `modifier.py` copy for best context
  efficiency. The primitive ships with a generic set (sql, memory, task,
  presentation tools).

## [1.5.0] - 2026-04-01
### Added
- **Session notes**: structured document maintained incrementally throughout
  a conversation, capturing decisions, errors, corrections, and working state.
  Unlike `context_summary` (regenerated on compaction), session notes persist
  across compaction events and accumulate detail over time.
  (files: backend/agents/memory/session_notes.py)
- `session_notes` field on `AgentState`, injected into the LLM prompt
  alongside (and separately from) `context_summary` via the modifier.
  (files: backend/agents/memory/state.py, backend/agents/memory/modifier.py)
- `session_notes` and `notes_token_cursor` columns on `ChatSession` model
  for cross-session persistence of session notes state.
  (files: schema/models.py)
- Threshold-gated extraction: notes update only after 8 000+ new tokens
  AND 2+ tool calls, avoiding LLM calls on trivial exchanges.
  (files: backend/agents/memory/session_notes.py)

### Changed
- Compaction shortcut: when session notes exist, `cleanup_checkpoint` uses
  them directly as the summary instead of running the expensive LLM
  summarization call, saving latency and tokens on every compaction cycle.
  (files: backend/agents/memory/cleanup.py)
- Runner loads existing session notes from the DB before the agent runs,
  injects them into checkpoint state, and triggers extraction post-stream.
  (files: backend/agents/runner.py)
- Modifier now accounts for `session_notes` in token budget and injects
  them as a system message positioned between the system prompt and the
  context summary.
  (files: backend/agents/memory/modifier.py)

### Migration notes
- New columns `session_notes` (Text, nullable) and `notes_token_cursor`
  (Integer, default 0) on the `chat_sessions` table. Run Alembic migration.
- No breaking changes; sessions without notes behave identically to before.

## [1.4.0] - 2026-04-01
### Added
- **AgentMemory model** with 4-type taxonomy (user, feedback, project, reference)
  for structured long-term memory. Includes name, description, content fields
  with staleness tracking via updated_at.
  (files: schema/models.py, contributr: backend/app/db/models/agent_memory.py)
- **AI-powered recall pre-flight**: before each agent turn, loads user memories
  and uses a fast LLM to select the most relevant ones. Injected into the system
  prompt as a "Recalled Context" section with staleness warnings for old memories.
  (files: backend/agents/memory/recall.py)
- **Taxonomy-aware background extraction**: replaces LangMem-based extraction.
  After each turn, reviews conversation against existing memories and outputs
  structured save/update/delete actions using the 4-type taxonomy.
  (files: backend/agents/memory/extraction.py)
- **Structured memory tools** registered in the slug registry: save_memory (typed),
  search_memories (with type filter), update_memory, forget_memory. All use the
  AgentMemory model and ContextVar-based user scoping.
  (files: backend/agents/memory/tools.py)

### Changed
- `build_agent()` and `build_coordinator()` now accept `recalled_context` kwarg
  to inject recalled memories into the system prompt.
  (files: backend/agents/base.py, backend/agents/coordinator.py)
- Runner calls recall pre-flight before agent construction when memory is enabled.
  (files: backend/agents/runner.py)
- Memory tools moved from LangGraph store-based to SQLAlchemy AgentMemory model.
  Tools are now registered in the slug registry (category: "memory") so they can
  be assigned per-agent via the admin UI.
  (files: backend/agents/memory/tools.py)

### Migration notes
- New `agent_memories` table required. Run the Alembic migration.
- Memory tools now use `current_user_id` ContextVar instead of closure-captured
  user_id. Ensure `current_user_id.set()` is called before agent construction.

## [1.3.0] - 2026-04-01
### Added
- Coordinator pattern for supervisor agents: dedicated `build_coordinator()`
  builder with delegation-first tool scoping and the "own the synthesis"
  prompt philosophy. Phase 1 uses create_react_agent; Phase 2+ will
  decompose into an explicit StateGraph with plan/route/delegate/synthesize/verify
  (files: backend/agents/coordinator.py, backend/agents/prompts/coordinator.py)
- `COORDINATOR_SYSTEM_PROMPT` with structured workflow (decompose -> research ->
  synthesize -> implement -> verify), continue-vs-fresh decision matrix,
  and delegation best practices
  (files: backend/agents/prompts/coordinator.py)
- `BEHAVIORAL_DIRECTIVES` appended to every agent's system prompt via
  `resolve_system_prompt()`, encoding honesty and action-awareness rules
  (files: backend/agents/prompts/coordinator.py, backend/agents/base.py)
- `VERIFICATION_PROMPT` for a standalone verification agent that re-derives
  results and issues PASS / PARTIAL / FAIL verdicts
  (files: backend/agents/prompts/coordinator.py)

### Changed
- Runner now routes supervisor agents through `build_coordinator()` instead of
  the generic `build_agent()`, giving supervisors distinct tool scoping and
  prompt behavior
  (files: backend/agents/runner.py)

### Migration notes
- Supervisor agent prompts should be updated to use `COORDINATOR_SYSTEM_PROMPT`
  from `prompts/coordinator.py` (replaces any prior supervisor prompt)
- A `verification-agent` builtin should be added to the app's agent seed list
  and included as a supervisor member

## [1.2.0] - 2026-04-01
### Added
- Ambient invocation context via `contextvars.ContextVar` for `current_user_id`
  and `current_session_id`, allowing any tool or child agent to access the
  invoking user and session without explicit parameter threading
  (files: backend/agents/context/__init__.py, backend/agents/runner.py)

### Changed
- Supervisors with no explicitly assigned tools now receive zero registry tools
  instead of all tools, forcing delegation to member agents as the primary
  execution path; direct tools can still be granted via tool_assignments
  (files: backend/agents/base.py)

### Migration notes
- Existing supervisors that relied on the "no assignment = all tools" fallback
  will need their tool_assignments configured via the admin UI if they should
  retain direct tool access

## [1.1.3] - 2026-04-01
### Fixed
- TaskItem primary key changed from single-column `id` to composite `(id, session_id)`,
  fixing cross-session collisions where `t1` in one session blocked `t1` in another
  (files: schema/models.py, backend/agents/tools/task_tools.py)
- Replaced all `db.get(TaskItem, task_id)` calls with explicit session-scoped
  `select().where()` queries, required by the composite PK and more correct regardless
  (files: backend/agents/tools/task_tools.py)
- Batch-load blocker details in `list_tasks` and `get_task` instead of N+1 queries
  (files: backend/agents/tools/task_tools.py)

## [1.1.2] - 2026-04-01
### Fixed
- Serialize concurrent create_task calls with pg_advisory_xact_lock to
  prevent duplicate task ID generation when LangGraph's ToolNode runs
  multiple create_task calls in parallel via asyncio.gather
  (files: backend/agents/tools/task_tools.py)

## [1.1.1] - 2026-04-01
### Fixed
- Task tools now open independent DB sessions per invocation instead of
  sharing the runner's session, preventing "Session is already flushing"
  errors when LangGraph's checkpoint saver flushes concurrently
  (files: backend/agents/tools/task_tools.py)

## [1.1.0] - 2026-04-01
### Added
- Structured task decomposition system for agent work planning
  (files: schema/models.py, backend/agents/tools/task_tools.py)
- TaskItem database model with session-scoped sequential IDs, status tracking,
  dependency management (blocked_by/blocks), and agent ownership
  (files: schema/models.py)
- Four LangChain tools: create_task, update_task, list_tasks, get_task
  registered as category "task_management"
  (files: backend/agents/tools/task_tools.py)
- Verification gate: nudges agents to run verification when 3+ tasks are
  all completed without any verification step
  (files: backend/agents/tools/task_tools.py)
- task_update SSE event emitted on task mutations for live frontend updates
  (files: backend/agents/runner.py, backend/api/chat.py)
- GET /chat/sessions/{id}/tasks REST endpoint for fetching session tasks
  (files: backend/api/chat.py)
- TaskBoardPanel frontend component showing tasks grouped by status with
  progress bar, dependency indicators, and auto-refresh on SSE events
  (files: frontend/components/task-board-panel.tsx)
- TaskBoardContext in ChatRuntime for SSE-driven task state propagation
  (files: frontend/components/chat-runtime.tsx)
- Tabbed panel switcher (Agents / Tasks) in the chat panel right sidebar
  (files: frontend/components/chat-panel.tsx)
- Extended AgentState with task_board field for future supervisor integration
  (files: backend/agents/memory/state.py)

### Migration notes
- New task_items table requires Alembic migration
- New API client method getSessionTasks() required in consuming apps
- TaskItem type added to INTEGRATION.md Section 3.5

## [1.0.0] - 2026-03-31
### Added
- Initial extraction from contributr and uad36
- Core agent engine: base.py (builder), runner.py (streaming), supervisor.py (delegation)
  (files: backend/agents/base.py, backend/agents/runner.py, backend/agents/supervisor.py)
- Agent registry with AI-enabled check and eager loading
  (files: backend/agents/registry.py)
- Settings cache for memory configuration
  (files: backend/agents/settings_cache.py)
- 3-tier memory system: checkpoint pool, context modifier, summarizer, extraction, cleanup
  (files: backend/agents/memory/pool.py, modifier.py, extraction.py, cleanup.py, state.py, tools.py)
- LLM manager with LiteLLM gateway and encrypted key management
  (files: backend/agents/llm/manager.py)
- Self-registering tool system with session isolation
  (files: backend/agents/tools/registry.py, base.py)
- Platform tools: chat history search, capability gap reporting
  (files: backend/agents/tools/chat_history.py, feedback_gap.py)
- Context window management and summarization
  (files: backend/agents/context/manager.py, summarizer.py)
- Knowledge graph auto-generation from SQLAlchemy metadata
  (files: backend/agents/knowledge/generator.py)
- Chat API with SSE streaming, session CRUD, agent activity tracking
  (files: backend/api/chat.py)
- Frontend chat runtime bridging assistant-ui to backend SSE
  (files: frontend/components/chat-runtime.tsx)
- Chat panel with thread list, agent selector, and resizable activity panel
  (files: frontend/components/chat-panel.tsx)
- Agent activity panel with live streaming and historical display
  (files: frontend/components/agent-activity-panel.tsx)

### Migration notes
- Requires PostgreSQL with pgvector extension
- Requires psycopg (not asyncpg) for LangGraph checkpoint/store
- Creates its own tables via LangGraph setup (checkpoint, store)
- Application models require Alembic migration
