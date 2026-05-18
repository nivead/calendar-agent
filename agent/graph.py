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
)

load_dotenv()

# ── 1. Define your tools list ──────────────────────────────────────────────
# This is what the LLM can call. Order doesn't matter.
TOOLS = [
    list_events,
    create_event,
    update_event,
    delete_event,
    check_availability,
]

# ── 2. Set up the LLM with tools bound ────────────────────────────────────
# Binding tools tells the LLM what's available and what args each tool needs.
llm = ChatAnthropic(model="claude-sonnet-4-5", temperature=0)
llm_with_tools = llm.bind_tools(TOOLS)

# ── 3. System prompt ───────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a helpful calendar assistant. You help users manage 
their Google Calendar by listing events, creating meetings, updating schedules, 
and checking availability.

Guidelines:
- Always check availability with check_availability before creating an event.
- Before deleting or updating an event, confirm the details with the user.
- When creating events, if no duration is specified assume 1 hour.
- Use natural, friendly language. Be concise.
- Today's date and time will be provided in each message context.
- always greet users like "I am nivead's assistant, how can i help"
"""

# ── 4. Define the LLM node ────────────────────────────────────────────────
# This is the "think" step — the LLM reads messages and decides what to do.
def call_llm(state: MessagesState):
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)
    # We return a dict that updates the graph state.
    # LangGraph merges this into the existing messages list.
    if response.tool_calls:
        for tc in response.tool_calls:
            print(f"  [LLM] → calling tool: {tc['name']}({tc['args']})")
    else:
        print(f"  [LLM] → final answer (no tool call)")

    return {"messages": [response]}

# ── 5. Build the graph ────────────────────────────────────────────────────
def build_graph():
    # MemorySaver stores conversation history in memory (per thread_id).
    # Each conversation thread is isolated — perfect for a chat UI later.
    memory = MemorySaver()

    builder = StateGraph(MessagesState)

    # Add our two nodes
    builder.add_node("llm", call_llm)
    builder.add_node("tools", ToolNode(TOOLS))

    # Always start at the LLM node
    builder.add_edge(START, "llm")

    # After the LLM runs: if it made a tool call → go to tools, else → END
    # tools_condition is a prebuilt helper that checks for tool_calls in the response
    builder.add_conditional_edges("llm", tools_condition)

    # After tools run: always go back to the LLM
    builder.add_edge("tools", "llm")

    # Compile with memory checkpointing
    return builder.compile(checkpointer=memory)


# Create a single graph instance to reuse
graph = build_graph()
