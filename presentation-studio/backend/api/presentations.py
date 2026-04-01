"""Presentations API: CRUD, template management, and data proxy for PostMessage bridge."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import User
from app.db.models.chat import ChatSession
from app.db.models.agent_config import AgentConfig
from app.db.models.presentation import Presentation, PresentationTemplate, PresentationVersion
from app.auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["presentations"])


# ── Schemas ────────────────────────────────────────────────────────────

class PresentationResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    description: str | None
    component_code: str
    template_version: int
    prompt: str
    chat_session_id: uuid.UUID | None
    created_by_id: uuid.UUID
    status: str
    created_at: datetime
    updated_at: datetime | None


class PresentationListItem(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    prompt: str
    status: str
    template_version: int
    created_at: datetime
    updated_at: datetime | None


class PresentationCreate(BaseModel):
    title: str
    description: str | None = None
    component_code: str = ""
    template_version: int | None = None
    prompt: str = ""
    chat_session_id: uuid.UUID | None = None
    status: str = "draft"


class PresentationUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    component_code: str | None = None
    template_version: int | None = None
    status: str | None = None


class PresentationVersionResponse(BaseModel):
    id: uuid.UUID
    presentation_id: uuid.UUID
    version_number: int
    component_code: str
    template_version: int
    change_summary: str | None
    created_at: datetime


class TemplateResponse(BaseModel):
    id: uuid.UUID
    version: int
    template_html: str
    description: str
    created_at: datetime


class TemplateCreate(BaseModel):
    template_html: str
    description: str


class DataQueryRequest(BaseModel):
    tool_slug: str
    params: dict = {}


async def _ensure_chat_session(
    db: AsyncSession,
    presentation: Presentation,
    user_id: uuid.UUID,
) -> uuid.UUID:
    """Return the presentation's chat_session_id, creating one if missing."""
    if presentation.chat_session_id:
        return presentation.chat_session_id

    agent_row = (await db.execute(
        select(AgentConfig).where(AgentConfig.slug == "presentation-designer").limit(1)
    )).scalar_one_or_none()

    session = ChatSession(
        user_id=user_id,
        agent_id=agent_row.id if agent_row else None,
        title=f"Presentation: {presentation.title[:200]}",
    )
    db.add(session)
    await db.flush()

    presentation.chat_session_id = session.id
    return session.id


# ── Project-scoped presentation routes ─────────────────────────────────

@router.get(
    "/projects/{project_id}/presentations",
    response_model=list[PresentationListItem],
)
async def list_presentations(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Presentation)
        .where(Presentation.project_id == project_id)
        .order_by(Presentation.created_at.desc())
    )
    return [
        PresentationListItem(
            id=p.id,
            title=p.title,
            description=p.description,
            prompt=p.prompt,
            status=p.status,
            template_version=p.template_version,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
        for p in result.scalars().all()
    ]


@router.post(
    "/projects/{project_id}/presentations",
    response_model=PresentationResponse,
    status_code=201,
)
async def create_presentation(
    project_id: uuid.UUID,
    body: PresentationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tv = body.template_version
    if tv is None:
        latest = await db.execute(
            select(func.max(PresentationTemplate.version))
        )
        tv = latest.scalar() or 1

    pres = Presentation(
        project_id=project_id,
        title=body.title,
        description=body.description,
        component_code=body.component_code,
        template_version=tv,
        prompt=body.prompt,
        chat_session_id=body.chat_session_id,
        created_by_id=user.id,
        status=body.status,
    )
    db.add(pres)
    await db.flush()

    await _ensure_chat_session(db, pres, user.id)

    version = PresentationVersion(
        presentation_id=pres.id,
        version_number=1,
        component_code=pres.component_code,
        template_version=tv,
        change_summary="Initial creation",
    )
    db.add(version)
    await db.commit()
    await db.refresh(pres)
    return pres


@router.get(
    "/projects/{project_id}/presentations/{presentation_id}",
    response_model=PresentationResponse,
)
async def get_presentation(
    project_id: uuid.UUID,
    presentation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.project_id == project_id,
        )
    )
    pres = result.scalar_one_or_none()
    if not pres:
        raise HTTPException(404, "Presentation not found")

    if not pres.chat_session_id:
        await _ensure_chat_session(db, pres, user.id)
        await db.commit()
        await db.refresh(pres)

    return pres


@router.patch(
    "/projects/{project_id}/presentations/{presentation_id}",
    response_model=PresentationResponse,
)
async def update_presentation(
    project_id: uuid.UUID,
    presentation_id: uuid.UUID,
    body: PresentationUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.project_id == project_id,
        )
    )
    pres = result.scalar_one_or_none()
    if not pres:
        raise HTTPException(404, "Presentation not found")

    code_changed = False
    if body.title is not None:
        pres.title = body.title
    if body.description is not None:
        pres.description = body.description
    if body.component_code is not None and body.component_code != pres.component_code:
        pres.component_code = body.component_code
        code_changed = True
    if body.template_version is not None:
        pres.template_version = body.template_version
        code_changed = True
    if body.status is not None:
        pres.status = body.status
    pres.updated_at = datetime.now(timezone.utc)

    if code_changed:
        max_ver = await db.execute(
            select(func.max(PresentationVersion.version_number)).where(
                PresentationVersion.presentation_id == pres.id
            )
        )
        next_ver = (max_ver.scalar() or 0) + 1
        version = PresentationVersion(
            presentation_id=pres.id,
            version_number=next_ver,
            component_code=pres.component_code,
            template_version=pres.template_version,
            change_summary=f"Update v{next_ver}",
        )
        db.add(version)

    await db.commit()
    await db.refresh(pres)
    return pres


