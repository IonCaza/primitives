"""Client-side screen context tools and application route discovery.

The client tools (``get_screen_context``, ``navigate_user``) run on the
frontend via the interrupt/resume protocol.  They are registered in the
tool registry so they appear in the admin UI and can be assigned to
agents, but at runtime they are built via ``make_client_tool`` (not the
registry factory) since they don't need a database session.

``get_app_routes`` is a lightweight server-side tool that returns the
application's navigable route map so agents can discover pages on-demand
without hardcoding routes in their system prompts.

## Extension point

The ``APP_ROUTES`` dict below is a **placeholder**.  Each application
should replace the contents with its own navigable pages. The shape is
``{ "group_name": [ { "path": str, "description": str } ] }``.  Path
parameters use curly-brace placeholders (e.g. ``{projectId}``) that
agents are expected to resolve from the current screen context or by
delegating to a specialist agent.
"""

from __future__ import annotations

import json

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agents.runner import make_client_tool
from app.agents.tools.base import ToolDefinition
from app.agents.tools.registry import register_tool_category

CATEGORY = "client_context"

# --- EXTENSION POINT ----------------------------------------------------
# Replace the contents of APP_ROUTES with your application's pages.
# The default entries below are illustrative examples only.
APP_ROUTES: dict[str, list[dict[str, str]]] = {
    "top_level": [
        {"path": "/dashboard", "description": "Main dashboard with overview and key metrics"},
        {"path": "/settings", "description": "User and workspace settings"},
    ],
    "entity": [
        {"path": "/items", "description": "List of all items"},
        {"path": "/items/{itemId}", "description": "Individual item detail"},
    ],
}
# ------------------------------------------------------------------------


class NavigateUserArgs(BaseModel):
    """Typed argument schema for the ``navigate_user`` client tool.

    Providing an explicit schema prevents the LLM from guessing argument
    names (e.g. ``url`` or ``route``) and forces it to use ``path``.
    """

    path: str = Field(
        description="The URL path to navigate to, e.g. /items/{itemId}",
    )


DEFINITIONS = [
    ToolDefinition(
        slug="get_screen_context",
        name="get_screen_context",
        description=(
            "Get information about what the user currently sees on their screen. "
            "Returns the current page, visible data, active filters, and UI state."
        ),
        category=CATEGORY,
        concurrency_safe=True,
    ),
    ToolDefinition(
        slug="navigate_user",
        name="navigate_user",
        description=(
            "Navigate the user to a specific page in the application. "
            "After navigation, returns the screen context of the new page."
        ),
        category=CATEGORY,
    ),
    ToolDefinition(
        slug="get_app_routes",
        name="get_app_routes",
        description=(
            "Get the map of all navigable pages in the application. "
            "Returns routes grouped by area with path templates and descriptions. "
            "Call this before navigate_user to discover available pages."
        ),
        category=CATEGORY,
        concurrency_safe=True,
    ),
]


def build_screen_context_tools() -> list:
    """Build the client-side screen/navigation tools plus ``get_app_routes``."""

    @tool
    def get_app_routes() -> str:
        """Get all navigable pages in the application.

        Returns a JSON object with route groups. Path parameters like
        ``{itemId}`` are identifiers -- resolve them from the current
        ``get_screen_context`` params field, or by delegating to a
        specialist agent that can look the identifier up by name.
        """
        return json.dumps(APP_ROUTES, indent=2)

    return [
        make_client_tool(
            name="get_screen_context",
            description=DEFINITIONS[0].description,
        ),
        make_client_tool(
            name="navigate_user",
            description=DEFINITIONS[1].description,
            args_schema=NavigateUserArgs,
        ),
        get_app_routes,
    ]


def _factory(_db):
    return build_screen_context_tools()


register_tool_category(
    CATEGORY,
    DEFINITIONS,
    _factory,
    session_safe=True,
    concurrency_safe=True,
)
