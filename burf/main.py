import os, uuid, json
from typing import AsyncIterator
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from sse_starlette.sse import EventSourceResponse
import anthropic

load_dotenv()

app = FastAPI(title="Burf AI Assistant")
app.mount("/static", StaticFiles(directory="static"), name="static")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# In-memory storage: { conversation_id: { title, messages: [...] } }
conversations: dict = {}

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


class ConversationCreate(BaseModel):
    title: str = "New Chat"


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/api/conversations")
async def list_conversations():
    return [
        {"id": cid, "title": data["title"], "message_count": len(data["messages"])}
        for cid, data in reversed(list(conversations.items()))
    ]


@app.post("/api/conversations")
async def create_conversation(body: ConversationCreate):
    cid = str(uuid.uuid4())
    conversations[cid] = {"title": body.title, "messages": []}
    return {"id": cid, "title": body.title}


@app.get("/api/conversations/{cid}")
async def get_conversation(cid: str):
    if cid not in conversations:
        raise HTTPException(404, "Conversation not found")
    return {"id": cid, **conversations[cid]}


@app.delete("/api/conversations/{cid}")
async def delete_conversation(cid: str):
    if cid not in conversations:
        raise HTTPException(404, "Conversation not found")
    del conversations[cid]
    return {"ok": True}


@app.post("/api/chat/stream")
async def chat_stream(body: MessageRequest):
    # Create conversation if needed
    cid = body.conversation_id
    if not cid or cid not in conversations:
        cid = str(uuid.uuid4())
        conversations[cid] = {"title": body.message[:40], "messages": []}

    convo = conversations[cid]
    convo["messages"].append({"role": "user", "content": body.message})

    # Update title from first message
    if len(convo["messages"]) == 1:
        convo["title"] = body.message[:50]

    async def generate() -> AsyncIterator[dict]:
        full_response = ""
        try:
            yield {"event": "start", "data": json.dumps({"conversation_id": cid})}

            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=convo["messages"],
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    yield {"event": "token", "data": json.dumps({"token": text})}

            convo["messages"].append({"role": "assistant", "content": full_response})
            yield {"event": "done", "data": json.dumps({"conversation_id": cid, "title": convo["title"]})}

        except Exception as e:
            yield {"event": "error", "data": json.dumps({"error": str(e)})}

    return EventSourceResponse(generate())
