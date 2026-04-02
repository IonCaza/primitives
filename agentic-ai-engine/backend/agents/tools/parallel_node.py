"""ToolNode subclass that partitions tool calls by concurrency safety.

LangGraph's default ToolNode runs *all* pending tool calls via
``asyncio.gather``.  That works for read-only tools but can cause
non-deterministic ordering and race conditions when stateful tools
(create, update, delete) execute concurrently.

``ParallelToolNode`` inspects each call's name against the tool
registry and partitions them into batches:

* **Concurrent batch** -- all calls in the batch are concurrency-safe
  and run via ``asyncio.gather``.
* **Serial item** -- a single non-safe call that runs alone, preserving
  the model's intended ordering for side-effectful operations.

Batches execute in the order they appear in the model's tool-call list,
so the overall call sequence stays deterministic.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.prebuilt import ToolNode

from app.agents.tools.registry import is_tool_concurrency_safe

logger = logging.getLogger(__name__)


@dataclass
class _Batch:
    concurrent: bool
    calls: list[dict] = field(default_factory=list)


def _partition_tool_calls(tool_calls: list[dict]) -> list[_Batch]:
    """Split tool calls into alternating concurrent/serial batches.

    Adjacent concurrency-safe calls are grouped together.  Each non-safe
    call becomes its own single-item serial batch so it runs in isolation.
    """
    batches: list[_Batch] = []
    current_concurrent: list[dict] = []

    for tc in tool_calls:
        if is_tool_concurrency_safe(tc["name"]):
            current_concurrent.append(tc)
        else:
            if current_concurrent:
                batches.append(_Batch(concurrent=True, calls=current_concurrent))
                current_concurrent = []
            batches.append(_Batch(concurrent=False, calls=[tc]))

    if current_concurrent:
        batches.append(_Batch(concurrent=True, calls=current_concurrent))

    return batches


class ParallelToolNode(ToolNode):
    """ToolNode that runs concurrency-safe tools in parallel and
    serializes everything else.
    """

    async def _afunc(
        self,
        input: list | dict[str, Any],
        config: Any = None,
        **kwargs: Any,
    ) -> Any:
        tool_calls, output_type = self._parse_input(input, store=kwargs.get("store"))

        if not tool_calls:
            if output_type == "list":
                return []
            elif output_type == "dict":
                return {self.messages_key: []}
            return output_type(messages=[])

        batches = _partition_tool_calls(tool_calls)
        results: list[ToolMessage] = []

        n_concurrent = sum(len(b.calls) for b in batches if b.concurrent)
        n_serial = sum(len(b.calls) for b in batches if not b.concurrent)
        if n_concurrent or n_serial:
            logger.debug(
                "ParallelToolNode: %d concurrent, %d serial across %d batches",
                n_concurrent, n_serial, len(batches),
            )

        for batch in batches:
            if batch.concurrent and len(batch.calls) > 1:
                batch_results = await asyncio.gather(
                    *[self._arun_one(tc, config) for tc in batch.calls]
                )
                results.extend(batch_results)
            else:
                for tc in batch.calls:
                    results.append(await self._arun_one(tc, config))

        if output_type == "list":
            return results
        elif output_type == "dict":
            return {self.messages_key: results}
        return output_type(messages=results)
