"""Client-side tools for UI screen context and navigation.

These tools use ``make_client_tool`` to pause the graph via LangGraph
``interrupt()`` and wait for the frontend to supply the result.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool

from app.agents.runner import make_client_tool


def build_screen_context_tools() -> list[BaseTool]:
    """Return client-side tools for reading screen context and navigating."""
    return [
        make_client_tool(
            name="get_screen_context",
            description=(
                "Get information about what the user currently sees on their screen. "
                "Returns the current page, visible data, active filters, and UI state. "
                "Call this when you need to understand the user's current context "
                "before answering questions about what they're looking at."
            ),
        ),
        make_client_tool(
            name="navigate_user",
            description=(
                "Navigate the user to a specific page in the application. "
                "After navigation, returns the screen context of the new page. "
                "Use this to take the user to relevant data they're asking about."
            ),
        ),
    ]
