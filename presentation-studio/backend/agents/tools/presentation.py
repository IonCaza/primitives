"""Agent tools for managing presentations and templates."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from langchain_core.tools import tool
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session as _session_factory
from app.db.models.presentation import Presentation, PresentationTemplate, PresentationVersion
from app.agents.tools.base import ToolDefinition
from app.agents.tools.registry import register_tool_category

logger = logging.getLogger(__name__)

CATEGORY = "presentation"

DEFINITIONS = [
    ToolDefinition(
        "save_presentation",
        "Save Presentation",
        "Save a presentation with React component code. If presentation_id is given, updates that existing presentation; otherwise creates a new one. Pins to the latest template version.",
        CATEGORY,
    ),
    ToolDefinition(
        "get_presentation",
        "Get Presentation",
        "Retrieve an existing presentation's component code and template version for viewing or editing.",
        CATEGORY,
    ),
    ToolDefinition(
        "update_presentation",
        "Update Presentation",
        "Update an existing presentation's component code. Re-pins to the latest template version and creates a version entry.",
        CATEGORY,
    ),
    ToolDefinition(
        "get_presentation_template",
        "Get Presentation Template",
        "Retrieve the current latest template HTML to understand the available hooks, utilities, and bridge API.",
        CATEGORY,
    ),
    ToolDefinition(
        "update_presentation_template",
        "Update Presentation Template",
        "Create a new immutable template version with updated HTML. Existing presentations are unaffected.",
        CATEGORY,
    ),
]


def _build_presentation_tools(db: AsyncSession) -> list:

    @tool
    async def save_presentation(
        project_name: str,
        title: str,
        component_code: str,
        prompt: str = "",
        description: str = "",
        presentation_id: str = "",
    ) -> str:
        """Save a presentation with React component code.

        If presentation_id is provided, updates that existing presentation.
        Otherwise creates a new one.

        Args:
            project_name: The project name or ID to save the presentation under.
            title: The presentation title.
            component_code: The React component code (App function and helpers).
            prompt: The original user prompt that generated this presentation.
            description: Optional description of the presentation.
            presentation_id: Optional ID of an existing presentation to update instead of creating new.

        Returns:
            The presentation ID.
        """
        from app.db.models import Project

        async with _session_factory() as session:
            latest = await session.execute(
                select(func.max(PresentationTemplate.version))
            )
            tv = latest.scalar() or 1

            if presentation_id:
                result = await session.execute(
                    select(Presentation).where(Presentation.id == presentation_id)
                )
                pres = result.scalar_one_or_none()
                if not pres:
                    return f"Error: Presentation '{presentation_id}' not found."
                pres.title = title
                pres.component_code = component_code
                pres.template_version = tv
                if description:
                    pres.description = description
                pres.updated_at = datetime.now(timezone.utc)

                max_ver = await session.execute(
                    select(func.max(PresentationVersion.version_number)).where(
                        PresentationVersion.presentation_id == pres.id
                    )
                )
                next_ver = (max_ver.scalar() or 0) + 1
                version = PresentationVersion(
                    presentation_id=pres.id,
                    version_number=next_ver,
                    component_code=component_code,
                    template_version=tv,
                    change_summary="Initial generation" if next_ver == 1 else f"Update v{next_ver}",
                )
                session.add(version)
                await session.commit()
                return f"Presentation saved successfully. ID: {pres.id} (template v{tv})"

            result = await session.execute(
                select(Project).where(Project.name.ilike(f"%{project_name}%")).limit(1)
            )
            project = result.scalar_one_or_none()
            if not project:
                return f"Error: Project '{project_name}' not found."

            pres = Presentation(
                project_id=project.id,
                title=title,
                description=description or None,
                component_code=component_code,
                template_version=tv,
                prompt=prompt,
                created_by_id=project.id,
                status="draft",
            )
            session.add(pres)
            await session.flush()

            version = PresentationVersion(
                presentation_id=pres.id,
                version_number=1,
                component_code=component_code,
                template_version=tv,
                change_summary="Initial creation",
            )
            session.add(version)
            await session.commit()

            return f"Presentation saved successfully. ID: {pres.id} (template v{tv})"

    @tool
    async def get_presentation(presentation_id: str) -> str:
        """Retrieve a presentation's component code and template version.

        Args:
            presentation_id: The UUID of the presentation to retrieve.

        Returns:
            The component code and metadata.
        """
        async with _session_factory() as session:
            result = await session.execute(
                select(Presentation).where(Presentation.id == presentation_id)
            )
            pres = result.scalar_one_or_none()
            if not pres:
                return f"Error: Presentation '{presentation_id}' not found."

            return (
                f"Title: {pres.title}\n"
                f"Template Version: {pres.template_version}\n"
                f"Status: {pres.status}\n"
                f"Prompt: {pres.prompt}\n\n"
                f"--- Component Code ---\n{pres.component_code}"
            )

    @tool
    async def update_presentation(
        presentation_id: str,
        component_code: str,
        change_summary: str = "",
    ) -> str:
        """Update an existing presentation's component code.

        Args:
            presentation_id: The UUID of the presentation to update.
            component_code: The new React component code.
            change_summary: Brief description of what changed.

        Returns:
            Confirmation message with version number.
        """
        async with _session_factory() as session:
            result = await session.execute(
                select(Presentation).where(Presentation.id == presentation_id)
            )
            pres = result.scalar_one_or_none()
            if not pres:
                return f"Error: Presentation '{presentation_id}' not found."

            latest = await session.execute(
                select(func.max(PresentationTemplate.version))
            )
            tv = latest.scalar() or pres.template_version

            pres.component_code = component_code
            pres.template_version = tv
            pres.updated_at = datetime.now(timezone.utc)

            max_ver = await session.execute(
                select(func.max(PresentationVersion.version_number)).where(
                    PresentationVersion.presentation_id == pres.id
                )
            )
            next_ver = (max_ver.scalar() or 0) + 1

            version = PresentationVersion(
                presentation_id=pres.id,
                version_number=next_ver,
                component_code=component_code,
                template_version=tv,
                change_summary=change_summary or f"Update v{next_ver}",
            )
            session.add(version)
            await session.commit()

            return f"Presentation updated to version {next_ver}. ID: {pres.id} (template v{tv})"

    @tool
    async def get_presentation_template() -> str:
        """Get the current latest presentation template HTML.

        Returns the full template with bridge library, hooks, and utility components
        so you can understand what's available in the canvas.

        Returns:
            The template HTML and version info.
        """
        async with _session_factory() as session:
            result = await session.execute(
                select(PresentationTemplate)
                .order_by(PresentationTemplate.version.desc())
                .limit(1)
            )
            tmpl = result.scalar_one_or_none()
            if not tmpl:
                return "Error: No presentation templates found."

            return (
                f"Template Version: {tmpl.version}\n"
                f"Description: {tmpl.description}\n\n"
                f"--- Template HTML ---\n{tmpl.template_html}"
            )

    @tool
    async def update_presentation_template(
        template_html: str,
        description: str,
    ) -> str:
        """Create a new immutable template version.

        Existing presentations are unaffected -- they remain pinned to their
        original template version. New presentations will use this version.

        IMPORTANT: The template must contain the marker /* __COMPONENT_CODE__ */
        where agent-generated code will be injected at render time.

        Args:
            template_html: The complete HTML template with /* __COMPONENT_CODE__ */ marker.
            description: What changed from the previous version.

        Returns:
            Confirmation with the new version number.
        """
        if "/* __COMPONENT_CODE__ */" not in template_html:
            return "Error: Template must contain the injection marker /* __COMPONENT_CODE__ */"

        async with _session_factory() as session:
            max_ver = await session.execute(
                select(func.max(PresentationTemplate.version))
            )
            next_version = (max_ver.scalar() or 0) + 1

            tmpl = PresentationTemplate(
                version=next_version,
                template_html=template_html,
                description=description,
            )
            session.add(tmpl)
            await session.commit()

            return f"Template version {next_version} created. Existing presentations are unaffected."

    return [
        save_presentation,
        get_presentation,
        update_presentation,
        get_presentation_template,
        update_presentation_template,
    ]


register_tool_category(CATEGORY, DEFINITIONS, _build_presentation_tools, session_safe=True)
