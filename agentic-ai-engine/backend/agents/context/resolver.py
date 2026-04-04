"""Entitlement resolver protocol and default (all-access) implementation.

Each consumer app implements ``EntitlementResolver`` to map their own
user / org / team model into an ``EntitlementContext``.  The resolver is
registered once at application startup and called by the agent runner on
every request.
"""
from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context.entitlements import DataScope, EntitlementContext


@runtime_checkable
class EntitlementResolver(Protocol):
    """Resolve a user id into a fully-populated EntitlementContext."""

    async def resolve(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> EntitlementContext: ...


class DefaultResolver:
    """All-access resolver used when no consumer-specific resolver is registered.

    Safe for single-tenant deployments and backward-compatible with
    existing setups that have no RBAC configuration.
    """

    async def resolve(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> EntitlementContext:
        return EntitlementContext(
            user_id=user_id,
            is_platform_admin=True,
            data_scope=DataScope.ALL,
        )


# ---------------------------------------------------------------------------
# Global resolver registry
# ---------------------------------------------------------------------------

_resolver: EntitlementResolver = DefaultResolver()


def register_entitlement_resolver(resolver: EntitlementResolver) -> None:
    """Replace the global resolver.  Call once at app startup."""
    global _resolver
    _resolver = resolver


def get_entitlement_resolver() -> EntitlementResolver:
    """Return the currently registered resolver."""
    return _resolver
