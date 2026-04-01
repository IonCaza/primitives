"""Seed data for the built-in Presentation Designer agent."""

from app.agents.builtin import BuiltinAgentSpec
from app.agents.prompts.presentation_designer import PRESENTATION_DESIGNER_PROMPT

SPEC = BuiltinAgentSpec(
    slug="presentation-designer",
    name="Presentation Designer",
    description=(
        "Creates beautiful, interactive dashboard presentations from project data. "
        "Generates React component code that renders in a sandboxed iframe with live "
        "data access via the PostMessage bridge. Can delegate domain-specific data "
        "queries to specialist agents and synthesize the results."
    ),
    system_prompt=PRESENTATION_DESIGNER_PROMPT,
    tool_slugs=[
        "find_project",
        "run_sql_query",
        "list_tables",
        "describe_table",
        "save_presentation",
        "get_presentation",
        "update_presentation",
        "get_presentation_template",
        "update_presentation_template",
    ],
    agent_type="supervisor",
    member_slugs=[],
    max_iterations=25,
)
