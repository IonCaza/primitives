import logging
import uuid

from langchain_core.messages import HumanMessage
from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy import select

from app.agents.base import build_agent
from app.db.base import async_session
from app.db.models.agent_config import AgentConfig
from app.db.models.llm_provider import LlmProvider

logger = logging.getLogger(__name__)


def _make_child_runner(member, provider):
    """Factory that returns a clean async function with only ``query: str`` in its signature.

    Each invocation creates its own database session so that a failure in
    one child agent does not poison the transaction for sibling agents.
    """

    async def _run_child(query: str) -> str:
        logger.info("Supervisor delegating to %s: %s", member.slug, query[:120])
        try:
            async with async_session() as child_db:
                child_agent, max_iter = build_agent(
                    member, provider, child_db, extra_tools=None,
                )
                child_thread = str(uuid.uuid4())
                result = await child_agent.ainvoke(
                    {"messages": [HumanMessage(content=query)]},
                    config={
                        "configurable": {"thread_id": child_thread},
                        "recursion_limit": (max_iter or 25) * 2,
                    },
                )
                last_msg = result["messages"][-1]
                response = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
                logger.info("Child agent %s responded (%d chars)", member.slug, len(response))
                return response
        except Exception as e:
            logger.exception("Child agent %s failed: %s", member.slug, e)
            return f"The {member.name} agent encountered an error: {e}"

    return _run_child


def build_delegation_tools(
    member_configs: list[AgentConfig],
    fallback_provider: LlmProvider,
) -> list[BaseTool]:
    """Wrap each member agent as a callable LangChain tool for the supervisor.

    Each tool runs the child agent's full tool-calling loop internally
    and returns the final text response.  Each invocation creates its
    own database session so concurrent delegations don't conflict.
    """
    tools: list[BaseTool] = []

    for member in member_configs:
        if not member.enabled:
            continue

        tool_name = f"ask_{member.slug.replace('-', '_')}"
        tool_desc = (
            f"Delegate a question to the {member.name} agent. "
            f"{member.description or ''} "
            f"Use this when the user's question falls within this agent's domain."
        ).strip()

        runner = _make_child_runner(member, fallback_provider)

        tool = StructuredTool.from_function(
            coroutine=runner,
            name=tool_name,
            description=tool_desc,
        )
        tools.append(tool)

    return tools


def build_prompt_management_tools(
    member_configs: list[AgentConfig],
) -> list[BaseTool]:
    """Build tools that let a supervisor view and update member agent prompts.

    Hierarchy enforcement: the allowed slug set is derived from *member_configs*
    at build time, so the tools can only target agents the supervisor owns.
    """
    allowed_slugs = {m.slug for m in member_configs if m.enabled}
    slug_list = ", ".join(sorted(allowed_slugs))

    async def _view_agent_prompt(agent_slug: str) -> str:
        if agent_slug not in allowed_slugs:
            return (
                f"Error: '{agent_slug}' is not in your hierarchy. "
                f"Available agents: {slug_list}"
            )
        async with async_session() as db:
            agent = await db.scalar(
                select(AgentConfig).where(AgentConfig.slug == agent_slug)
            )
            if not agent:
                return f"Error: Agent '{agent_slug}' not found."
            prompt = agent.system_prompt or "(empty)"
            return (
                f"## System prompt for {agent.name} (`{agent.slug}`)\n"
                f"**Length**: {len(prompt)} chars\n\n"
                f"{prompt}"
            )

    async def _update_agent_prompt(agent_slug: str, new_prompt: str) -> str:
        if agent_slug not in allowed_slugs:
            return (
                f"Error: '{agent_slug}' is not in your hierarchy. "
                f"Available agents: {slug_list}"
            )
        if not new_prompt or not new_prompt.strip():
            return "Error: new_prompt cannot be empty."
        async with async_session() as db:
            agent = await db.scalar(
                select(AgentConfig).where(AgentConfig.slug == agent_slug)
            )
            if not agent:
                return f"Error: Agent '{agent_slug}' not found."
            old_len = len(agent.system_prompt or "")
            agent.system_prompt = new_prompt.strip()
            await db.commit()
            warning = ""
            if agent.is_builtin:
                warning = (
                    " Warning: this is a built-in agent whose prompt resets to "
                    "the default on application restart."
                )
            return (
                f"Updated system prompt for {agent.name} (`{agent.slug}`). "
                f"Previous: {old_len} chars → New: {len(agent.system_prompt)} chars. "
                f"Takes effect on the agent's next invocation.{warning}"
            )

    return [
        StructuredTool.from_function(
            coroutine=_view_agent_prompt,
            name="view_agent_prompt",
            description=(
                "View the current system prompt of a member agent in your "
                "hierarchy. Use this to understand how a child agent is "
                "instructed before deciding whether to update its prompt."
            ),
        ),
        StructuredTool.from_function(
            coroutine=_update_agent_prompt,
            name="update_agent_prompt",
            description=(
                "Update the system prompt of a member agent in your hierarchy. "
                "This replaces the agent's core instructions. Knowledge-graph "
                "context and behavioral directives are appended separately at "
                "runtime. Always call view_agent_prompt first."
            ),
        ),
    ]
