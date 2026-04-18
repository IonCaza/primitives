"""Example built-in Supervisor agent.

Demonstrates the coordinator pattern: no direct tools, delegates to
member agents, uses structured task decomposition to manage complex work.
"""

from app.agents.builtin import BuiltinAgentSpec
from app.agents.prompts.coordinator import COORDINATOR_SYSTEM_PROMPT

SPEC = BuiltinAgentSpec(
    slug="supervisor",
    name="Supervisor",
    description=(
        "Coordinating agent that orchestrates specialist agents. "
        "Decomposes complex requests into tasks, delegates to domain "
        "experts, synthesizes cross-domain responses, and verifies "
        "results before reporting."
    ),
    system_prompt=COORDINATOR_SYSTEM_PROMPT,
    tool_slugs=[
        # Task management (work decomposition & tracking)
        "create_task",
        "update_task",
        "list_tasks",
        "get_task",
        # Skills (reusable prompts)
        "use_skill",
        "list_skills",
        # 3-tier memory
        "save_memory",
        "search_memories",
        "update_memory",
        "forget_memory",
        # Screen context & navigation (client-side tools)
        "get_screen_context",
        "navigate_user",
        "get_app_routes",
    ],
    agent_type="supervisor",
    member_slugs=[
        "text-to-sql",
        "verification-agent",
        # --- add your domain agent slugs here ---
    ],
    max_iterations=50,
)
