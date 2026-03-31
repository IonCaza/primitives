"""Auto-generate knowledge graph data from SQLAlchemy metadata.

Supports three generation modes:
- schema_only:         entity names, columns, types, relationships (no DB queries)
- entities_only:       entity names + row counts (DB queries, no column details)
- schema_and_entities: full schema details + row counts
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

INTERNAL_TABLES = frozenset({
    "alembic_version",
    "ai_settings",
    "llm_providers",
    "agents",
    "agent_tool_assignments",
    "agent_knowledge_graph_assignments",
    "knowledge_graphs",
    "chat_sessions",
    "chat_messages",
})

M2M_TABLES = frozenset({
    "project_contributors",
    "commit_branches",
})


def _col_type_label(col) -> str:
    try:
        return str(col.type)
    except Exception:
        return "unknown"


def _build_graph_structure(
    excluded: set[str],
    include_columns: bool,
    row_counts: dict[str, int] | None = None,
) -> dict:
    """Build {nodes, edges} from SQLAlchemy metadata."""
    tables = Base.metadata.sorted_tables
    nodes: list[dict] = []
    edges: list[dict] = []
    included_tables: set[str] = set()

    for table in tables:
        tname = table.name
        if tname in INTERNAL_TABLES or tname in excluded or tname in M2M_TABLES:
            continue
        included_tables.add(tname)

        node: dict = {"id": tname, "label": tname.replace("_", " ").title()}
        if table.comment:
            node["description"] = table.comment
        if include_columns:
            cols = []
            for col in table.columns:
                info: dict = {"name": col.name, "type": _col_type_label(col)}
                if col.primary_key:
                    info["pk"] = True
                if col.unique:
                    info["unique"] = True
                if col.nullable is False and not col.primary_key:
                    info["required"] = True
                if col.comment:
                    info["comment"] = col.comment
                cols.append(info)
            node["columns"] = cols
        if row_counts and tname in row_counts:
            node["row_count"] = row_counts[tname]
        nodes.append(node)

    for table in tables:
        tname = table.name
        if tname in INTERNAL_TABLES or tname in excluded:
            continue

        if tname in M2M_TABLES:
            fk_list = list(table.foreign_keys)
            if len(fk_list) == 2:
                t1 = fk_list[0].column.table.name
                t2 = fk_list[1].column.table.name
                if t1 in included_tables and t2 in included_tables:
                    edges.append({
                        "id": f"m2m_{tname}",
                        "source": t1,
                        "target": t2,
                        "label": f"M2M via {tname}",
                        "type": "m2m",
                    })
            continue

        if tname not in included_tables:
            continue
        for fk in table.foreign_keys:
            target_table = fk.column.table.name
            if target_table in included_tables:
                edges.append({
                    "id": f"fk_{tname}_{fk.parent.name}",
                    "source": tname,
                    "target": target_table,
                    "label": fk.parent.name,
                    "type": "fk",
                })

    return {"nodes": nodes, "edges": edges}


async def _get_row_counts(db: AsyncSession, table_names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tname in table_names:
        try:
            result = await db.execute(text(f'SELECT COUNT(*) FROM "{tname}"'))
            counts[tname] = result.scalar() or 0
        except Exception:
            counts[tname] = -1
    return counts


async def generate_graph_data(
    db: AsyncSession,
    mode: str,
    excluded_entities: list[str] | None = None,
) -> dict:
    excluded = set(excluded_entities or [])
    include_columns = mode in ("schema_only", "schema_and_entities")
    include_counts = mode in ("entities_only", "schema_and_entities")

    row_counts = None
    if include_counts:
        domain_tables = [
            t.name for t in Base.metadata.sorted_tables
            if t.name not in INTERNAL_TABLES and t.name not in excluded and t.name not in M2M_TABLES
        ]
        row_counts = await _get_row_counts(db, domain_tables)

    return _build_graph_structure(excluded, include_columns, row_counts)


def generate_content(graph_data: dict, mode: str) -> str:
    """Convert structured graph data into markdown text for prompt injection."""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    if not nodes:
        return ""

    outgoing: dict[str, list[dict]] = {}
    for e in edges:
        outgoing.setdefault(e["source"], []).append(e)

    include_columns = mode in ("schema_only", "schema_and_entities")
    lines = ["## Data Model\n"]

    for node in nodes:
        nid = node["id"]
        header = f"### {node['label']} (`{nid}`)"
        if "row_count" in node:
            header += f"  [{node['row_count']} rows]"
        lines.append(header)

        if node.get("description"):
            lines.append(node["description"])

        if include_columns and "columns" in node:
            col_parts = []
            for c in node["columns"]:
                desc = c["name"]
                desc += f" ({c['type']}"
                flags = []
                if c.get("pk"):
                    flags.append("PK")
                if c.get("unique"):
                    flags.append("unique")
                if c.get("required"):
                    flags.append("required")
                if flags:
                    desc += ", " + ", ".join(flags)
                desc += ")"
                if c.get("comment"):
                    desc += f" — {c['comment']}"
                col_parts.append(desc)
            lines.append("Columns: " + ", ".join(col_parts))

        rels = outgoing.get(nid, [])
        if rels:
            rel_parts = []
            for r in rels:
                if r["type"] == "m2m":
                    rel_parts.append(f"↔ {r['target']} ({r['label']})")
                else:
                    rel_parts.append(f"→ {r['target']} (via {r['label']})")
            lines.append("Relationships: " + ", ".join(rel_parts))

        lines.append("")

    return "\n".join(lines)