@router.delete(
    "/projects/{project_id}/presentations/{presentation_id}",
    status_code=204,
)
async def delete_presentation(
    project_id: uuid.UUID,
    presentation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.project_id == project_id,
        )
    )
    pres = result.scalar_one_or_none()
    if not pres:
        raise HTTPException(404, "Presentation not found")
    await db.delete(pres)
    await db.commit()


@router.get(
    "/projects/{project_id}/presentations/{presentation_id}/versions",
    response_model=list[PresentationVersionResponse],
)
async def list_presentation_versions(
    project_id: uuid.UUID,
    presentation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Presentation).where(
            Presentation.id == presentation_id,
            Presentation.project_id == project_id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Presentation not found")

    versions = await db.execute(
        select(PresentationVersion)
        .where(PresentationVersion.presentation_id == presentation_id)
        .order_by(PresentationVersion.version_number.desc())
    )
    return list(versions.scalars().all())


# ── Global template routes ─────────────────────────────────────────────

@router.get("/presentations/templates/latest", response_model=TemplateResponse)
async def get_latest_template(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PresentationTemplate).order_by(PresentationTemplate.version.desc()).limit(1)
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(404, "No templates found")
    return tmpl


@router.get("/presentations/templates/{version}", response_model=TemplateResponse)
async def get_template_by_version(
    version: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PresentationTemplate).where(PresentationTemplate.version == version)
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(404, f"Template version {version} not found")
    return tmpl


@router.post("/presentations/templates", response_model=TemplateResponse, status_code=201)
async def create_template_version(
    body: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    max_ver = await db.execute(select(func.max(PresentationTemplate.version)))
    next_version = (max_ver.scalar() or 0) + 1

    tmpl = PresentationTemplate(
        version=next_version,
        template_html=body.template_html,
        description=body.description,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return tmpl


# ── Data proxy for PostMessage bridge ──────────────────────────────────

ALLOWED_TOOL_CATEGORIES: frozenset[str] = frozenset({
    "sql_query",
})
"""Override this set in your app to add domain-specific tool categories
that are safe for presentation data queries."""

_SQL_MAX_ROWS = 200


async def _execute_sql_json(db: AsyncSession, sql: str) -> dict:
    """Run a read-only SELECT and return structured JSON rows.

    Uses the same guardrails as the run_sql_query agent tool but returns
    ``{"columns": [...], "rows": [{col: val, ...}, ...]}`` instead of a
    formatted text table so the iframe bridge can consume it directly.
    """
    from app.agents.tools.sql_query import _validate_select_only

    error = _validate_select_only(sql)
    if error:
        raise HTTPException(400, f"BLOCKED: {error}")

    limited = sql.rstrip().rstrip(";")
    limited = f"SELECT * FROM ({limited}) AS _q LIMIT {_SQL_MAX_ROWS}"

    from sqlalchemy import text as sa_text
    try:
        result = await db.execute(sa_text(limited))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
    except Exception as exc:
        logger.warning("Presentation SQL query failed: %s — %s", sql, exc)
        raise HTTPException(400, f"Query error: {exc}")

    for row in rows:
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
            elif isinstance(v, (bytes, memoryview)):
                row[k] = str(v)

    return {"columns": columns, "rows": rows}


@router.post("/projects/{project_id}/presentations/data")
async def execute_presentation_query(
    project_id: uuid.UUID,
    body: DataQueryRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    from app.agents.tools.registry import get_definition, build_tools_for_slugs

    defn = get_definition(body.tool_slug)
    if not defn:
        raise HTTPException(400, f"Unknown tool: {body.tool_slug}")
    if defn.category not in ALLOWED_TOOL_CATEGORIES:
        raise HTTPException(403, f"Tool category '{defn.category}' is not allowed for presentation queries")

    if body.tool_slug == "run_sql_query":
        sql = body.params.get("sql", "")
        if not sql:
            raise HTTPException(400, "Missing 'sql' parameter")
        result = await _execute_sql_json(db, sql)
        return {"result": result}

    tools = build_tools_for_slugs(db, {body.tool_slug})
    if not tools:
        raise HTTPException(400, f"Could not build tool: {body.tool_slug}")

    tool = tools[0]
    try:
        params = {**body.params, "project_id": str(project_id)}
        result = await tool.ainvoke(params)
        return {"result": result}
    except Exception as e:
        raise HTTPException(500, f"Tool execution error: {e}")
