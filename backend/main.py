import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agent import build_agent
from .routers import chat, charts, conversations, database_explorer, documents, purchase_orders

# Show warnings and errors from the agent/chat modules in the console
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = build_agent()
    yield


app = FastAPI(title="Aria Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(charts.router)
app.include_router(purchase_orders.router)
app.include_router(database_explorer.router)
app.include_router(documents.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

