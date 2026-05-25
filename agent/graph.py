import os
from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver

from tools.calendar_tools import (
    list_events,
    create_event,
    update_event,
    delete_event,
    check_availability,
    find_free_slots,
    create_recurring_event,
)

load_dotenv()

# ── Owner identity ─────────────────────────────────────────────────────────
# Set CALENDAR_OWNER_EMAIL in .env and AWS Secrets Manager
CALENDAR_OWNER_EMAIL = os.getenv("CALENDAR_OWNER_EMAIL", "").lower().strip()

def is_owner(email: str) -> bool:
    """Check if the user is the calendar owner."""
    if not CALENDAR_OWNER_EMAIL:
        return True  # local dev fallback — no restriction
    return email.lower().strip() == CALENDAR_OWNER_EMAIL

# ── Tool sets ──────────────────────────────────────────────────────────────
OWNER_TOOLS = [
    list_events,
    create_event,
    update_event,
    delete_event,
    check_availability,
    find_free_slots,
    create_recurring_event,
]

GUEST_TOOLS = [
    check_availability,   # free/busy only — no event details
    find_free_slots,      # suggest available times
    create_event,         # book a meeting
]

# ── System prompts ─────────────────────────────────────────────────────────
OWNER_SYSTEM_PROMPT = """You are a personal calendar assistant for the calendar owner.
You have full access to manage their Google Calendar.

Guidelines:
- Always check availability with check_availability before creating an event.
- If check_availability finds a conflict, use find_free_slots to suggest alternatives.
- When the user says 'every X', 'recurring', 'daily', 'weekly', or 'monthly',
  always use create_recurring_event instead of create_event.
- Before deleting or updating an event, confirm the details with the user.
- When creating events, if no duration is specified assume 1 hour.
- Use natural, friendly language. Be concise.
- Today's date and time will be provided in each message context.
"""

GUEST_SYSTEM_PROMPT = """You are a scheduling assistant helping visitors book meetings
with the calendar owner. You help people find a good time and book appointments.

What you CAN do:
- Check when the owner is available (free/busy)
- Find available time slots
- Book a meeting on their calendar on the visitor's behalf

What you CANNOT do:
- View, list, or describe existing calendar events (privacy)
- Delete or modify existing events
- Access any personal calendar information

When booking a meeting always:
1. Ask for the visitor's name and email address (to add as attendee)
2. Ask for the meeting purpose/title
3. Check availability for the requested time before booking
4. Confirm the details before creating

Be friendly and helpful. If asked about existing events or calendar details,
politely explain you can only help with checking availability and booking.
Today's date and time will be provided in each message context.
"""

# ── LLM ────────────────────────────────────────────────────────────────────
llm = ChatAnthropic(model="claude-sonnet-4-5", temperature=0)
owner_llm = llm.bind_tools(OWNER_TOOLS)
guest_llm  = llm.bind_tools(GUEST_TOOLS)

# ── Graph builder ──────────────────────────────────────────────────────────
def build_graph(owner: bool = True):
    """Build a graph with the appropriate tools for owner or guest."""
    tools      = OWNER_TOOLS if owner else GUEST_TOOLS
    bound_llm  = owner_llm  if owner else guest_llm
    prompt     = OWNER_SYSTEM_PROMPT if owner else GUEST_SYSTEM_PROMPT
    memory     = MemorySaver()

    def call_llm(state: MessagesState):
        messages = [SystemMessage(content=prompt)] + state["messages"]
        response = bound_llm.invoke(messages)

        if response.tool_calls:
            for tc in response.tool_calls:
                print(f"  [llm] → {tc['name']}({tc['args']})")
        else:
            print(f"  [llm] → final answer")

        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("llm",   call_llm)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", tools_condition)
    builder.add_edge("tools", "llm")

    return builder.compile(checkpointer=memory)

# ── Two graph instances ────────────────────────────────────────────────────
owner_graph = build_graph(owner=True)
guest_graph = build_graph(owner=False)

# Backward-compatible alias — used by evals and chat.py
graph = owner_graph

def get_graph(email: str):
    """Return the correct graph based on user identity."""
    return owner_graph if is_owner(email) else guest_graph