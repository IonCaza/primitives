"""Test scaffold main.py -- validates the agentic-ai-engine primitive can be integrated."""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.memory.pool import init_memory_pool, close_memory_pool
from app.api.chat import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_memory_pool()
    yield
    await close_memory_pool()


app = FastAPI(title="Test Scaffold", lifespan=lifespan)
app.include_router(chat_router, prefix="/api/v1")
