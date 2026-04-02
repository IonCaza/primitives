"""Example built-in Verification Agent.

Demonstrates a tool-less agent used within supervisor workflows to
independently confirm that work products are correct and complete.
"""

from app.agents.builtin import BuiltinAgentSpec
from app.agents.prompts.coordinator import VERIFICATION_PROMPT

SPEC = BuiltinAgentSpec(
    slug="verification-agent",
    name="Verification Agent",
    description=(
        "Independently confirms work products are correct, complete, and "
        "honestly reported. Re-derives key results, checks edge cases, and "
        "issues a PASS / PARTIAL / FAIL verdict."
    ),
    system_prompt=VERIFICATION_PROMPT,
    tool_slugs=[],
    agent_type="standard",
)
