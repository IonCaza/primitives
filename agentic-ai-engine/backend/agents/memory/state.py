"""Custom agent state that extends LangGraph's built-in AgentState."""

from __future__ import annotations

from langgraph.prebuilt.chat_agent_executor import AgentState as _BaseAgentState


class AgentState(_BaseAgentState):
    context_summary: str | None = None
    session_notes: str | None = None
    task_board: list[dict] | None = None
