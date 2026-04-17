# Changelog

All notable changes to the agentic-ai-engine primitive will be documented here.

## [1.13.0] - 2026-04-14
### Added
- **Console entry persistence**: tool calls and thinking blocks are now
  persisted to a `console_entries` table, enabling historical console
  replay when loading previous chat sessions. New `ConsoleEntry` schema,
  `ConsoleEntryOut` response model, and full persistence pipeline in the
  chat API.
  (files: schema/console_entry.py, backend/api/chat.py)
- **Universal `tool_call_start`/`tool_call_end` SSE events**: the runner
  now emits structured tool-call events for *all* tools (not just
  delegation tools), carrying `tool_name`, `args`, and `result`. This
  gives the ConsolePanel live visibility into every tool invocation.
  (files: backend/agents/runner.py)
- **Delegation query tracking**: `agent_start` events now include the
  `query` text the supervisor sent to the child agent. Stored as
  `delegation_query` on `AgentActivity` and surfaced in the
  `AgentActivityOut` API response and `ChildAgent` / `ActivityGroup`
  frontend types.
  (files: backend/agents/runner.py, backend/api/chat.py,
  schema/models.py, frontend/components/chat-runtime.tsx)
- **Child agent memory context**: delegated child agents now receive
  session notes and recalled long-term memories, giving them awareness
  of the ongoing conversation without their own checkpoint history.
  Session notes are injected as `<session_context>` in the query;
  recalled memories are passed via `recalled_context` to `build_agent`.
  (files: backend/agents/supervisor.py)
- **Enhanced delegation tool description**: the `ask_<agent>` tool
  description now includes an `IMPORTANT` clause instructing the
  supervisor to always pass full context (entities, identifiers, details)
  since child agents cannot see prior messages.
  (files: backend/agents/supervisor.py)

### Changed
- **Chat runtime session resilience**: `makeChatModelAdapter` now retries
  up to 1 second (20 × 50ms) for `sessionIdRef` to be populated before
  sending the first message, preventing race conditions on fast initial
  sends. `RuntimeHook` uses a `prevRemoteIdRef` guard to only update
  `sessionIdRef` on actual thread switches, preventing stale overwrites.
  The `session` SSE event is now forwarded to `onAgentEvent` so the
  runtime can update `currentSessionId` immediately.
  (files: frontend/components/chat-runtime.tsx)
- **Runner event type handling**: the `error` event type from the runner
  is now forwarded through the SSE stream as an `error` event, allowing
  RBAC denials and other pre-stream errors to reach the frontend.
  (files: backend/api/chat.py)

### Migration notes
- New `console_entries` table required. See `schema/console_entry.py`
  for the canonical definition. Run Alembic autogenerate.
- New `delegation_query` column (Text, default `""`) on the
  `agent_activities` table. Run Alembic autogenerate.
- `ConsoleEntryRecord` interface must be present in the consumer's
  `@/lib/types` module (same shape as introduced in v1.9.0).
- `AgentActivityRecord` interface should include `delegation_query?: string`.
- No breaking changes; existing sessions without console entries or
  delegation queries render identically to before.

## [1.12.3] - 2026-04-06
### Fixed
- **`backend/requirements.txt`**: aligned dependency minimums with
  INTEGRATION.md and the versions validated in contributr/uad36.
  Previous ranges (`langchain>=0.3`, `langgraph>=0.4`, etc.) still
  pointed at pre-1.0 releases that are incompatible with the
  ParallelToolNode and registry fixes introduced in 1.12.1-1.12.2.
  (files: backend/requirements.txt)

## [1.12.2] - 2026-04-06
### Fixed
- **`_wrap_tool_isolated`**: replaced `target._arun(**kwargs)` with
  `target.coroutine(**kwargs)`.  langchain-core >= 1.2.15 made `config`
  a required keyword-only parameter on `StructuredTool._arun()`, breaking
  the session-isolation wrapper which only receives the tool's own
  arguments from the outer coroutine.  Calling `coroutine` directly
  executes the tool logic without the callback pipeline (preserving the
  no-double-events intent from v1.11.1) and without the `config`
  requirement.
  (files: backend/agents/tools/registry.py)

