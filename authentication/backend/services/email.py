import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
from jinja2 import BaseLoader, Environment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.smtp_settings import SmtpSettings, SINGLETON_ID
from app.db.models.email_template import EmailTemplate
from app.services.encryption import _get_fernet

logger = logging.getLogger(__name__)

_jinja_env = Environment(loader=BaseLoader(), autoescape=True)


def _decrypt_password(encrypted: str) -> str:
    if not encrypted:
        return ""
    return _get_fernet().decrypt(encrypted.encode()).decode()


async def _get_smtp_settings(db: AsyncSession) -> SmtpSettings | None:
    result = await db.execute(select(SmtpSettings).where(SmtpSettings.id == SINGLETON_ID))
    return result.scalar_one_or_none()


def _render(template_str: str, variables: dict) -> str:
    return _jinja_env.from_string(template_str).render(**variables)


async def render_template(slug: str, variables: dict, db: AsyncSession) -> tuple[str, str, str]:
    """Load an EmailTemplate by slug and render subject, html, text with variables."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.slug == slug))
    tpl = result.scalar_one_or_none()
    if tpl is None:
        raise ValueError(f"Email template '{slug}' not found")
    subject = _render(tpl.subject, variables)
    html = _render(tpl.body_html, variables)
    text = _render(tpl.body_text, variables) if tpl.body_text else ""
    return subject, html, text


async def send_email(
    to: str,
    subject: str,
    html_body: str,
    text_body: str,
    db: AsyncSession,
) -> None:
    smtp = await _get_smtp_settings(db)
    if smtp is None or not smtp.enabled or not smtp.host:
        raise RuntimeError("SMTP is not configured or not enabled")

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{smtp.from_name} <{smtp.from_email}>" if smtp.from_name else smtp.from_email
    msg["To"] = to
    msg["Subject"] = subject
    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    password = _decrypt_password(smtp.password_encrypted)

    await aiosmtplib.send(
        msg,
        hostname=smtp.host,
        port=smtp.port,
        username=smtp.username or None,
        password=password or None,
        start_tls=smtp.use_tls,
    )
    logger.info("Email sent to %s: %s", to, subject)


async def send_templated_email(
    to: str,
    template_slug: str,
    variables: dict,
    db: AsyncSession,
) -> None:
    subject, html, text = await render_template(template_slug, variables, db)
    await send_email(to, subject, html, text, db)
