import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_core.messages import HumanMessage
from agent.graph import graph

app = FastAPI()

# Allow the React dev server to talk to FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite's default port
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_TIMEZONE = "America/Los_Angeles"

class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


def make_sse(event: str, data: dict) -> str:
    """Format a server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_agent(message: str, thread_id: str) -> AsyncGenerator[str, None]:
    now = datetime.now(ZoneInfo(USER_TIMEZONE))
    time_ctx = f"[Current time: {now.strftime('%A, %B %d %Y %I:%M %p %Z')}]"
    full_message = f"{time_ctx}\n\n{message}"

    config = {"configurable": {"thread_id": thread_id}}

    try:
        # stream_mode="updates" emits one dict per node execution
        for event in graph.stream(
            {"messages": [HumanMessage(content=full_message)]},
            config=config,
            stream_mode="updates",
        ):
            for node_name, node_output in event.items():
                messages = node_output.get("messages", [])

                for msg in messages:
                    msg_type = type(msg).__name__

                    if msg_type == "AIMessage":
                        if msg.tool_calls:
                            # Agent is calling a tool — tell the UI
                            for tc in msg.tool_calls:
                                yield make_sse("tool_call", {
                                    "tool": tc["name"],
                                    "args": tc["args"],
                                })
                        else:
                            # Final answer — stream it
                            yield make_sse("message", {
                                "role": "assistant",
                                "content": msg.content,
                            })

                    elif msg_type == "ToolMessage":
                        # Tool result — send back so UI can show it
                        yield make_sse("tool_result", {
                            "tool": msg.name,
                            "content": msg.content,
                        })

            # Small pause to avoid overwhelming the client
            await asyncio.sleep(0.01)

        yield make_sse("done", {})

    except Exception as e:
        yield make_sse("error", {"message": str(e)})


@app.post("/chat")
async def chat(req: ChatRequest):
    return StreamingResponse(
        stream_agent(req.message, req.thread_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables nginx buffering if deployed
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}