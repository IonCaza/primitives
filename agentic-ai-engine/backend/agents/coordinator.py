"""Coordinator-grade supervisor builder.

Phase 1: Uses create_react_agent with the coordinator prompt and
delegation-first tool scoping (supervisors get empty registry tools
unless explicitly assigned).  Functionally equivalent to build_agent
but with the enhanced coordinator prompt and task-centric workflow.

Phase 2+ (future): Decompose into an explicit StateGraph with
plan -> route -> delegate -> synthesize -> verify nodes.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import resolve_system_prompt
from app.agents.llm.manager import build_llm_from_provider
from app.agents.memory.modifier import make_state_modifier
from app.agents.memory.pool import get_checkpointer, get_store
from app.agents.memory.state import AgentState
from app.agents.tools.parallel_node import ParallelToolNode
from app.agents.tools.registry import build_tools_for_slugs
from app.db.models.agent_config import AgentConfig
from app.db.models.llm_provider import LlmProvider


def build_coordinator(
    agent_config: AgentConfig,
    provider: LlmProvider,
    db: AsyncSession,
    *,
    extra_tools: list[BaseTool] | None = None,
    recalled_context: str = "",
    skill_context: str = "",
):
    """Build a coordinator agent for supervisor-type agents.

    Supervisors get only their explicitly-assigned registry tools (or none
    if nothing is assigned), forcing them to rely on delegation and task
    management tools passed via *extra_tools*.

    Returns ``(compiled_graph, max_iterations)`` -- same interface as
    ``build_agent`` so the runner can swap transparently.
    """
    llm = build_llm_from_provider(provider, streaming=True)

    tool_slugs = {a.tool_slug for a in agent_config.tool_assignments}
    tools = build_tools_for_slugs(db, tool_slugs) if tool_slugs else []

    if extra_tools:
        tools = tools + extra_tools

    system_prompt = resolve_system_prompt(agent_config)
    if recalled_context:
        system_prompt += "\n\n" + recalled_context
    if skill_context:
        system_prompt += "\n\n## Activated Skills\n\n" + skill_context
    modifier = make_state_modifier(system_prompt, agent_config, provider)

    checkpointer = get_checkpointer()
    store = get_store()

    tool_node = ParallelToolNode(tools) if tools else tools

    agent = create_react_agent(
        model=llm,
        tools=tool_node or tools,
        state_schema=AgentState,
        checkpointer=checkpointer,
        store=store,
        prompt=modifier,
    )
    return agent, agent_config.max_iterations
