# Changelog

All notable changes to the agentic-ai-engine primitive will be documented here.

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
