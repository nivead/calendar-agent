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

# ── Tools list ─────────────────────────────────────────────────────────────
TOOLS = [
    list_events,
    create_event,
    update_event,
    delete_event,
    check_availability,
    find_free_slots,
    create_recurring_event,
]

# ── LLM ────────────────────────────────────────────────────────────────────
llm = ChatAnthropic(model="claude-sonnet-4-5", temperature=0)
llm_with_tools = llm.bind_tools(TOOLS)

# ── System prompt ──────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a helpful calendar assistant. You help users manage
their Google Calendar by listing events, creating meetings, updating schedules,
and checking availability.

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

# ── LLM node ───────────────────────────────────────────────────────────────
def call_llm(state: MessagesState):
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)

    if response.tool_calls:
        for tc in response.tool_calls:
            print(f"  [llm] → {tc['name']}({tc['args']})")
    else:
        print(f"  [llm] → final answer")

    return {"messages": [response]}

# ── Graph ───────────────────────────────────────────────────────────────────
def build_graph():
    memory = MemorySaver()

    builder = StateGraph(MessagesState)
    builder.add_node("llm",   call_llm)
    builder.add_node("tools", ToolNode(TOOLS))

    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", tools_condition)
    builder.add_edge("tools", "llm")

    return builder.compile(checkpointer=memory)

graph = build_graph()