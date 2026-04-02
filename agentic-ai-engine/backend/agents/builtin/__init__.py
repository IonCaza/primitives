from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BuiltinAgentSpec:
    slug: str
    name: str
    description: str
    system_prompt: str
    tool_slugs: list[str] = field(default_factory=list)
    agent_type: str = "standard"
    member_slugs: list[str] = field(default_factory=list)
    max_iterations: int = 25


def get_builtin_agents() -> list[BuiltinAgentSpec]:
    """Return all built-in agent specs (standard agents first, then supervisors).

    --- EXTENSION POINT ---
    Add your domain-specific agent imports here.  Each agent module should
    export a ``SPEC`` instance of :class:`BuiltinAgentSpec`.
    """
    from app.agents.builtin.text_to_sql import SPEC as text_to_sql
    from app.agents.builtin.verification_agent import SPEC as verification_agent
    from app.agents.builtin.supervisor import SPEC as supervisor

    return [
        text_to_sql,
        verification_agent,
        # --- domain-specific agents go here ---
        supervisor,  # supervisors last so members are seeded first
    ]