## [1.12.1] - 2026-04-06
### Fixed
- **ParallelToolNode**: rewritten `_afunc` override to match the
  langgraph-prebuilt 1.0.x `ToolNode` API.  The previous implementation
  used the pre-1.0 signature (`config=None, **kwargs`) and passed a
  spurious `store=` keyword to `_parse_input` (which never accepted it),
  causing `TypeError: ToolNode._parse_input() got an unexpected keyword
  argument 'store'` at runtime.  Now constructs per-call `ToolRuntime`
  instances via `get_config_list` / `_extract_state` and passes them to
  `_arun_one`, matching the upstream contract.
  (files: backend/agents/tools/parallel_node.py)

### Changed
- Minimum langgraph dependency raised from `>=0.4` to `>=1.0`
  (`langgraph-prebuilt >=1.0`).  The pre-1.0 `ToolNode._afunc` signature
  (`config, **kwargs`) is no longer supported.
  (files: backend/agents/tools/parallel_node.py)

### Migration notes
- Consumers on `langgraph <1.0` must upgrade.  Update your dependency
  spec to `langgraph>=1.0,<2` and `langgraph-checkpoint-postgres>=3.0,<4`.
- No code changes beyond the dependency bump; the `ParallelToolNode` API
  that consumers import is unchanged.

## [1.12.0] - 2026-04-05
### Added
- **File and image attachment support in chat**: Users can attach images and
  text files to chat messages. The frontend registers a `CompositeAttachmentAdapter`
  (combining `SimpleImageAttachmentAdapter` + `SimpleTextAttachmentAdapter`) with the
  assistant-ui runtime, resolving the "Attachments are not supported" error. The chat
  model adapter extracts attachment content from user messages and sends them to the
  backend as structured `{type, data, name}` objects. The backend `ChatRequest` now
  accepts an optional `attachments` list, and `run_agent_stream` constructs multimodal
  `HumanMessage` content (with `image_url` parts for images) when attachments are
  present, enabling vision-capable LLMs to process uploaded images.
  (files: frontend/components/chat-runtime.tsx, backend/api/chat.py,
  backend/agents/runner.py)

## [1.11.1] - 2026-04-04
### Fixed
- **Double tool events in `astream_events`**: `_wrap_tool_isolated` called
  `target.ainvoke(kwargs)` which runs the inner tool through LangChain's
  full callback pipeline.  Because `astream_events` installs a
  `LogStreamCallbackHandler` via `contextvars`, the inner tool inherited it
  and emitted its own `on_tool_start`/`on_tool_end` in addition to the
  outer wrapper's events -- producing duplicate `tool_call_start`/
  `tool_call_end` SSE events (and duplicate console entries) for every
  non-session-safe tool.  Changed to `target._arun(**kwargs)` which
  executes the tool logic directly without triggering callbacks.
  (files: backend/agents/tools/registry.py)

## [1.11.0] - 2026-04-04
### Added
- **Supervisor prompt management tools**: `view_agent_prompt` and
  `update_agent_prompt` allow a supervisor agent to inspect and correct the
  system prompts of agents within its hierarchy at runtime. Hierarchy
  enforcement is baked into the closure -- only member agents can be targeted.
  (files: backend/agents/supervisor.py)
- **Coordinator prompt guidance** for prompt management: when-to-use heuristics
  (repeated misinterpretation, outdated schemas) and guardrails (always view
  before update, preserve working sections).
  (files: backend/agents/prompts/coordinator.py)

### Changed
- **Runner** now builds and injects prompt management tools alongside
  delegation tools for supervisor agents.
  (files: backend/agents/runner.py)

### Migration notes
- No schema changes. Purely additive.
- Consumers that fork `supervisor.py` should import
  `build_prompt_management_tools` and add
  `extra_tools.extend(build_prompt_management_tools(member_agents))` in the
  supervisor block of their runner, or copy the updated `runner.py`.
