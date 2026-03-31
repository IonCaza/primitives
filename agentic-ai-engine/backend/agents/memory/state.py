"""Custom agent state that extends LangGraph's built-in AgentState with a rolling summary."""

from __future__ import annotations

from langgraph.prebuilt.chat_agent_executor import AgentState as _BaseAgentState


class AgentState(_BaseAgentState):
    context_summary: str | None = None
