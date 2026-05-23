import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage
from agent.graph import graph


def run_agent(user_message: str, thread_id: str = "eval"):
    now = datetime.now(timezone.utc)
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
        if type(msg).__name__ == "AIMessage" and not getattr(msg, "tool_calls", None):
            final_reply = msg.content

    return {"tool_calls": tool_calls, "final_reply": final_reply, "messages": messages}


@pytest.fixture(autouse=True)
def mock_calendar(mocker):
    """Default mock — calendar is free, one existing event."""
    mocker.patch("tools.calendar_tools.get_service", return_value=MagicMock(
        events=lambda: MagicMock(
            list=lambda **kw: MagicMock(execute=lambda: {"items": [
                {"id": "evt_001", "summary": "Team standup",
                 "start": {"dateTime": "2026-05-20T10:00:00-07:00"}}
            ]}),
            insert=lambda **kw: MagicMock(execute=lambda: {
                "id": "new_evt_001",
                "summary": kw["body"]["summary"],
                "start": kw["body"]["start"],
                "htmlLink": "http://cal.google.com/ev/1"
            }),
            get=lambda **kw: MagicMock(execute=lambda: {
                "id": kw["eventId"],
                "summary": "Team standup",
                "start": {"dateTime": "2026-05-20T10:00:00-07:00"},
                "end":   {"dateTime": "2026-05-20T10:30:00-07:00"},
            }),
            delete=lambda **kw: MagicMock(execute=lambda: None),
            update=lambda **kw: MagicMock(execute=lambda: {
                "id": kw["eventId"],
                "summary": kw["body"].get("summary", "Updated"),
            }),
        ),
        freebusy=lambda: MagicMock(
            query=lambda body: MagicMock(execute=lambda: {
                "calendars": {"primary": {"busy": []}}
            })
        )
    ))


def test_booking_calls_create_event():
    result = run_agent("Schedule a call with Alice tomorrow at 3pm", thread_id="eval_1")
    tool_names = [t["name"] for t in result["tool_calls"]]
    assert "create_event" in tool_names, f"Expected create_event, got: {tool_names}"


def test_checks_availability_before_booking():
    result = run_agent("Book a team lunch tomorrow at noon", thread_id="eval_2")
    tool_names = [t["name"] for t in result["tool_calls"]]

    assert "check_availability" in tool_names, "Should check availability"
    assert "create_event" in tool_names, "Should create the event"

    avail_idx = tool_names.index("check_availability")
    create_idx = tool_names.index("create_event")
    assert avail_idx < create_idx, "check_availability must come before create_event"


def test_does_not_book_when_busy(mocker):
    # Generate a busy slot dynamically for tomorrow — avoids hardcoded date mismatch
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    busy_start = tomorrow.replace(hour=9, minute=0, second=0).isoformat()
    busy_end   = tomorrow.replace(hour=18, minute=0, second=0).isoformat()

    mocker.patch("tools.calendar_tools.get_service", return_value=MagicMock(
        events=lambda: MagicMock(
            list=lambda **kw: MagicMock(execute=lambda: {"items": []}),
        ),
        freebusy=lambda: MagicMock(
            query=lambda body: MagicMock(execute=lambda: {
                "calendars": {"primary": {"busy": [
                    {"start": busy_start, "end": busy_end}
                ]}}
            })
        )
    ))

    result = run_agent("Book a meeting tomorrow at 10am", thread_id="eval_3")
    tool_names = [t["name"] for t in result["tool_calls"]]

    assert "create_event" not in tool_names, "Should NOT book when slot is busy"

    reply_lower = result["final_reply"].lower()
    has_conflict_word = any(w in reply_lower for w in [
        "conflict", "busy", "not free", "unavailable", "taken",
        "already", "booked", "occupied", "clash"
    ])
    assert has_conflict_word, f"Reply should mention conflict, got: {result['final_reply']}"


def test_delete_asks_for_confirmation():
    result = run_agent("Delete my team standup", thread_id="eval_4")

    # First AI message that has no tool calls = the agent's first response
    first_ai_msg = next(
        (m for m in result["messages"]
         if type(m).__name__ == "AIMessage" and not getattr(m, "tool_calls", None)),
        None
    )
    assert first_ai_msg is not None, "Agent should reply before deleting"

    reply_lower = first_ai_msg.content.lower()

    # Agent is asking a question = asking for confirmation
    is_question = "?" in first_ai_msg.content

    # Check for common confirmation phrases
    has_confirm_phrase = any(w in reply_lower for w in [
        "confirm", "sure", "are you sure", "want to",
        "would you", "would you like", "still like",
        "shall i", "should i", "like me to", "go ahead"
    ])

    assert is_question or has_confirm_phrase, \
        f"Should ask for confirmation, got: {first_ai_msg.content}"


def test_listing_calls_list_events():
    result = run_agent("What is on my calendar this week?", thread_id="eval_5")
    tool_names = [t["name"] for t in result["tool_calls"]]
    assert "list_events" in tool_names, f"Should call list_events, got: {tool_names}"