"""Entitlement context for RBAC-aware agent execution.

The ``EntitlementContext`` carries a fully-resolved picture of what the
current user is allowed to see and do.  It is populated once per request
by an ``EntitlementResolver`` (consumer-provided) and stored in a
``ContextVar`` so that every tool invocation — including those running in
parallel or inside delegated child agents — can read it without explicit
parameter threading.

Three layers compose the effective access set:

* **Layer A – Policy hierarchy** (platform → org → team → user):
  determines ``data_scope``, ``agent_tool_policies``, and
  ``sql_allowed_tables``.

* **Layer B – Explicit grants**: additive per-resource sharing
  (``resource_grants``).

* **Layer C – Self-identity**: the user always sees their own data
  (``contributor_ids`` for contributr, ``user_id`` match for uad36
  ``created_by``).
"""
from __future__ import annotations

import contextvars
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DataScope(str, Enum):
    """Visibility level resolved from the access-policy hierarchy."""
    OWN = "own"
    TEAM = "team"
    ORG = "org"
    ALL = "all"


@dataclass(frozen=True)
class ResourceGrant:
    """A single explicit resource-sharing entry."""
    resource_type: str
    resource_id: uuid.UUID
    permission: str  # "view" | "edit" | "admin"


@dataclass(frozen=True)
class AgentToolPolicy:
    """Per-agent tool allow-list for a specific user."""
    agent_slug: str
    allowed_tool_slugs: frozenset[str] | None  # None ⇒ all tools assigned to the agent


@dataclass(frozen=True)
class EntitlementContext:
    """Fully-resolved entitlements for the current request."""

    user_id: uuid.UUID
    is_platform_admin: bool = False

    # Layer A — policy-resolved scope
    data_scope: DataScope = DataScope.ALL
    organization_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    team_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    project_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)

    # Layer B — explicit grants
    resource_grants: frozenset[ResourceGrant] = field(default_factory=frozenset)

    # Layer C — self-identity (contributr: user ↔ contributor links)
    contributor_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)

    # Agent + tool ACL
    agent_tool_policies: dict[str, AgentToolPolicy] = field(default_factory=dict)

    # Role context for granular checks (e.g. {"org:<uuid>": "admin"})
    roles: dict[str, str] = field(default_factory=dict)

    # Sql allow-list resolved from policy (None ⇒ no restriction)
    sql_allowed_tables: frozenset[str] | None = None

    # ------------------------------------------------------------------
    # RLS session variables
    # ------------------------------------------------------------------

    @property
    def rls_vars(self) -> dict[str, str]:
        """Key-value pairs to ``SET LOCAL`` before SQL tool execution.

        All values are strings because ``current_setting()`` in Postgres
        returns text.  Array-typed values use comma separation so
        ``string_to_array(…, ',')`` can consume them in RLS policies.
        """
        granted_ids_by_type: dict[str, list[str]] = {}
        for g in self.resource_grants:
            granted_ids_by_type.setdefault(g.resource_type, []).append(str(g.resource_id))

        all_project_ids = set(str(p) for p in self.project_ids)
        for pid in granted_ids_by_type.get("project", []):
            all_project_ids.add(pid)

        return {
            "app.current_user_id": str(self.user_id),
            "app.data_scope": self.data_scope.value,
            "app.current_org_ids": ",".join(str(o) for o in self.organization_ids),
            "app.current_project_ids": ",".join(all_project_ids),
            "app.current_contributor_ids": ",".join(str(c) for c in self.contributor_ids),
            "app.current_team_ids": ",".join(str(t) for t in self.team_ids),
            **{
                f"app.granted_{rtype}_ids": ",".join(ids)
                for rtype, ids in granted_ids_by_type.items()
            },
        }

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def can_invoke_agent(self, agent_slug: str) -> bool:
        """Return True if this user is allowed to invoke *agent_slug*."""
        if self.is_platform_admin or not self.agent_tool_policies:
            return True
        return agent_slug in self.agent_tool_policies

    def allowed_tools_for_agent(self, agent_slug: str) -> frozenset[str] | None:
        """Return the tool allow-list for *agent_slug*, or None (= all)."""
        if self.is_platform_admin:
            return None
        policy = self.agent_tool_policies.get(agent_slug)
        if policy is None:
            return None
        return policy.allowed_tool_slugs

    def has_grant(self, resource_type: str, resource_id: uuid.UUID) -> bool:
        return any(
            g.resource_type == resource_type and g.resource_id == resource_id
            for g in self.resource_grants
        )

    def grants_for_type(self, resource_type: str) -> frozenset[uuid.UUID]:
        return frozenset(
            g.resource_id for g in self.resource_grants
            if g.resource_type == resource_type
        )


# ---------------------------------------------------------------------------
# Ambient context var
# ---------------------------------------------------------------------------

current_entitlements: contextvars.ContextVar[EntitlementContext | None] = contextvars.ContextVar(
    "current_entitlements", default=None,
)
