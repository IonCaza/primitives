"""Query-scoping helper for RBAC-aware agent tools.

Provides ``scoped_query()`` which applies the three entitlement layers
(policy scope, explicit grants, self-identity) to a SQLAlchemy ``select``
statement.  Tool authors call it with whichever columns are relevant:

    stmt = select(Commit)
    stmt = scoped_query(
        stmt,
        project_col=Repository.project_id,   # Layer A + B
        contributor_col=Commit.contributor_id, # Layer C (self-identity)
    )
"""
from __future__ import annotations

import uuid

from sqlalchemy import or_
from sqlalchemy.sql import Select

from app.agents.context.entitlements import DataScope, EntitlementContext, current_entitlements


def scoped_query(
    stmt: Select,
    *,
    project_col=None,
    org_col=None,
    creator_col=None,
    contributor_col=None,
    resource_type: str | None = None,
    resource_id_col=None,
) -> Select:
    """Append entitlement WHERE clauses to *stmt*.

    Parameters
    ----------
    stmt:
        A SQLAlchemy ``select()`` to filter.
    project_col:
        Column holding a project UUID.  Filters to the user's accessible
        projects (Layer A) plus any explicitly granted projects (Layer B).
    org_col:
        Column holding an organization UUID.  Filters to the user's orgs
        (Layer A).
    creator_col:
        Column holding the creating user's UUID.  Matches ``user_id``
        (Layer C self-identity for resources *created by* the user).
    contributor_col:
        Column holding a contributor UUID.  Matches any of the user's
        linked contributor identities (Layer C self-identity for VCS data).
    resource_type / resource_id_col:
        For entity-level grants (Layer B).  Matches if the resource has
        an explicit ``ResourceGrant`` for this user.
    """
    ctx = current_entitlements.get()
    if ctx is None or ctx.is_platform_admin or ctx.data_scope == DataScope.ALL:
        return stmt

    conditions: list = []

    # Layer A — policy scope: org-level
    if org_col is not None and ctx.organization_ids:
        conditions.append(org_col.in_(ctx.organization_ids))

    # Layer A + B — policy scope + granted projects
    if project_col is not None:
        all_project_ids = ctx.project_ids | ctx.grants_for_type("project")
        if all_project_ids:
            conditions.append(project_col.in_(all_project_ids))

    # Layer B — explicit entity grants
    if resource_type and resource_id_col is not None:
        granted = ctx.grants_for_type(resource_type)
        if granted:
            conditions.append(resource_id_col.in_(granted))

    # Layer C — self-identity (creator)
    if creator_col is not None:
        conditions.append(creator_col == ctx.user_id)

    # Layer C — self-identity (contributor)
    if contributor_col is not None and ctx.contributor_ids:
        conditions.append(contributor_col.in_(ctx.contributor_ids))

    if not conditions:
        return stmt

    return stmt.where(or_(*conditions))
