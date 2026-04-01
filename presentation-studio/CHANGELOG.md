# Changelog

## 1.0.0 — 2026-03-31

Initial extraction from contributr.

### Schema
- `schema/presentation.py` — PresentationTemplate, Presentation, PresentationVersion models

### Backend
- `backend/api/presentations.py` — Full CRUD API, template management, data proxy for iframe bridge
- `backend/agents/tools/presentation.py` — Agent tools: save/get/update presentation and template
- `backend/agents/builtin/presentation_designer.py` — Builtin supervisor agent spec
- `backend/agents/prompts/presentation_designer.py` — System prompt with SDK reference

### Frontend
- `frontend/components/presentation-studio.tsx` — Split-pane chat + live preview editor
- `frontend/components/presentation-sandbox.tsx` — Sandboxed iframe renderer with PostMessage bridge
- `frontend/hooks/use-presentations.ts` — React Query hooks for all presentation operations
- `frontend/pages/presentations/page.tsx` — Presentation list page
- `frontend/pages/presentations/new/page.tsx` — New presentation form with color palette picker
- `frontend/pages/presentations/[presentationId]/page.tsx` — Studio detail page

### Config
- `config/v1-template.html` — Canonical v1 template HTML with bridge, hooks, Recharts, Tailwind
- `config/env.example` — Environment variables (none beyond agentic-ai-engine)

### Canonicalization notes
- PostMessage protocol type changed from `contributr_query` to `presentation_query`
- Bridge namespace changed from `contributr.query()` to `bridge.query()`
- CSS classes changed from `contributr-loading`/`contributr-error` to `studio-loading`/`studio-error`
- Domain-specific ALLOWED_TOOL_CATEGORIES reduced to `sql_query` base; extension point documented
- Domain-specific analyst member_slugs removed from designer spec; extension point documented
- Prompt generalized to remove specific `ask_*_analyst` references
- Example prompts generalized from contribution-analytics-specific to generic dashboard examples
- Palette preset renamed from "Application"/"Contributr app colors" to "Default"/"Warm & balanced palette"
- ChatRuntime import changed from `ContributrChatRuntime` to generic `ChatRuntime`
