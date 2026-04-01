from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.models import User
from app.db.models.email_template import EmailTemplate
from app.auth.dependencies import require_admin
from app.services.email import _render

router = APIRouter(prefix="/settings/email-templates", tags=["email-templates"])


# ── Schemas ──────────────────────────────────────────────────────────────

class EmailTemplateOut(BaseModel):
    id: str
    slug: str
    name: str
    subject: str
    body_html: str
    body_text: str
    variables: dict
    is_builtin: bool

    model_config = {"from_attributes": True}


class EmailTemplateUpdate(BaseModel):
    subject: str | None = None
    body_html: str | None = None
    body_text: str | None = None


class EmailTemplatePreviewRequest(BaseModel):
    variables: dict | None = None


class EmailTemplatePreviewResponse(BaseModel):
    subject: str
    body_html: str


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("", response_model=list[EmailTemplateOut])
async def list_email_templates(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(EmailTemplate).order_by(EmailTemplate.slug))
    rows = result.scalars().all()
    return [
        EmailTemplateOut(
            id=str(r.id), slug=r.slug, name=r.name, subject=r.subject,
            body_html=r.body_html, body_text=r.body_text,
            variables=r.variables, is_builtin=r.is_builtin,
        )
        for r in rows
    ]


@router.get("/{slug}", response_model=EmailTemplateOut)
async def get_email_template(
    slug: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.slug == slug))
    tpl = result.scalar_one_or_none()
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return EmailTemplateOut(
        id=str(tpl.id), slug=tpl.slug, name=tpl.name, subject=tpl.subject,
        body_html=tpl.body_html, body_text=tpl.body_text,
        variables=tpl.variables, is_builtin=tpl.is_builtin,
    )


@router.put("/{slug}", response_model=EmailTemplateOut)
async def update_email_template(
    slug: str,
    body: EmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.slug == slug))
    tpl = result.scalar_one_or_none()
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    if body.subject is not None:
        tpl.subject = body.subject
    if body.body_html is not None:
        tpl.body_html = body.body_html
    if body.body_text is not None:
        tpl.body_text = body.body_text

    await db.commit()
    await db.refresh(tpl)
    return EmailTemplateOut(
        id=str(tpl.id), slug=tpl.slug, name=tpl.name, subject=tpl.subject,
        body_html=tpl.body_html, body_text=tpl.body_text,
        variables=tpl.variables, is_builtin=tpl.is_builtin,
    )


@router.post("/{slug}/preview", response_model=EmailTemplatePreviewResponse)
async def preview_email_template(
    slug: str,
    body: EmailTemplatePreviewRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.slug == slug))
    tpl = result.scalar_one_or_none()
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    sample_vars = {k: v.get("sample", f"[{k}]") for k, v in tpl.variables.items()}
    if body.variables:
        sample_vars.update(body.variables)

    return EmailTemplatePreviewResponse(
        subject=_render(tpl.subject, sample_vars),
        body_html=_render(tpl.body_html, sample_vars),
    )
