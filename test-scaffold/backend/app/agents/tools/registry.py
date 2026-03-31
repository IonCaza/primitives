from __future__ import annotations

import logging
from typing import Callable

from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.tools.base import ToolDefinition

logger = logging.getLogger(__name__)

ToolFactory = Callable[[AsyncSession], list]

_TOOL_FACTORIES: dict[str, ToolFactory] = {}
_TOOL_DEFINITIONS: dict[str, ToolDefinition] = {}
_SESSION_SAFE_CATEGORIES: set[str] = set()


def register_tool_category(
    category: str,
    definitions: list[ToolDefinition],
    factory: ToolFactory,
    *,
    session_safe: bool = False,
) -> None:
    _TOOL_FACTORIES[category] = factory
    for defn in definitions:
        _TOOL_DEFINITIONS[defn.slug] = defn
    if session_safe:
        _SESSION_SAFE_CATEGORIES.add(category)


def get_all_definitions() -> list[ToolDefinition]:
    return list(_TOOL_DEFINITIONS.values())


def get_definition(slug: str) -> ToolDefinition | None:
    return _TOOL_DEFINITIONS.get(slug)


def _wrap_tool_isolated(tool: BaseTool, factory: ToolFactory) -> BaseTool:
    """Wrap a tool so each invocation gets its own DB session.

    Rebuilds the tool via its factory with a fresh session, then invokes it.
    The original tool's metadata (name, description, args_schema) is preserved.
    """
    from app.db.base import async_session as session_factory

    tool_name = tool.name

    async def _run(**kwargs):
        async with session_factory() as db:
            fresh_tools = {t.name: t for t in factory(db)}
            target = fresh_tools.get(tool_name)
            if target is None:
                return f"Internal error: tool {tool_name} unavailable"
            return await target.ainvoke(kwargs)

    return StructuredTool(
        name=tool.name,
        description=tool.description,
        args_schema=tool.args_schema,
        coroutine=_run,
    )


def build_tools_for_slugs(db: AsyncSession, slugs: set[str]) -> list:
    """Build LangChain tool instances for the requested slugs."""
    tools = []
    for category, factory in _TOOL_FACTORIES.items():
        category_tools = factory(db)
        needs_wrap = category not in _SESSION_SAFE_CATEGORIES
        for t in category_tools:
            if t.name in slugs:
                tools.append(_wrap_tool_isolated(t, factory) if needs_wrap else t)
    return tools


def build_all_tools(db: AsyncSession) -> list:
    tools = []
    for category, factory in _TOOL_FACTORIES.items():
        category_tools = factory(db)
        if category in _SESSION_SAFE_CATEGORIES:
            tools.extend(category_tools)
        else:
            tools.extend(_wrap_tool_isolated(t, factory) for t in category_tools)
    return tools