- Built-in agents' prompts are still reset on restart by the seed function.
  To make supervisor prompt edits persistent across restarts, modify the seed
  logic to skip overwriting when a builtin agent's prompt has been
  customized (out of scope for this primitive -- consumer decision).

## [1.10.0] - 2026-04-04
### Added
- **RBAC entitlement framework**: three-layer access model (policy
  hierarchy + explicit resource grants + self-identity) enabling
  configurable, hierarchical data scoping across platform / organization /
  team / user levels.
  (files: backend/agents/context/entitlements.py, backend/agents/context/resolver.py)
- **EntitlementContext** frozen dataclass carrying fully-resolved user
  entitlements: data_scope, organization/team/project/contributor IDs,
  resource grants, agent-tool policies, and RLS session variables.
  (files: backend/agents/context/entitlements.py)
- **EntitlementResolver** protocol with pluggable consumer implementations
  and a backward-compatible DefaultResolver (all-access).
  (files: backend/agents/context/resolver.py)
- **AccessPolicy** database model for hierarchical policy configuration
  with scope_type (platform/org/team/user), data_scope, per-agent tool
  rules, and SQL table allow-lists.
  (files: schema/access_policy.py)
- **ResourceGrant** database model for explicit per-resource sharing
  between users with permission levels and optional expiry.
  (files: schema/access_policy.py)
- **scoped_query()** helper for applying entitlement filters to SQLAlchemy
  select statements, supporting project, org, creator, and contributor
  column scoping across all three entitlement layers.
  (files: backend/agents/tools/scoping.py)
- **current_entitlements** ContextVar re-exported from the context package
  for tool-level access to the resolved entitlement context.
  (files: backend/agents/context/__init__.py)

### Changed
- **Runner** resolves entitlements via the registered EntitlementResolver
  before agent construction and checks agent access before proceeding.
  (files: backend/agents/runner.py)
- **build_agent** and **build_coordinator** filter tool assignments against
  the user's agent-tool policy when an EntitlementContext is available.
  (files: backend/agents/base.py, backend/agents/coordinator.py)

### Migration notes
- New tables `access_policies` and `resource_grants` require Alembic
  migration.  See `schema/access_policy.py` for canonical definitions.
- To enable RBAC, implement `EntitlementResolver` and call
  `register_entitlement_resolver()` at app startup.  Without registration
  the DefaultResolver grants full access (backward compatible).
- Add `from app.agents.context.entitlements import ...` to tool modules
  that need data scoping.  Use `scoped_query()` from
  `app.agents.tools.scoping` for ORM-based tools.
- For text-to-SQL safety, inject `EntitlementContext.rls_vars` as
  `SET LOCAL` session variables before SQL execution and enable Postgres
  RLS on tenant-scoped tables (consumer-specific migration).

