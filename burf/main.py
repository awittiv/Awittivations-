import os, uuid, json, sqlite3
from contextlib import contextmanager
from typing import AsyncIterator
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from sse_starlette.sse import EventSourceResponse
import anthropic

load_dotenv()

# ── Database ──────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(__file__), "burf.db")

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role            TEXT NOT NULL,
                content         TEXT NOT NULL,
                created_at      TEXT DEFAULT (datetime('now'))
            );
        """)

init_db()

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Burf AI Assistant")
app.mount("/static", StaticFiles(directory="static"), name="static")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are Burf, a sharp and capable personal AI assistant built for Jack Wittiv (Awittivations LLC). You are direct, intelligent, and action-oriented.

You help with:
- Business strategy and planning (BANKIT, AuraX, CDFI, Awittivations)
- Code and software engineering (Python, FastAPI, React, Solidity, Supabase)
- Financial analysis and grant applications
- Research and writing

Be concise but thorough. Use markdown formatting — headers, bullet points, code blocks where relevant. When you don't know something, say so clearly."""


class MessageRequest(BaseModel):
    conversation_id: str | None = None
    message: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/api/conversations")
def list_conversations():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.id, c.title, COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id
            ORDER BY c.updated_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/conversations/{cid}")
def get_conversation(cid: str):
    with get_db() as conn:
        conv = conn.execute("SELECT id, title FROM conversations WHERE id=?", (cid,)).fetchone()
        if not conv:
            raise HTTPException(404, "Conversation not found")
        msgs = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY created_at",
            (cid,)
        ).fetchall()
    return {"id": conv["id"], "title": conv["title"], "messages": [dict(m) for m in msgs]}


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: str):
    with get_db() as conn:
        if not conn.execute("SELECT 1 FROM conversations WHERE id=?", (cid,)).fetchone():
            raise HTTPException(404, "Conversation not found")
        conn.execute("DELETE FROM conversations WHERE id=?", (cid,))
    return {"ok": True}


@app.post("/api/chat/stream")
async def chat_stream(body: MessageRequest):
    cid = body.conversation_id

    # Load or create conversation, append user message
    with get_db() as conn:
        if cid:
            exists = conn.execute("SELECT 1 FROM conversations WHERE id=?", (cid,)).fetchone()
            if not exists:
                cid = None

        if not cid:
            cid = str(uuid.uuid4())
            title = body.message[:60]
            conn.execute("INSERT INTO conversations (id, title) VALUES (?,?)", (cid, title))
        else:
            # Update title from first user message if conversation is new
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id=?", (cid,)
            ).fetchone()[0]
            if count == 0:
                conn.execute(
                    "UPDATE conversations SET title=?, updated_at=datetime('now') WHERE id=?",
                    (body.message[:60], cid)
                )

        conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (?,?,?)",
            (cid, "user", body.message)
        )

        # Fetch full history for Claude
        history = conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY created_at",
            (cid,)
        ).fetchall()
        title = conn.execute("SELECT title FROM conversations WHERE id=?", (cid,)).fetchone()["title"]

    messages_for_claude = [{"role": r["role"], "content": r["content"]} for r in history]

    async def generate() -> AsyncIterator[dict]:
        full_response = ""
        try:
            yield {"event": "start", "data": json.dumps({"conversation_id": cid})}

            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages_for_claude,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield {"event": "token", "data": json.dumps({"token": text})}

            # Persist assistant reply
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content) VALUES (?,?,?)",
                    (cid, "assistant", full_response)
                )
                conn.execute(
                    "UPDATE conversations SET updated_at=datetime('now') WHERE id=?", (cid,)
                )

            yield {"event": "done", "data": json.dumps({"conversation_id": cid, "title": title})}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(generate())
