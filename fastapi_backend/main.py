import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from config import PORT, CORS_ORIGIN
from routes import ai
from auth import get_current_user
from middleware import verify_kong_header
from database import get_db, engine

logger = logging.getLogger("uvicorn.error")

REQUIRED_INTENTS = {"code_generation", "general_chat", "summarization"}

MIGRATION_SQL_HINT = """
================================================================================
  ACTION REQUIRED — intent_routing table is missing or empty.
  
  Run the following command to apply the migration on the existing container:

  docker exec -it platform-db psql -U platform_admin -d platform_permissions -c "
  ALTER TABLE permission_audit_logs ADD COLUMN IF NOT EXISTS intent VARCHAR(255);

  CREATE TABLE IF NOT EXISTS intent_routing (
      intent      VARCHAR(255) PRIMARY KEY,
      service_id  VARCHAR(255) NOT NULL REFERENCES ai_services(service_id),
      description TEXT,
      created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
  );

  INSERT INTO intent_routing (intent, service_id, description) VALUES
    ('code_generation', 'ollama_deep_seek_coder', 'Routes code-related prompts to DeepSeek Coder'),
    ('general_chat',    'ollama_llama3.2',        'Routes general conversation to Llama 3.2'),
    ('summarization',   'ollama_llama3.2',        'Routes summarization tasks to Llama 3.2')
  ON CONFLICT DO NOTHING;
  "

  Then restart the fastapi_backend container:
    docker restart fastapi_backend
================================================================================
"""


async def check_intent_routing_table():
    """
    Non-destructive startup check: verifies intent_routing table exists and
    contains the required seed rows.  Logs a clear warning with the migration
    SQL if either condition is not met.  Never auto-creates tables.
    """
    async with engine.connect() as conn:
        # 1. Check table exists
        table_check = await conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_schema = 'public' AND table_name = 'intent_routing'"
                ")"
            )
        )
        table_exists = table_check.scalar()

        if not table_exists:
            logger.error(
                "STARTUP CHECK FAILED: 'intent_routing' table does not exist."
                + MIGRATION_SQL_HINT
            )
            return

        # 2. Check seed rows
        rows = await conn.execute(
            text("SELECT intent FROM intent_routing")
        )
        existing_intents = {row[0] for row in rows}
        missing = REQUIRED_INTENTS - existing_intents

        if missing:
            logger.error(
                f"STARTUP CHECK FAILED: 'intent_routing' is missing rows for: {missing}"
                + MIGRATION_SQL_HINT
            )
            return

        logger.info(
            "STARTUP CHECK OK: intent_routing table is healthy "
            f"({len(existing_intents)} intents registered)."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await check_intent_routing_table()
    yield


app = FastAPI(
    title="Kong AI Proxy Platform (FastAPI)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"])
async def root():
    return {"message": "FastAPI AI Platform Backend is running. Access via /api/"}


@app.get("/api/", tags=["Health"])
async def api_root():
    return {"message": "hello world from Python (FastAPI)!"}


@app.get("/api/documents", tags=["Data"], dependencies=[Depends(verify_kong_header)])
async def get_documents(user: dict = Depends(get_current_user)):
    email = user.get("email", "unknown")
    return {
        "message": "Documents",
        "client": email,
        "data": [
            {"id": 1, "name": f"{email} user Document 1"},
            {"id": 2, "name": f"{email} user Document 2"},
            {"id": 3, "name": f"{email} user Document 3"},
        ]
    }


@app.get("/api/admin", tags=["Data"], dependencies=[Depends(verify_kong_header)])
async def get_admin(user: dict = Depends(get_current_user)):
    email = user.get("email", "unknown")
    return {
        "message": "admin documents",
        "client": email,
        "data": [
            {"id": 1, "name": f"{email} admin Document 1"},
            {"id": 2, "name": f"{email} admin Document 2"},
            {"id": 3, "name": f"{email} admin Document 3"},
        ]
    }


app.include_router(ai.router, prefix="/api")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=True)
