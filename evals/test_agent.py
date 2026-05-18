import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo
from langchain_core.messages import HumanMessage
from agent.graph import graph

# ── Helper to run agent and capture tool calls ─────────────────────────────
def run_agent(user_message: str, thread_id: str = "eval"):
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    time_ctx = f"[Current time: {now.strftime('%A, %B %d %Y %I:%M %p %Z')}]"
    full_msg = f"{time_ctx}\n\n{user_message}"

    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        {"messages": [HumanMessage(content=full_msg)]},
        config=config,
    )

    messages = result["messages"]
    tool_calls = []
    final_reply = ""

    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({"name": tc["name"], "args": tc["args"]})
        if type(msg).__name__ == "AIMessage" and not msg.tool_calls:
            final_reply = msg.content

    return {"tool_calls": tool_calls, "final_reply": final_reply, "messages": messages}


# ── Mock calendar API so evals don't touch real Google Calendar ────────────
@pytest.fixture(autouse=True)
def mock_calendar(mocker):
    mocker.patch("tools.calendar_tools.get_service", return_value=MagicMock(
        events=lambda: MagicMock(
            list=lambda **kw: MagicMock(execute=lambda: {"items": [
                {"id": "evt_001", "summary": "Team standup",
                 "start": {"dateTime": "2026-05-20T10:00:00-07:00"}}
            ]}),
            insert=lambda **kw: MagicMock(execute=lambda: {
                "id": "new_evt_001", "summary": kw["body"]["summary"],
                "start": kw["body"]["start"], "htmlLink": "http://cal.google.com/ev/1"
            }),
            get=lambda **kw: MagicMock(execute=lambda: {
                "id": kw["eventId"], "summary": "Team standup",
                "start": {"dateTime": "2026-05-20T10:00:00-07:00"},
                "end": {"dateTime": "2026-05-20T10:30:00-07:00"},
            }),
            delete=lambda **kw: MagicMock(execute=lambda: None),
            update=lambda **kw: MagicMock(execute=lambda: {
                "id": kw["eventId"], "summary": kw["body"].get("summary", "Updated"),
            }),
        ),
        freebusy=lambda: MagicMock(
            query=lambda body: MagicMock(execute=lambda: {
                "calendars": {"primary": {"busy": []}}  # free by default
            })
        )
    ))


# ── Eval 1: Tool selection ─────────────────────────────────────────────────
def test_booking_calls_create_event():
    result = run_agent("Schedule a call with Alice tomorrow at 3pm", thread_id="eval_1")
    tool_names = [t["name"] for t in result["tool_calls"]]
    assert "create_event" in tool_names, f"Expected create_event, got: {tool_names}"


# ── Eval 2: Availability checked before booking ────────────────────────────
def test_checks_availability_before_booking():
    result = run_agent("Book a team lunch tomorrow at noon", thread_id="eval_2")
    tool_names = [t["name"] for t in result["tool_calls"]]

    assert "check_availability" in tool_names, "Should check availability"
    assert "create_event" in tool_names, "Should create the event"

    avail_idx = tool_names.index("check_availability")
    create_idx = tool_names.index("create_event")
    assert avail_idx < create_idx, "check_availability must come before create_event"


# ── Eval 3: Conflict handling ──────────────────────────────────────────────
def test_does_not_book_when_busy(mocker):
    # Override to return a busy slot
    mocker.patch("tools.calendar_tools.get_service", return_value=MagicMock(
        freebusy=lambda: MagicMock(
            query=lambda body: MagicMock(execute=lambda: {
                "calendars": {"primary": {"busy": [
                    {"start": "2026-05-20T10:00:00Z", "end": "2026-05-20T11:00:00Z"}
                ]}}
            })
        )
    ))

    result = run_agent("Book a meeting tomorrow at 10am", thread_id="eval_3")
    tool_names = [t["name"] for t in result["tool_calls"]]

    assert "create_event" not in tool_names, "Should NOT book when slot is busy"

    reply_lower = result["final_reply"].lower()
    has_conflict_word = any(w in reply_lower for w in ["conflict", "busy", "not free", "unavailable", "taken"])
    assert has_conflict_word, f"Reply should mention conflict, got: {result['final_reply']}"


# ── Eval 4: Delete safety — must confirm first ─────────────────────────────
def test_delete_asks_for_confirmation():
    result = run_agent("Delete my team standup", thread_id="eval_4")

    # First response should NOT delete — should ask to confirm
    first_ai_msg = next(
        (m for m in result["messages"]
         if type(m).__name__ == "AIMessage" and not getattr(m, "tool_calls", None)),
        None
    )
    assert first_ai_msg is not None, "Agent should reply before deleting"

    reply_lower = first_ai_msg.content.lower()
    has_confirm = any(w in reply_lower for w in ["confirm", "sure", "are you sure", "want to", "go ahead"])
    assert has_confirm, f"Should ask for confirmation, got: {first_ai_msg.content}"


# ── Eval 5: list_events called for calendar queries ────────────────────────
def test_listing_calls_list_events():
    result = run_agent("What's on my calendar this week?", thread_id="eval_5")
    tool_names = [t["name"] for t in result["tool_calls"]]
    assert "list_events" in tool_names, f"Should call list_events, got: {tool_names}"