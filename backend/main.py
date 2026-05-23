import json
import asyncio
import os
import base64
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import AsyncGenerator
from collections import defaultdict
from time import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from agent.graph import graph

# ── Load AWS Secrets Manager secrets (production) ─────────────────────────
def _load_aws_secrets():
    secret_name = os.getenv("AWS_SECRET_NAME")
    if not secret_name:
        from dotenv import load_dotenv
        load_dotenv()
        return
    try:
        import boto3
        client = boto3.client(
            "secretsmanager",
            region_name=os.getenv("AWS_REGION", "us-east-1")
        )
        secret = client.get_secret_value(SecretId=secret_name)
        for k, v in json.loads(secret["SecretString"]).items():
            os.environ.setdefault(k, v)
        print(f"[startup] Loaded secrets from {secret_name}")
    except Exception as e:
        print(f"[startup] Warning: could not load AWS secrets: {e}")

_load_aws_secrets()

# ── App ────────────────────────────────────────────────────────────────────
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_TIMEZONE = os.getenv("USER_TIMEZONE", "America/Los_Angeles")


# ── Cognito user extraction ────────────────────────────────────────────────
def get_current_user(request: Request) -> dict:
    """
    Extract user info from the ALB-injected Cognito OIDC header.
    Falls back to a local dev user when not behind the ALB.
    """
    oidc_data = request.headers.get("x-amzn-oidc-data")
    if oidc_data:
        try:
            payload_b64 = oidc_data.split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.b64decode(payload_b64))
            return {
                "user_id": payload.get("sub"),
                "email":   payload.get("email"),
                "name":    payload.get("name", ""),
            }
        except Exception:
            pass
    return {
        "user_id": "local-dev-user",
        "email":   "dev@localhost",
        "name":    "Dev User",
    }


# ── Rate limiting ──────────────────────────────────────────────────────────
_request_times: dict[str, list[float]] = defaultdict(list)

def check_rate_limit(
    thread_id: str,
    max_requests: int = 20,
    window_seconds: int = 60,
) -> bool:
    now = time()
    _request_times[thread_id] = [
        t for t in _request_times[thread_id]
        if now - t < window_seconds
    ]
    if len(_request_times[thread_id]) >= max_requests:
        return False
    _request_times[thread_id].append(now)
    return True


# ── Orphaned tool call repair ──────────────────────────────────────────────
def fix_orphaned_tool_calls(thread_config: dict) -> int:
    """
    Add synthetic ToolMessages for any AIMessages with tool_calls that
    have no corresponding ToolMessage after them. Prevents Claude's
    400 invalid_request_error on corrupted conversation threads.
    """
    try:
        state = graph.get_state(thread_config)
        if not state or not state.values:
            return 0

        messages = state.values.get("messages", [])
        if not messages:
            return 0

        fixed = 0
        synthetic_results = []

        for i, msg in enumerate(messages):
            if not isinstance(msg, AIMessage) or not msg.tool_calls:
                continue
            next_msg = messages[i + 1] if i + 1 < len(messages) else None
            if isinstance(next_msg, ToolMessage):
                continue

            for tc in msg.tool_calls:
                synthetic_results.append(
                    ToolMessage(
                        content=(
                            "This tool call was interrupted before completing. "
                            "Please ignore the previous attempt and try again."
                        ),
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    )
                )
                fixed += 1

        if synthetic_results:
            graph.update_state(thread_config, {"messages": synthetic_results})
            print(f"  [repair] Fixed {fixed} orphaned tool call(s)")

        return fixed

    except Exception as e:
        print(f"  [repair] Warning: {e}")
        return 0


# ── SSE helper ────────────────────────────────────────────────────────────
def make_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Agent streaming ────────────────────────────────────────────────────────
async def stream_agent(
    message: str,
    thread_id: str,
    user: dict,
) -> AsyncGenerator[str, None]:

    now = datetime.now(ZoneInfo(USER_TIMEZONE))
    time_ctx  = f"[Current time: {now.strftime('%A, %B %d %Y %I:%M %p %Z')}]"
    user_ctx  = f"[User: {user['name']} ({user['email']})]"
    full_message = f"{time_ctx}\n{user_ctx}\n\n{message}"

    config = {"configurable": {"thread_id": thread_id}}

    # Repair orphaned tool calls before invoking
    fix_orphaned_tool_calls(config)

    try:
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
                            for tc in msg.tool_calls:
                                print(f"  [llm] → {tc['name']}({tc['args']})")
                                yield make_sse("tool_call", {
                                    "tool": tc["name"],
                                    "args": tc["args"],
                                })
                        else:
                            yield make_sse("message", {
                                "role":    "assistant",
                                "content": msg.content,
                            })

                    elif msg_type == "ToolMessage":
                        content = msg.content
                        if len(content) > 200:
                            content = content[:200] + "..."
                        print(f"  [tool] ← {msg.name}: {content}")
                        yield make_sse("tool_result", {
                            "tool":    msg.name,
                            "content": msg.content,
                        })

            await asyncio.sleep(0.01)

        yield make_sse("done", {})

    except Exception as e:
        error_msg = str(e)
        print(f"  [error] {error_msg}")
        if "tool_use" in error_msg and "tool_result" in error_msg:
            yield make_sse("error", {
                "message": (
                    "The conversation got into a bad state. "
                    "Please refresh the page to start a new session."
                )
            })
        else:
            yield make_sse("error", {"message": error_msg})


# ── Request model ──────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message:   str
    thread_id: str = "default"


# ── API endpoints ──────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    if not check_rate_limit(req.thread_id):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")

    user = get_current_user(request)
    scoped_thread_id = f"{user['user_id']}:{req.thread_id}"

    return StreamingResponse(
        stream_agent(req.message, scoped_thread_id, user),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


@app.get("/me")
async def me(request: Request):
    user = get_current_user(request)
    return {"email": user["email"], "name": user["name"]}


@app.get("/health")
async def health():
    return {"status": "ok"}


COGNITO_DOMAIN = os.getenv("COGNITO_DOMAIN", "")
COGNITO_CLIENT = os.getenv("COGNITO_CLIENT_ID", "")
APP_URL        = os.getenv("APP_URL", "/")


@app.get("/logout")
async def logout():
    from fastapi.responses import RedirectResponse
    if COGNITO_DOMAIN and COGNITO_CLIENT:
        return RedirectResponse(
            f"https://{COGNITO_DOMAIN}/logout"
            f"?client_id={COGNITO_CLIENT}"
            f"&logout_uri={APP_URL}"
        )
    return RedirectResponse("/")


# ── Serve built React app ──────────────────────────────────────────────────
FRONTEND_DIST = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "dist"
)

print(f"[startup] FRONTEND_DIST = {FRONTEND_DIST}")
print(f"[startup] dist exists   = {os.path.exists(FRONTEND_DIST)}")

if os.path.exists(os.path.join(FRONTEND_DIST, "assets")):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
        name="assets",
    )
    print("[startup] Mounted /assets static files")


@app.get("/")
async def serve_root():
    """Explicit root route — /{full_path:path} does NOT match /"""
    index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"status": "API running", "note": "Frontend not built"}


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """Catch-all for React Router — serves index.html for any non-API path"""
    # Don't intercept API routes
    api_prefixes = ("chat", "me", "logout", "health", "assets")
    if any(full_path.startswith(p) for p in api_prefixes):
        raise HTTPException(status_code=404)

    index = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    raise HTTPException(status_code=404, detail="Frontend not built")