## [1.9.5] - 2026-04-02
### Fixed
- Thread-switch pane clearing now hooks into assistant-ui correctly.
  Added `ThreadSwitchDetector` component rendered inside
  `AssistantRuntimeProvider` that uses `useThreadListItem` (assistant-
  ui's own hook) to subscribe to `remoteId` changes. When the active
  thread changes, the detector calls `onThreadSwitch` to clear all
  pane state. Previous approaches that relied on `useEffect` in the
  `runtimeHook` or state updates from `initialize()` failed because
  `unstable_useRemoteThreadListRuntime` does not propagate those
  changes back through React's standard rendering pipeline.
  (files: frontend/components/chat-runtime.tsx)

## [1.9.4] - 2026-04-02
### Fixed
- Clear panel state directly from `initialize()` in the thread list
  adapter. This is the one function that **always** executes when the
  user clicks "New Thread". Previous approaches relied on `useEffect`
  in `RuntimeHook` detecting a `remoteId` change, but
  `unstable_useRemoteThreadListRuntime` may not propagate that change
  back to the parent component's render cycle, so the effect never
  fires and stale data from the previous thread persists.
  `onThreadSwitchRef` is now passed to `useThreadListAdapter` and
  called from `initialize()` after setting the new session ID.
  (files: frontend/components/chat-runtime.tsx)

## [1.9.3] - 2026-04-02
### Fixed
- Defence-in-depth fix for thread-switch pane clearing. The v1.9.2
  staleness guard alone was insufficient because
  `unstable_useRemoteThreadListRuntime` does not reliably fire the
  `useEffect` in `RuntimeHook` on every thread switch. New approach:
  `panelSessionRef` tracks which session the panel state belongs to;
  `ensureSessionClean()` (cheap ref comparison) resets all pane state
  on mismatch. Called from three independent checkpoints: a post-render
  `useEffect` (catches the switch even if `onThreadSwitch` never fires),
  `onRunStart` (catches it when the user sends the first message), and
  `onAgentEvent` (catches it when the first SSE event arrives).
  (files: frontend/components/chat-runtime.tsx)

## [1.9.2] - 2026-04-02
### Fixed
- Thread switch now correctly clears Agents, Tasks, and Console panes.
  A stale-load race condition allowed the previous thread's `load()`
  callback to repopulate state via refs after `onThreadSwitch` had
  already cleared it. Added a `sessionIdRef` guard in
  `useHistoryAdapter` to discard results when the active session has
  changed since the fetch began.
  (files: frontend/components/chat-runtime.tsx)

## [1.9.1] - 2026-04-02
### Fixed
- `create_task` tool no longer rejects `blocked_by` forward-references
  when tasks are created in parallel batches via `ParallelToolNode`;
  validation downgraded from hard error to debug log since `list_tasks`
  and `get_task` already handle missing blocker refs gracefully.
  (files: backend/agents/tools/task_tools.py)

## [1.9.0] - 2026-04-02
### Added
- **ConsolePanel** frontend component: live + historical visualization
  of tool calls (with expandable args/results, duration badges, error
  highlighting) and thinking blocks, grouped by triggering user message.
  (files: frontend/components/console-panel.tsx)
- **Console state in ChatRuntime**: `LiveConsoleEntry`, `ConsoleGroup`
  types exported; `ChildAgentContextValue` now includes
  `liveConsoleEntries`, `historicalConsole`, and `sessionIdRef`;
  SSE routing for `tool_call_start`, `tool_call_end`, `thinking` events
  populates console state alongside the existing chat display;
  `buildConsoleGroups()` loads historical console from message history.
  (files: frontend/components/chat-runtime.tsx)

### Changed
- **ChatPanel** side panel now has three tabs — Agents, Tasks, Console —
  giving equal visibility to agent delegation, task decomposition, and
  tool/thinking introspection.
  (files: frontend/components/chat-panel.tsx)
- **ConsoleEntryRecord** type must now be present in the consumer's
  `@/lib/types` module (see INTEGRATION.md).
  (files: frontend/components/chat-runtime.tsx, frontend/components/console-panel.tsx)

### Migration notes
- Add `ConsoleEntryRecord` interface to your `@/lib/types` file (see
  INTEGRATION.md section 3.2 for the exact shape).
- Copy `console-panel.tsx` to your components directory.
- Ensure your `ChatMessage` type includes `console_entries` field and
  your API returns it from message history endpoints.
- Add `@/components/ui/badge` shadcn component if not already installed.

## [1.8.2] - 2026-04-02
### Fixed
- **ParallelToolNode**: pass `input_type` to `_arun_one()` and use
  `_combine_tool_outputs()` for result formatting, fixing a `TypeError`
  with langgraph >=0.6.11 where `_arun_one` gained a required
  `input_type` parameter.
  (files: backend/agents/tools/parallel_node.py)
- **Embedding dimension mismatch**: `build_embeddings_from_provider` now
  accepts an optional `dims` keyword and forwards it as the `dimensions`
  parameter to litellm, preventing `DataException: expected N dimensions,
  not M` when the store table was created with fewer dimensions than the
  model's native output (e.g. store has 1536 but text-embedding-3-large
  produces 3072).
  (files: backend/agents/llm/manager.py)
### Migration notes
- Consumers should detect existing `store_vectors` table dimensions at
  startup and pass `dims=<existing>` to `build_embeddings_from_provider`
  to avoid dimension mismatches. See updated INTEGRATION.md section 2.4.

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
